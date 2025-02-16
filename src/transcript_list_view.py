import streamlit as st
from src.utils.view_table import get_table_client, list_table_items
from datetime import datetime
import pytz
import assemblyai as aai
import os
from azure.data.tables import UpdateMode, TableClient
import logging

if not st.experimental_user.is_logged_in:
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


def get_timezone_abbr(tz):
    """Get timezone abbreviation (e.g., PST, EST)"""
    return datetime.now(pytz.timezone(tz)).strftime("%Z")


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


@st.cache_data(ttl=300)
def load_table_data(_table_client, user_email, user_role):
    """Load and process table data with caching"""
    # Define a reasonable minimum date (e.g., year 2000)
    MIN_DATE = datetime(2000, 1, 1, tzinfo=pytz.UTC)

    # Get items and filter by current user
    items = list_table_items(_table_client)
    if not items:
        return []

    # Get all transcript statuses at once
    transcript_statuses = get_transcript_statuses()

    items_list = []

    for i, item in enumerate(items):
        item_dict = dict(item)
        # Normalize both user_role and uploaderEmail to lowercase for a consistent comparison.
        if (user_role or "").lower() not in ["coach", "admin"] and item_dict.get(
            "uploaderEmail", ""
        ).lower() != user_email.lower():
            continue

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
    st.session_state.selected_transcript = transcript_id
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
    upload_time_str = (
        upload_time.strftime("%Y-%m-%d %H:%M:%S") if upload_time else "N/A"
    )

    with st.expander(f"📄 {item['RowKey']}", expanded=True):
        # Header with key info
        st.markdown(f"""
        ### File Information
        | Detail | Value |
        |--------|-------|
        | Size | {item.get("formatted_size", "N/A")} |
        | Type | {item.get("blobContentType", "N/A")} |
        | Uploaded | {upload_time_str} |
        | Status | {status_color} {status.title()} |
        | Transcript ID | `{item.get("transcriptId", "N/A")}` |
        | Uploader Name | {item.get("uploaderName", "N/A")} |
        | Uploader Email | {item.get("uploaderEmail", "N/A")} |
        """)

        # Actions row
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if item.get("transcriptId"):
                if st.button(
                    "View Details",
                    key=f"view_{item['transcriptId']}",
                    type="primary",
                ):
                    navigate_to_detail(item["transcriptId"])
        with col2:
            if item.get("audioUrl"):
                st.link_button("Download Audio", item["audioUrl"], type="secondary")

        st.divider()

        # Transcript preview with improved markdown
        if item.get("status") == "completed" and item.get("transcriptId"):
            try:
                transcript = aai.Transcript.get_by_id(item["transcriptId"])
                if transcript.text:
                    st.markdown("#### 📝 Transcript Preview")
                    preview_text = (
                        transcript.text[:500] + "..."
                        if len(transcript.text) > 500
                        else transcript.text
                    )
                    st.markdown(f">{preview_text}")
                elif transcript.utterances:
                    st.markdown("#### 📝 Transcript Preview")
                    preview_utterances = transcript.utterances[
                        :2
                    ]  # Show first 2 utterances
                    for utterance in preview_utterances:
                        st.markdown(f"**{utterance.speaker}**  \n>{utterance.text}")
                    if len(transcript.utterances) > 2:
                        st.markdown("*... (click View Details to see full transcript)*")
                else:
                    st.info("No transcript content available")
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
    user = st.experimental_user
    # For non-coach users, ensure we only count items that belong to them.
    if (getattr(user, "role", "")).lower() not in ["coach", "admin"]:
        items_list = [
            i
            for i in items_list
            if i.get("uploaderEmail", "").lower() == user.email.lower()
        ]
    total_items = len(items_list)
    completed_items = len([i for i in items_list if i.get("status") == "completed"])
    processing_items = len([i for i in items_list if i.get("status") == "processing"])
    error_items = len([i for i in items_list if i.get("status") in ["error", "failed"]])

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
    user = st.experimental_user
    with st.spinner("Loading transcripts..."):
        items_list = load_table_data(
            table_client, user.email, getattr(user, "role", None)
        )

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

    # Display status overview in a fragment
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

    # Add refresh controls in a fragment
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("Refresh Now", icon="��"):
                st.session_state.last_refresh = datetime.now(pytz.UTC)
                st.cache_data.clear()
                st.rerun()
        with col2:
            st.caption(
                f"Last refresh: {st.session_state.last_refresh.astimezone(local_tz).strftime('%H:%M:%S')}"
            )


# Main execution
display_table_data()


def list_all_mappings():
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    table_client = TableClient.from_connection_string(
        connection_string, table_name="TranscriptMappings"
    )

    entities = table_client.list_entities()
    entities_list = list(entities)
    user = st.experimental_user
    # Only filter by uploaderEmail if the user is NOT a coach or admin.
    if (getattr(user, "role", "")).lower() not in ["coach", "admin"]:
        entities_list = [
            entity
            for entity in entities_list
            if entity.get("uploaderEmail", "").lower() == user.email.lower()
        ]
    return entities_list
