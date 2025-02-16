import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
import os
from assemblyai.types import ListTranscriptParameters
import pytz
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import requests
from typing import Optional
import altair as alt
from src.utils.azure_storage import get_blob_sas_url
from src.upload import get_account_key_from_connection_string
from src.utils.google_drive import upload_transcript_to_drive

# Configure AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")


def back_to_list():
    """Navigate back to the transcript list view."""
    st.session_state.selected_transcript = None
    st.query_params.clear()  # Clear URL parameters
    st.switch_page("src/transcript_list_view.py")


# Initialize session state before any UI elements
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "annotations" not in st.session_state:
    st.session_state.annotations = {}
if "selected_transcript" not in st.session_state:
    st.session_state.selected_transcript = None
if "transcription_settings" not in st.session_state:
    st.session_state.transcription_settings = {
        "language_code": "en",
        "speaker_labels": True,
        "speakers_expected": 2,  # Default to 2 speakers
        "auto_highlights": False,
        "punctuate": True,
        "format_text": True,
        "content_safety": False,
        "filter_profanity": False,
        "disfluencies": False,
        "sentiment_analysis": False,
        "auto_chapters": False,
        "entity_detection": False,
        "redact_pii": False,
        "redact_pii_audio": False,
        "redact_pii_policies": [
            "person_name",
            "email_address",
            "phone_number",
            "location",
            "organization",
            "credit_card_number",
            "credit_card_cvv",
            "banking_information",
            "us_social_security_number",
            "medical_condition",
        ],  # Default PII policies including financial and medical items
        "redact_pii_sub": "entity_type",
        "word_boost": [],  # Initialize empty word boost list
    }
if "transcription_settings_form" not in st.session_state:
    st.session_state.transcription_settings_form = (
        st.session_state.transcription_settings.copy()
    )

# Get transcript ID from query parameters or session state
if "id" in st.query_params:
    transcript_id = st.query_params["id"]
    st.session_state.selected_transcript = transcript_id
elif not st.session_state.get("selected_transcript"):
    back_to_list()

# Initialize debug mode from environment variable
DEBUG = os.getenv("DEBUG", False)

# Now add the title
st.title("📚 Transcript Review Dashboard")

# Initialize the transcriber
transcriber = aai.Transcriber()

# Use the same US timezone list and picker
US_TIMEZONES = [
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "US/Alaska",
    "US/Hawaii",
]

if "timezone" not in st.session_state:
    st.session_state.timezone = "US/Pacific"

with st.sidebar:
    st.session_state.timezone = st.selectbox(
        "Select Timezone",
        options=US_TIMEZONES,
        index=US_TIMEZONES.index(st.session_state.timezone),
        help="Choose your local timezone",
        format_func=lambda x: x.replace("US/", ""),
    )


def format_date_with_timezone(
    date_str, timezone_name="America/New_York", show_timezone=True
):
    # Convert string to datetime if needed
    if isinstance(date_str, str):
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    else:
        date = date_str

    # Convert to selected timezone
    timezone = pytz.timezone(timezone_name)
    localized_date = date.astimezone(timezone)

    # Format with a friendly string like "Monday, March 20 at 2:30 PM EDT"
    format_string = "%A, %B %d at %I:%M %p"
    if show_timezone:
        format_string += " %Z"
    return localized_date.strftime(format_string)


def format_duration(seconds):
    """Convert seconds to HH:MM:SS format"""
    if not seconds:
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


# Add caching functions
@st.cache_data(ttl=3600)
def get_transcript_list() -> list:
    """Cache the list of transcripts."""
    transcript_data = []
    completed_count = 0
    last_transcript_id = None

    while completed_count < 10:
        params = ListTranscriptParameters(limit=20, after_id=last_transcript_id)
        response = transcriber.list_transcripts(params=params)

        if not response.transcripts:
            break

        for item in response.transcripts:
            status = str(
                item.status.value if hasattr(item.status, "value") else item.status
            )
            transcript_data.append(
                {
                    "ID": item.id,
                    "Status": status,
                    "Created": item.created,
                    "Audio URL": item.audio_url or "",
                }
            )
            if status == "completed":
                completed_count += 1
                if completed_count >= 10:
                    break

        if response.transcripts:
            last_transcript_id = response.transcripts[-1].id

    return transcript_data


