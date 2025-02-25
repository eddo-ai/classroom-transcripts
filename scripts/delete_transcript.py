import os
import requests
from dotenv import load_dotenv
import streamlit as st
import assemblyai as aai
import pandas as pd
from datetime import datetime

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="AssemblyAI Transcript Manager", page_icon="🎤", layout="wide"
)

# Initialize session state
if "transcripts" not in st.session_state:
    st.session_state.transcripts = []
if "search_term" not in st.session_state:
    st.session_state.search_term = ""
if "status_filter" not in st.session_state:
    st.session_state.status_filter = "All"
if "current_page" not in st.session_state:
    st.session_state.current_page = 1
if "items_per_page" not in st.session_state:
    st.session_state.items_per_page = 10
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None
if "transcript_details" not in st.session_state:
    st.session_state.transcript_details = None


# Initialize AssemblyAI client
def get_api_key():
    """Get API key from environment or Streamlit secrets."""
    return os.getenv("ASSEMBLYAI_API_KEY") or st.secrets.get("ASSEMBLYAI_API_KEY")


def delete_transcript(transcript_id: str):
    """Delete a transcript from AssemblyAI."""
    try:
        # Try to get API key from environment or Streamlit secrets
        api_key = get_api_key()
        if not api_key:
            return {
                "success": False,
                "message": "ASSEMBLYAI_API_KEY not found in environment or secrets",
            }

        headers = {"authorization": api_key}

        # Make DELETE request to AssemblyAI API
        url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        response = requests.delete(url, headers=headers)

        # Check response
        if response.status_code == 200:
            return {
                "success": True,
                "message": f"Successfully deleted transcript {transcript_id}",
            }
        else:
            return {
                "success": False,
                "message": f"Error deleting transcript: {response.text}",
            }

    except Exception as e:
        return {"success": False, "message": f"Error deleting transcript: {str(e)}"}


