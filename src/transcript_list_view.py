import streamlit as st
from src.utils.view_table import get_table_client, list_table_items
from datetime import datetime
import pytz
import assemblyai as aai
import os
import logging

from utils.azure_storage import get_sas_url_for_audio_file_name

DEBUG = bool(os.getenv("DEBUG", False))
TRANSCRIPT_PREVIEW_MAX_LENGTH = 1000
TRANSCRIPT_PREVIEW_SPEAKER_TURNS = 5

if not st.experimental_user.get("is_logged_in"):
    st.login()

# Initialize session state for status values if not already set
if "transcription_statuses" not in st.session_state:
    st.session_state.transcription_statuses = [
        "queued",  # Initial state
        "processing",  # Being transcribed
        "completed",  # Done
        "error",  # Failed
        "failed",  # Another error state
    ]

# Initialize session state for auto-refresh
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now(pytz.UTC)

# US timezone options
US_TIMEZONES = [
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "US/Alaska",
    "US/Hawaii",
]

# Initialize timezone in session state
if "timezone" not in st.session_state:
    st.session_state.timezone = "US/Pacific"

# Add timezone picker to sidebar
with st.sidebar:
    st.session_state.timezone = st.selectbox(
        "Select Timezone",
        options=US_TIMEZONES,
        index=US_TIMEZONES.index(st.session_state.timezone),
        help="Choose your local timezone",
        format_func=lambda x: x.replace("US/", ""),
    )

# Update local_tz to use session state
local_tz = pytz.timezone(st.session_state.timezone)


# Initialize AssemblyAI client
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
transcriber = aai.Transcriber()

# Initialize session state for pagination
if "items_per_page" not in st.session_state:
    st.session_state.items_per_page = 5  # Initial number of items to show
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# Get admin emails from Streamlit secrets
ADMIN_EMAILS = [email.strip().lower() for email in st.secrets.admin_emails.split(",")]

# Debug logging for admin list
if DEBUG:
    st.write("Debug - Admin emails:", ADMIN_EMAILS)


def is_admin(email: str) -> bool:
    """Check if the given email belongs to an admin"""
    return email.lower() in ADMIN_EMAILS


def reset_pagination():
    """Reset pagination state"""
    st.session_state.items_per_page = 5
    st.session_state.current_page = 1


def format_file_size(size_in_bytes):
    """Convert bytes to human readable format"""
    if not isinstance(size_in_bytes, (int, float)):
        return "N/A"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_in_bytes < 1024:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024
    return f"{size_in_bytes:.2f} TB"


# Get timezone abbreviation



def localized_timestamp(timestamp):
    """Get localized timestamp"""
    local_timestamp = timestamp.astimezone(local_tz)
    time_string = local_timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")
    return time_string


def get_transcript_status(transcript_id):
    """Get transcript status from AssemblyAI"""
    # Skip test data
    if transcript_id.startswith("test_"):
        return "completed"

    try:
        transcript = aai.Transcript.get_by_id(transcript_id)
        return transcript.status.value
    except Exception as e:
        if "not found" in str(e).lower():
            return "error"  # Transcript doesn't exist in AssemblyAI
        st.error(f"Error getting transcript status: {str(e)}")
        return "error"


st.title("🔍 Audio Files & Transcriptions")

# Initialize table client
table_client = get_table_client()


def can_view_transcript(transcript_email: str, user_email: str) -> bool:
    """Check if user can view a specific transcript"""
    if is_admin(user_email):
        return True
    # If no uploader email is set, only admins can view
    if not transcript_email:
        return False
    return transcript_email.lower() == user_email.lower()


@st.cache_data(ttl=300)
def get_transcript_statuses():
    """Get all transcript statuses in one API call"""
    try:
        # Create parameters to get all transcripts
        params = aai.ListTranscriptParameters(
            limit=100  # Adjust limit as needed
        )
        response = transcriber.list_transcripts(params)

        # Create mapping of transcript ID to status
        status_map = {}
        for t in response.transcripts:
            # Handle test data
            if t.id.startswith("test_"):
                status_map[t.id] = "completed"
            else:
                status_map[t.id] = t.status.value

        # Get next page if available
        while response.page_details.before_id_of_prev_url:
            params.before_id = response.page_details.before_id_of_prev_url
            response = transcriber.list_transcripts(params)
            for t in response.transcripts:
                if t.id.startswith("test_"):
                    status_map[t.id] = "completed"
                else:
                    status_map[t.id] = t.status.value

        return status_map
    except Exception as e:
        st.error(f"Error getting transcript statuses: {str(e)}")
        return {}