@st.cache_data(ttl=3600)
def get_cached_transcript_details(transcript_id: str) -> dict:
    """Get cached transcript details excluding status."""
    transcript = aai.Transcript.get_by_id(transcript_id)

    # Explicitly set audio_url to None for AssemblyAI CDN URLs
    audio_url = None
    if transcript.audio_url and "blob.core.windows.net" in transcript.audio_url:
        audio_url = transcript.audio_url

    return {
        "id": transcript.id,
        "text": transcript.text,
        "words": transcript.words,
        "utterances": transcript.utterances,
        "audio_url": audio_url,  # Only include blob storage URLs
        "audio_duration": transcript.audio_duration,
        "language_code": getattr(transcript, "language_code", "en"),
        "confidence": getattr(transcript, "confidence", None),
    }


@st.cache_data(ttl=3000)
def get_blob_sas_url_cached(audio_url: str) -> Optional[str]:
    """Get cached SAS URL for blob storage audio file."""
    try:
        if not audio_url:
            return None

        # Only process Azure blob storage URLs
        if "blob.core.windows.net" not in audio_url:
            st.warning("Audio file not in Azure storage")
            return None

        # If URL already has a SAS token, return it as is
        if "?st=" in audio_url:
            return audio_url

        # Get storage account key from connection string
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            st.error("Missing Azure Storage connection string")
            return None

        # Get account key using utility function
        storage_account_key = get_account_key_from_connection_string(connection_string)
        if not storage_account_key:
            st.error("Could not extract storage account key from connection string")
            return None

        # Parse URL to get account, container, and blob
        parts = audio_url.split("/")
        account = parts[2].split(".")[0]
        container_name = parts[3]
        blob_name = "/".join(parts[4:])

        # Use the utility function to get the SAS URL
        return get_blob_sas_url(
            blob_name=blob_name,
            container_name=container_name,
            storage_account=account,
            storage_account_key=storage_account_key,
        )

    except Exception as e:
        st.warning(f"Could not generate SAS URL: {str(e)}")
        return None


def get_transcript_status(transcript_id: str) -> str:
    """Get fresh transcript status without caching."""
    transcript = aai.Transcript.get_by_id(transcript_id)
    return str(transcript.status)


def is_recent_transcript(created_date: datetime, hours: int = 12) -> bool:
    """Check if transcript is less than N hours old."""
    now = datetime.now(created_date.tzinfo)
    age = now - created_date
    return age.total_seconds() < (hours * 3600)