def get_transcript_details(transcript_id: str):
    """Get detailed information about a transcript."""
    try:
        api_key = get_api_key()
        if not api_key:
            return {
                "success": False,
                "message": "ASSEMBLYAI_API_KEY not found in environment or secrets",
            }

        # Set API key for AssemblyAI
        aai.settings.api_key = api_key

        # Get transcript
        transcript = aai.Transcript.get_by_id(transcript_id)

        # Get timestamps safely using getattr
        created_at = getattr(transcript, "created_at", None)
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M")

        completed_at = getattr(transcript, "completed_at", None)
        if completed_at and isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(
                completed_at.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M")

        # Get transcript details
        details = {
            "id": transcript.id,
            "status": transcript.status.value,
            "created_at": created_at,
            "completed_at": completed_at,
            "audio_url": transcript.audio_url,
            "error": getattr(transcript, "error", None),
            "confidence": getattr(transcript, "confidence", None),
            "words": len(transcript.words)
            if hasattr(transcript, "words") and transcript.words
            else 0,
            "utterances": len(transcript.utterances)
            if hasattr(transcript, "utterances") and transcript.utterances
            else 0,
            "duration": format_duration(getattr(transcript, "audio_duration", None)),
            "text_preview": truncate_text(transcript.text, 200)
            if hasattr(transcript, "text") and transcript.text
            else "No text available",
        }

        return {"success": True, "details": details}
    except Exception as e:
        return {
            "success": False,
            "message": f"Error getting transcript details: {str(e)}",
        }


def list_transcripts(limit=100):
    """List recent transcripts using AssemblyAI SDK."""
    try:
        api_key = get_api_key()
        if not api_key:
            return {
                "success": False,
                "message": "ASSEMBLYAI_API_KEY not found in environment or secrets",
            }

        # Set API key for AssemblyAI
        aai.settings.api_key = api_key

        # Initialize transcriber
        transcriber = aai.Transcriber()

        # Get transcript list
        params = aai.ListTranscriptParameters(limit=limit)
        transcript_list = transcriber.list_transcripts(params)

        return {
            "success": True,
            "transcripts": [
                {
                    "id": t.id,
                    "status": t.status.value,
                    "created_at": getattr(t, "created_at", None),
                    "audio_url": getattr(t, "audio_url", None),
                    "audio_duration": getattr(t, "audio_duration", None),
                }
                for t in transcript_list.transcripts
            ],
        }
    except Exception as e:
        return {"success": False, "message": f"Error listing transcripts: {str(e)}"}


def format_duration(milliseconds):
    """Format milliseconds to a human-readable duration."""
    if not milliseconds:
        return "Unknown"

    seconds = milliseconds / 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"


def truncate_text(text, max_length=100):
    """Truncate text to max_length and add ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def load_transcripts():
    """Load transcripts and store in session state."""
    with st.spinner("Loading transcripts..."):
        result = list_transcripts(limit=100)

    if result["success"]:
        st.session_state.transcripts = result["transcripts"]
        st.session_state.last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True
    else:
        st.error(result["message"])
        return False


def filter_transcripts(transcripts, search_term="", status_filter="All"):
    """Filter transcripts based on search term and status."""
    filtered = transcripts

    # Filter by search term
    if search_term:
        search_term = search_term.lower()
        filtered = [
            t
            for t in filtered
            if search_term in t["id"].lower()
            or (t["audio_url"] and search_term in t["audio_url"].lower())
        ]

    # Filter by status
    if status_filter != "All":
        filtered = [t for t in filtered if t["status"] == status_filter]

    return filtered


def paginate(items, page=1, items_per_page=10):
    """Paginate a list of items."""
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    return items[start_idx:end_idx]


def delete_button_callback(transcript_id):
    """Callback for delete button."""
    st.session_state[f"delete_{transcript_id}"] = True


def format_transcript_data(transcripts):
    """Format transcript data for display."""
    data = []
    for t in transcripts:
        created_at = t.get("created_at")
        if created_at:
            created_at = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M")

        # Format audio URL for display
        audio_url = t.get("audio_url", "N/A")
        if audio_url and len(audio_url) > 40:
            display_url = audio_url[:20] + "..." + audio_url[-17:]
        else:
            display_url = audio_url

        # Format duration
        duration = format_duration(t.get("audio_duration"))

        data.append(
            {
                "ID": t["id"],
                "Status": t["status"],
                "Created": created_at,
                "Duration": duration,
                "Audio Source": display_url,
            }
        )

    return data


# Streamlit UI
st.title("🎤 AssemblyAI Transcript Browser")

# Add refresh button and last refresh time in the sidebar
with st.sidebar:
    st.subheader("Actions")
    refresh_col, time_col = st.columns([1, 2])

    with refresh_col:
        if st.button("🔄 Refresh", use_container_width=True):
            load_transcripts()

    with time_col:
        if st.session_state.last_refresh:
            st.caption(f"Last updated: {st.session_state.last_refresh}")

    st.divider()

    # Filters
    st.subheader("Filters")
    st.session_state.search_term = st.text_input(
        "Search by ID or URL", value=st.session_state.search_term
    )

    status_options = ["All", "queued", "processing", "completed", "error", "failed"]
    st.session_state.status_filter = st.selectbox(
        "Status filter",
        options=status_options,
        index=status_options.index(st.session_state.status_filter),
    )

    # Pagination controls
    st.divider()
    st.subheader("Display Settings")
    st.session_state.items_per_page = st.select_slider(
        "Items per page", options=[5, 10, 25, 50], value=st.session_state.items_per_page
    )

    # API Key info
    st.divider()
    api_key = get_api_key()
    if api_key:
        st.success("✅ AssemblyAI API key found")
    else:
        st.error("❌ AssemblyAI API key not found")
        st.info("Set ASSEMBLYAI_API_KEY in your environment or Streamlit secrets")

# Load transcripts on first run
if not st.session_state.transcripts:
    load_transcripts()

# Process transcripts
if st.session_state.transcripts:
    # Filter transcripts
    filtered_transcripts = filter_transcripts(
        st.session_state.transcripts,
        st.session_state.search_term,
        st.session_state.status_filter,
    )

    # Calculate total pages
    total_items = len(filtered_transcripts)
    total_pages = max(
        1,
        (total_items + st.session_state.items_per_page - 1)
        // st.session_state.items_per_page,
    )

    # Adjust current page if needed
    if st.session_state.current_page > total_pages:
        st.session_state.current_page = total_pages

    # Paginate
    page_transcripts = paginate(
        filtered_transcripts,
        st.session_state.current_page,
        st.session_state.items_per_page,
    )

    # Display transcripts
    if page_transcripts:
        # Format data
        formatted_data = format_transcript_data(page_transcripts)

        # Display info about filtered results
        st.caption(
            f"Showing {len(page_transcripts)} of {total_items} transcripts (filtered from {len(st.session_state.transcripts)} total)"
        )

        # Display as dataframe
        df = pd.DataFrame(formatted_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Pagination controls
        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if st.session_state.current_page > 1:
                if st.button("← Previous", use_container_width=True):
                    st.session_state.current_page -= 1
                    st.rerun()

        with col2:
            st.caption(f"Page {st.session_state.current_page} of {total_pages}")

        with col3:
            if st.session_state.current_page < total_pages:
                if st.button("Next →", use_container_width=True):
                    st.session_state.current_page += 1
                    st.rerun()

        # Transcript selection and actions
        st.divider()
        st.subheader("Transcript Actions")

        selected_transcript_id = st.selectbox(
            "Select a transcript",
            options=[t["id"] for t in page_transcripts],
            format_func=lambda x: f"{x} ({next((t['status'] for t in page_transcripts if t['id'] == x), 'unknown')})",
        )

        if selected_transcript_id:
            col1, col2 = st.columns([1, 1])

            with col1:
                # View details button
                if st.button("📄 View Details", use_container_width=True):
                    with st.spinner("Loading transcript details..."):
                        result = get_transcript_details(selected_transcript_id)

                        if result["success"]:
                            st.session_state.transcript_details = result["details"]
                        else:
                            st.error(result["message"])

            with col2:
                # Delete button
                delete_pressed = st.button(
                    "🗑️ Delete Transcript", type="primary", use_container_width=True
                )
                if delete_pressed:
                    st.warning(
                        "⚠️ Are you sure you want to delete this transcript? This action cannot be undone."
                    )
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("❌ Cancel", use_container_width=True):
                            st.rerun()
                    with col2:
                        if st.button("✅ Confirm Delete", use_container_width=True):
                            with st.spinner("Deleting transcript..."):
                                result = delete_transcript(selected_transcript_id)

                                if result["success"]:
                                    st.success(result["message"])
                                    # Remove from session state
                                    st.session_state.transcripts = [
                                        t
                                        for t in st.session_state.transcripts
                                        if t["id"] != selected_transcript_id
                                    ]
                                    # Clear selected transcript if it was deleted
                                    if (
                                        st.session_state.transcript_details
                                        and st.session_state.transcript_details["id"]
                                        == selected_transcript_id
                                    ):
                                        st.session_state.transcript_details = None
                                else:
                                    st.error(result["message"])

        # Display transcript details if available
        if st.session_state.transcript_details:
            st.divider()
            st.subheader(
                f"Transcript Details: {st.session_state.transcript_details['id']}"
            )

            details = st.session_state.transcript_details
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Status**: " + details["status"])
                st.markdown("**Created**: " + (details["created_at"] or "Unknown"))
                st.markdown(
                    "**Completed**: " + (details["completed_at"] or "Not completed")
                )

            with col2:
                st.markdown("**Duration**: " + details["duration"])
                st.markdown("**Words**: " + str(details["words"]))
                st.markdown("**Speakers**: " + str(details["utterances"]))

            with col3:
                st.markdown(
                    "**Confidence**: "
                    + (
                        str(details["confidence"])
                        if details["confidence"]
                        else "Unknown"
                    )
                )
                if details["error"]:
                    st.markdown("**Error**: " + details["error"])

            # Audio URL
            st.markdown("**Audio URL**: " + (details["audio_url"] or "Not available"))

            # Transcript preview
            st.subheader("Transcript Preview")
            st.markdown(details["text_preview"])

            # Clear details button
            if st.button("Close Details"):
                st.session_state.transcript_details = None
                st.rerun()
    else:
        st.info("No transcripts match your filters")
else:
    st.info("No transcripts found. Click 'Refresh' to load transcripts.")

# Footer
st.divider()
st.caption("Built with AssemblyAI API")

if __name__ == "__main__":
    # The app is run with streamlit run script
    pass