def query_table_entities(
    table_client, user_email: str, table_name: str = "Transcriptions"
):
    """
    Query table entities based on user permissions.

    Args:
        table_client: Azure TableClient instance
        user_email: Email of the current user
        table_name: Name of the table to query (default: TranscriptMappings)

    Returns:
        List of entities the user has permission to view
    """

    if not user_email:
        return []

    try:
        # For regular users, only fetch their items
        if not is_admin(user_email):
            st.write(
                f"Debug - User {user_email} is not admin, fetching only their items"
            )
            filter_condition = f"uploaderEmail eq '{user_email.lower()}'"
            items = list(table_client.query_entities(filter_condition))
        else:
            st.write(f"Debug - User {user_email} is admin, fetching all items")
            items = list_table_items(table_client)

        st.write(f"Debug - Number of items fetched: {len(items) if items else 0}")
        return items

    except Exception as e:
        logging.error(f"Error querying table {table_name}: {e}")
        return []


@st.cache_data(ttl=300)
def load_table_data(_table_client):
    """Load and process table data with caching"""
    MIN_DATE = datetime(2000, 1, 1, tzinfo=pytz.UTC)

    user = st.experimental_user
    validated_email = user.email if user.email_verified else None

    if validated_email is not None:
        table_name = "debug_transcriptions" if DEBUG else "Transcriptions"
        # Use consolidated query function
        items = query_table_entities(_table_client, str(validated_email), table_name)

    if not items:
        return []

    # Get all transcript statuses at once
    transcript_statuses = get_transcript_statuses()
    items_list = []

    for item in items:
        item_dict = dict(item)

        # Add formatted size
        if "blobSize" in item_dict:
            item_dict["formatted_size"] = format_file_size(item_dict["blobSize"])

        # Get status from cached transcript statuses
        if "transcriptId" in item_dict:
            item_dict["status"] = transcript_statuses.get(
                item_dict["transcriptId"], "error"
            )
        else:
            item_dict["status"] = "pending"

        item_dict["_previous_status"] = item_dict["status"]

        # Process timestamp
        if "uploadTime" not in item_dict:
            item_dict["uploadTime"] = item_dict.get("Timestamp", MIN_DATE)

        try:
            # Handle different timestamp types
            if isinstance(item_dict["uploadTime"], str):
                dt = datetime.fromisoformat(
                    item_dict["uploadTime"].replace("Z", "+00:00")
                )
            elif isinstance(item_dict["uploadTime"], datetime):
                dt = item_dict["uploadTime"]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
            else:
                dt = MIN_DATE

            local_dt = dt.astimezone(local_tz)
            item_dict["_timestamp"] = local_dt
            item_dict["uploadTime"] = local_dt
        except ValueError as e:
            logging.error(f"Error parsing time: {e}")
            item_dict["_timestamp"] = MIN_DATE
            item_dict["uploadTime"] = MIN_DATE

        # Add class name and description
        item_dict["className"] = item_dict.get("className", "N/A")
        item_dict["description"] = item_dict.get("description", "N/A")

        items_list.append(item_dict)

    return items_list


@st.cache_data(ttl=30)  # Cache for 30 seconds only for pending items
def get_pending_transcript_statuses(transcript_ids):
    """Get status updates for pending transcripts"""
    if not transcript_ids:
        return {}

    status_map = {}
    for transcript_id in transcript_ids:
        try:
            transcript = aai.Transcript.get_by_id(transcript_id)
            status_map[transcript_id] = transcript.status.value
        except Exception as e:
            logging.error(f"Error getting status for {transcript_id}: {e}")
            status_map[transcript_id] = "error"
    return status_map


def should_auto_refresh(items_list):
    """Determine if we should auto-refresh based on pending items"""
    pending_statuses = {"queued", "processing"}
    # Only return True if there are actual pending items
    has_pending = any(item.get("status") in pending_statuses for item in items_list)
    # Add a timestamp check to prevent rapid refreshes
    time_since_refresh = (
        datetime.now(pytz.UTC) - st.session_state.last_refresh
    ).total_seconds()
    return has_pending and time_since_refresh >= 30


def navigate_to_detail(transcript_id):
    """Navigate to the detail view for a transcript"""
    st.session_state.selected_transcript = {
        "id": transcript_id,
        "audio_url_with_sas": get_sas_url_for_audio_file_name(transcript_id),
    }
    st.query_params["id"] = transcript_id  # Use new API to set params
    st.switch_page("src/transcript_detail_view.py")