def try_assemblyai_audio(audio_url: str) -> bool:
    """Test if AssemblyAI CDN URL is accessible."""
    try:
        response = requests.head(audio_url, timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def show():
    """Display the transcript detail page."""
    try:
        # Add back button at the top
        if st.button("← Back to List", type="secondary"):
            back_to_list()
            return

        # Use transcript ID from session state
        if not st.session_state.selected_transcript:
            st.info(
                "No transcript selected. Please select a transcript from the list view."
            )
            back_to_list()
            return

        selected_id = st.session_state.selected_transcript
        try:
            transcript_details = get_cached_transcript_details(selected_id)
            transcript = aai.Transcript.get_by_id(selected_id)

            if transcript.status == aai.TranscriptStatus.completed:
                # Get timezone from session state
                selected_timezone = st.session_state.timezone

                # Show transcript ID and status
                st.header(f"📝 Transcript Details")
                st.caption(f"ID: {selected_id}")

                # Main content tabs
                tab_list = ["📝 Transcript", "💭 Insights"]
                if DEBUG:
                    tab_list.append("🔍 Details")

                # Download options
                download_cols = st.columns([1, 1, 2])
                with download_cols[0]:
                    if st.button("📥 Download Transcript", type="secondary"):
                        # Prepare transcript content
                        if transcript.utterances:
                            content = "\n\n".join(
                                [
                                    f"{u.speaker} ({u.start / 1000:.1f}s - {u.end / 1000:.1f}s):\n{u.text}"
                                    for u in transcript.utterances
                                ]
                            )
                        else:
                            content = transcript.text or "No transcript text available"

                            # Create download button
                            st.download_button(
                                label="Save as TXT",
                                data=content,
                                file_name=f"transcript_{selected_id}.txt",
                                mime="text/plain",
                            )

                with download_cols[1]:
                    if (
                        transcript.audio_url
                        and "blob.core.windows.net" in transcript.audio_url
                    ):
                        # Get SAS URL for Azure blob storage
                        download_url = get_blob_sas_url_cached(transcript.audio_url)
                        if download_url:
                            st.link_button(
                                "🔊 Download Audio", download_url, type="secondary"
                            )

                # Add a UI element to specify Google Drive folder
                drive_folder = st.text_input("Google Drive Folder", value="Classroom Transcripts")

                tabs = st.tabs(tab_list)

                with tabs[0]:
                    # Quick stats summary at top
                    quick_stats = st.columns(4)
                    with quick_stats[0]:
                        st.caption("Duration")
                        st.write(
                            f"⏱️ {format_duration(transcript.audio_duration) if transcript.audio_duration else 'N/A'}"
                        )
                    with quick_stats[1]:
                        st.caption("Speakers")
                        st.write(
                            f"👥 {len(set(w.speaker for w in transcript.words)) if transcript.words else '0'}"
                        )
                    with quick_stats[2]:
                        st.caption("Words")
                        st.write(
                            f"📝 {len(transcript.words):,}" if transcript.words else "0"
                        )
                    with quick_stats[3]:
                        st.caption("Language")
                        st.write(
                            f"🌐 {getattr(transcript, 'language_code', 'en').upper()}"
                        )

                    # Audio player
                    if (
                        transcript.audio_url
                        and "blob.core.windows.net" in transcript.audio_url
                    ):
                        # Use the same SAS URL for the audio player
                        player_url = get_blob_sas_url_cached(transcript.audio_url)
                        if player_url:
                            st.audio(player_url)

                    st.divider()

                    # Full transcript with utterance display
                    st.subheader("Full Transcript")
                    if transcript.utterances:
                        for utterance in transcript.utterances:
                            with st.container():
                                st.markdown(
                                    f"**{utterance.speaker}** ({format_duration(utterance.start / 1000)} - {format_duration(utterance.end / 1000)})"
                                )
                                st.write(utterance.text)
                                st.divider()
                    else:
                        st.write(
                            transcript.text
                            if transcript.text
                            else "No transcript text available"
                        )

                with tabs[1]:  # Insights tab
                    if transcript.words:
                        # Word Cloud
                        st.subheader("☁️ Word Cloud")
                        text = " ".join([w.text for w in transcript.words]).lower()
                        wordcloud = WordCloud(
                            width=1600,
                            height=800,
                            background_color="white",
                            scale=2,
                            collocations=False,
                        ).generate(text)

                        fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
                        ax.imshow(wordcloud, interpolation="bilinear")
                        ax.axis("off")
                        st.pyplot(fig)
                        plt.close()

                        st.divider()

                    if transcript.utterances:
                        # Speaker Timeline
                        st.subheader("⏱️ Speaker Timeline")
                        timeline_data = []
                        for utterance in transcript.utterances:
                            try:
                                if not all(
                                    hasattr(utterance, attr)
                                    for attr in ["start", "end", "speaker", "text"]
                                ):
                                    continue

                                start_time = float(utterance.start) / 1000.0
                                end_time = float(utterance.end) / 1000.0

                                if start_time >= end_time:
                                    continue

                                timeline_data.append(
                                    {
                                        "Speaker": str(utterance.speaker),
                                        "Start": start_time,
                                        "End": end_time,
                                        "Text": utterance.text[:50] + "..."
                                        if len(utterance.text) > 50
                                        else utterance.text,
                                    }
                                )

                            except Exception as e:
                                st.warning(f"Skipped utterance: {str(e)}")
                                continue

                        if timeline_data:
                            try:
                                timeline_df = pd.DataFrame(timeline_data)
                                timeline_df["Speaker"] = timeline_df["Speaker"].astype(
                                    str
                                )
                                timeline_df["Text"] = timeline_df["Text"].astype(str)
                                timeline_df = timeline_df.sort_values("Start")

                                timeline = (
                                    alt.Chart(
                                        data=alt.Data(
                                            values=timeline_df.to_dict("records")
                                        )
                                    )
                                    .encode(
                                        x=alt.X(
                                            "Start:Q",
                                            title="Time",
                                            axis=alt.Axis(
                                                format="d",
                                                labelExpr="datum.value == 0 ? '00:00' : timeFormat(datum.value * 1000, '%M:%S')",
                                                grid=True,
                                            ),
                                        ),
                                        x2="End:Q",
                                        y=alt.Y(
                                            "Speaker:N",
                                            sort=alt.EncodingSortField(
                                                field="Start", order="ascending"
                                            ),
                                            title="Speaker",
                                        ),
                                        color=alt.Color(
                                            "Speaker:N",
                                            legend=None,
                                            scale=alt.Scale(scheme="tableau10"),
                                        ),
                                        tooltip=[
                                            "Speaker",
                                            alt.Tooltip(
                                                "Start:Q", format=".1f", title="Start"
                                            ),
                                            alt.Tooltip(
                                                "End:Q", format=".1f", title="End"
                                            ),
                                            "Text",
                                        ],
                                    )
                                    .mark_bar(opacity=0.8, height=20, cornerRadius=3)
                                    .properties(
                                        width="container",
                                        height=300,
                                        title="Conversation Flow",
                                    )
                                )

                                # Add brush selection for zoom
                                brush = alt.selection_interval(
                                    encodings=["x"], name="brush"
                                )
                                timeline = timeline.add_selection(
                                    brush
                                ).transform_filter(brush)

                                # Customize chart appearance
                                timeline = (
                                    timeline.configure_axis(
                                        grid=True,
                                        gridColor="#EEEEEE",
                                        labelFontSize=12,
                                        titleFontSize=14,
                                    )
                                    .configure_view(strokeWidth=0)
                                    .configure_title(fontSize=16, anchor="start")
                                )

                                st.altair_chart(timeline, use_container_width=True)

                            except Exception as e:
                                st.error(f"Visualization error: {str(e)}")
                                if DEBUG:
                                    st.write("Error details:", str(e))

                    if DEBUG:
                        with tabs[2]:  # Debug tab
                            st.write("Debug information:")
                            st.write(f"Transcript ID: {transcript.id}")
                            st.write(f"Status: {transcript.status}")
                            st.write(f"Audio URL: {transcript.audio_url}")
                            st.write(f"Text: {transcript.text}")
                            st.write(
                                f"Words: {len(transcript.words) if transcript.words else 0}"
                            )
                            st.write(
                                f"Utterances: {len(transcript.utterances) if transcript.utterances else 0}"
                            )
                            st.write(
                                f"Language: {getattr(transcript, 'language_code', 'en').upper()}"
                            )
                            st.write(
                                f"Confidence: {getattr(transcript, 'confidence', 'N/A')}"
                            )
                            st.write(
                                f"Duration: {format_duration(transcript.audio_duration) if transcript.audio_duration else 'N/A'}"
                            )

                # Upload transcript to Google Drive
                drive_response = upload_transcript_to_drive(transcript, filename=f"{drive_folder}/{selected_id}.txt")
                if not drive_response["success"]:
                    logging.error(f"Failed to upload transcript to Google Drive: {drive_response['error']}")
                    st.error("Failed to upload transcript to Google Drive. Please try again.")
                else:
                    st.success(f"Transcript uploaded to Google Drive: [View]({drive_response['link']})")

            else:
                st.warning(
                    f"Transcript is not completed. Current status: {transcript.status}"
                )

        except Exception as e:
            st.error(f"Error loading transcript details: {str(e)}")

    except Exception as e:
        st.error(f"Error loading transcript view: {str(e)}")


show()