def display_transcript_item(item):
    """Display a single transcript item in a fragment"""
    # Get status info for formatting
    status = item.get("status", "N/A")
    status_color = {
        "completed": "🟢",
        "processing": "🟡",
        "error": "🔴",
        "failed": "🔴",
        "queued": "⚪",
    }.get(status, "⚪")

    # Format upload time
    upload_time = item.get("uploadTime")
    upload_time_str = localized_timestamp(upload_time)

    with st.expander(f"📄 {item['originalFileName']}", expanded=False):
        # Header with key info
        st.markdown(f"""
        ### File Information
        | Detail | Value |
        |--------|-------|
        | Size | {item.get("formatted_size", "N/A")} |
        | Uploaded | {upload_time_str} |
        | Status | {status_color} {status.title()} |
        | Class Name | {item.get("className", "N/A")} |
        | Description | {item.get("description", "N/A")} |
        """)

        # Audio player
        audio_url_with_sas = get_sas_url_for_audio_file_name(item.get("RowKey"))
        if audio_url_with_sas:
            st.audio(audio_url_with_sas)

        # Transcript preview with improved markdown
        if item.get("status") == "completed" and item.get("transcriptId"):
            try:
                transcript = aai.Transcript.get_by_id(item["transcriptId"])

                # Good transcriptions have text and utterances
                if transcript.text and transcript.utterances:
                    ### Show 3 utterances and a link to download the full transcript
                    st.markdown("#### 📝 Transcript Preview")
                    for utterance in transcript.utterances[:TRANSCRIPT_PREVIEW_SPEAKER_TURNS]:
                        if DEBUG:
                            st.write(utterance)
                        st.markdown(f"**Speaker {utterance.speaker}**:  {utterance.text}")
                    ## TODO: Name speakers
                elif transcript.text:
                    st.info("AI failed to distinguish speakers.")
                    st.write(transcript.text[:TRANSCRIPT_PREVIEW_MAX_LENGTH])
            except Exception as e:
                st.warning("Could not load transcript preview")
        elif item.get("status") == "processing":
            st.markdown("""
            #### ⏳ Processing
            The transcript is still being generated. This typically takes 1-2 minutes.
            """)
        elif item.get("status") in ["error", "failed"]:
            st.markdown("""
            #### ❌ Error
            There was a problem processing this transcript. Please try uploading the file again.
            """)


def display_status_overview(items_list):
    """Display status overview in a fragment"""
    # Only count items the user has permission to see

    user = st.experimental_user

    validated_email = user.email if user.email_verified else None

    # Filter items based on validated email
    viewable_items = (
        items_list
        if is_admin(str(validated_email))
        else [
            item
            for item in items_list
            if can_view_transcript(item.get("uploaderEmail", ""), str(validated_email))
        ]
    )

    total_items = len(viewable_items)
    completed_items = len([i for i in viewable_items if i.get("status") == "completed"])
    processing_items = len(
        [i for i in viewable_items if i.get("status") == "processing"]
    )
    error_items = len(
        [i for i in viewable_items if i.get("status") in ["error", "failed"]]
    )

    st.subheader("📊 Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Files", total_items)
    with col2:
        st.metric("Completed", completed_items)
    with col3:
        st.metric("Processing", processing_items)
    with col4:
        st.metric("Errors", error_items)


def display_table_data():
    """Display the table data with progress indicators"""
    items_list = load_table_data(table_client)

    if not items_list:
        st.info("No files found in the system")
        return

    # Sort by timestamp
    items_list.sort(key=lambda x: x.get("_timestamp", datetime.min), reverse=True)

    # Auto-refresh logic
    if st.session_state.auto_refresh and should_auto_refresh(items_list):
        time_since_refresh = (
            datetime.now(pytz.UTC) - st.session_state.last_refresh
        ).total_seconds()
        if time_since_refresh >= 30:
            st.session_state.last_refresh = datetime.now(pytz.UTC)
            st.cache_data.clear()
            st.rerun()

    # Display status overview with already filtered list
    with st.container():
        display_status_overview(items_list)
        st.divider()

    # Filter controls
    st.subheader("🔍 Transcripts")
    col1, col2 = st.columns([2, 1])
    with col1:
        status_filter = st.multiselect(
            "Filter by Status",
            options=st.session_state.transcription_statuses,
            default=["completed"],
            help="Select one or more statuses to filter",
            on_change=reset_pagination,  # Reset pagination when filter changes
        )
    with col2:
        sort_order = st.selectbox(
            "Sort by",
            options=["Newest First", "Oldest First"],
            index=0,
            on_change=reset_pagination,  # Reset pagination when sort changes
        )

    # Apply filters
    filtered_items = [
        item for item in items_list if item.get("status") in status_filter
    ]

    # Apply sorting
    if sort_order == "Oldest First":
        filtered_items.reverse()

    # Calculate pagination
    total_items = len(filtered_items)
    start_idx = 0
    end_idx = st.session_state.items_per_page

    # Display items in fragments
    for item in filtered_items[start_idx:end_idx]:
        with st.container():
            display_transcript_item(item)

    # Load More button
    if end_idx < total_items:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(
                f"Load More ({total_items - end_idx} remaining)",
                use_container_width=True,
            ):
                st.session_state.items_per_page += 5
                st.rerun()

    # Show total count
    st.caption(f"Showing {min(end_idx, total_items)} of {total_items} transcripts")


display_table_data()
