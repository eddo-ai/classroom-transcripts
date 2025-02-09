import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import os
from urllib.parse import urlparse, parse_qs
import plotly.express as px
import plotly.graph_objects as go
from assemblyai.types import ListTranscriptParameters

load_dotenv()

# Configure AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

st.set_page_config(
    page_title="Transcript Review Dashboard",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "annotations" not in st.session_state:
    st.session_state.annotations = {}
if "selected_transcript" not in st.session_state:
    st.session_state.selected_transcript = None

# Main content area with sidebar
st.title("📚 Transcript Review Dashboard")

# Initialize the transcriber
transcriber = aai.Transcriber()

try:
    # Get list of transcripts with pagination
    transcript_data = []
    completed_count = 0
    last_transcript_id = None

    while completed_count < 10:
        # Fetch next page of transcripts
        params = ListTranscriptParameters(
            limit=20,  # Fetch more per page to increase chances of finding completed ones
            after_id=last_transcript_id,
        )
        response = transcriber.list_transcripts(params=params)

        # Debug view of raw response
        with st.sidebar:
            with st.expander("🔍 Debug: Raw Transcripts", expanded=False):
                st.write(response)

        if not response.transcripts:
            break

        for item in response.transcripts:
            try:
                status = (
                    item.status.value
                    if hasattr(item.status, "value")
                    else str(item.status)
                )
                created_date = pd.to_datetime(item.created)
                friendly_date = created_date.strftime("%A, %B %d at %I:%M %p")

                transcript_data.append(
                    {
                        "ID": item.id,
                        "Status": status,
                        "Created": item.created,
                        "Friendly Date": friendly_date,
                        "Duration": "N/A",  # Duration not available in list response
                        "Audio URL": item.audio_url or "",
                    }
                )

                if status == "completed":
                    completed_count += 1
                    if completed_count >= 10:
                        break

            except Exception as e:
                st.warning(f"Error processing transcript: {str(e)}")
                continue

        # Get ID of last transcript for next page
        if response.transcripts:
            last_transcript_id = response.transcripts[-1].id
        else:
            break

    if not transcript_data:
        st.info("No transcripts found.")
    else:
        # Create display dataframe
        df = pd.DataFrame(transcript_data)
        df["Created"] = pd.to_datetime(df["Created"])

        # Sort by creation date (newest first)
        df = df.sort_values("Created", ascending=False)

        # Sidebar with status summary and recent transcripts
        with st.sidebar:
            st.title("🕒 Recent Transcripts")
            # Show the date range of the transcripts
            st.caption(f"Since {df['Created'].min().strftime('%B %d, %Y')} at {df['Created'].min().strftime('%I:%M %p')}")

            st.divider()

            # Filter to completed transcripts for selection
            completed_df = df[df["Status"] == "completed"]
            if len(completed_df) == 0:
                st.info("No completed transcripts available.")
                selected_id = None
            else:
                # Show 10 most recent completed transcripts
                recent_completed = completed_df.head(10)
                selected_id = st.radio(
                    "Select a transcript to review",
                    options=recent_completed["ID"].tolist(),
                    format_func=lambda x: recent_completed[recent_completed["ID"] == x][
                        "Friendly Date"
                    ].iloc[0],
                    key="transcript_selector",
                )

                # Make a note of in transcripts still in process or error
                processing_df = df[df["Status"] == "processing"]
                error_df = df[df["Status"] == "error"]

                if len(processing_df) > 0:
                    st.warning(
                        f"{len(processing_df)} transcripts are still being processed."
                    )
                if len(error_df) > 0:
                    st.warning(f"{len(error_df)} transcripts have errors.")

            # Move filters to bottom of sidebar
            with st.expander("🔍 Advanced Filters", expanded=False):
                # Status filter
                status_filter = st.multiselect(
                    "Status",
                    ["completed", "error", "queued", "processing"],
                    default=["completed"],
                )

                # Date range filter
                st.subheader("Date Range")
                date_range = st.date_input(
                    "Select dates",
                    value=(datetime.now().date(), datetime.now().date()),
                    help="Filter transcripts by creation date",
                )

        # Main content - Detail View
        if selected_id:
            try:
                transcript = aai.Transcript.get_by_id(selected_id)

                if transcript.status == aai.TranscriptStatus.completed:
                    # Show friendly date as title with audio URL
                    st.header(
                        f"📝 {df[df['ID'] == selected_id]['Friendly Date'].iloc[0]}"
                    )
                    if transcript.audio_url:
                        st.audio(transcript.audio_url)

                    # Create two columns for metadata and debug info
                    meta_col, debug_col = st.columns([2, 1])

                    with meta_col:
                        # Top-level metrics in a clean grid
                        st.subheader("📊 Key Metrics")
                        metrics_cols = st.columns(3)
                        with metrics_cols[0]:
                            st.metric(
                                "Duration",
                                f"{transcript.audio_duration:.1f}s"
                                if transcript.audio_duration
                                else "N/A",
                            )
                            st.metric(
                                "Words",
                                len(transcript.words) if transcript.words else 0,
                            )
                        with metrics_cols[1]:
                            st.metric(
                                "Speakers",
                                len(set(w.speaker for w in transcript.words))
                                if transcript.words
                                else 0,
                            )
                            st.metric(
                                "Avg Words/Min",
                                f"{(len(transcript.words or []) / (transcript.audio_duration or 1) * 60):.1f}"
                                if transcript.words and transcript.audio_duration
                                else "N/A",
                            )
                        with metrics_cols[2]:
                            st.metric(
                                "Confidence",
                                f"{transcript.confidence:.1%}"
                                if hasattr(transcript, "confidence")
                                else "N/A",
                            )
                            st.metric(
                                "Language",
                                getattr(transcript, "language_code", "en").upper(),
                            )

                    with debug_col:
                        # Debug expander with raw transcript data
                        with st.expander("🔍 Debug Info", expanded=False):
                            st.json(
                                {
                                    "id": transcript.id,
                                    "status": str(transcript.status),
                                    "audio_url": transcript.audio_url,
                                    "audio_duration": transcript.audio_duration,
                                    "confidence": getattr(
                                        transcript, "confidence", None
                                    ),
                                    "language": getattr(
                                        transcript, "language_code", None
                                    ),
                                }
                            )

                    # Main content tabs
                    tabs = st.tabs(
                        ["📝 Transcript", "👥 Speakers", "📊 Analysis", "💭 Feedback"]
                    )

                    with tabs[0]:
                        # Full transcript with utterance display
                        st.subheader("📜 Full Transcript")
                        if transcript.utterances:
                            for utterance in transcript.utterances:
                                with st.container():
                                    st.markdown(
                                        f"**{utterance.speaker}** ({utterance.start / 1000:.1f}s - {utterance.end / 1000:.1f}s)"
                                    )
                                    st.write(utterance.text)
                                    st.divider()
                        else:
                            st.write(
                                transcript.text
                                if transcript.text
                                else "No transcript text available"
                            )

                    with tabs[1]:
                        if transcript.utterances:
                            st.subheader("👥 Speaker Statistics")
                            speaker_stats = {}
                            for utterance in transcript.utterances:
                                if utterance.speaker not in speaker_stats:
                                    speaker_stats[utterance.speaker] = {
                                        "word_count": len(utterance.text.split()),
                                        "duration": (utterance.end - utterance.start)
                                        / 1000,
                                        "turns": 1,
                                    }
                                else:
                                    speaker_stats[utterance.speaker]["word_count"] += (
                                        len(utterance.text.split())
                                    )
                                    speaker_stats[utterance.speaker]["duration"] += (
                                        utterance.end - utterance.start
                                    ) / 1000
                                    speaker_stats[utterance.speaker]["turns"] += 1

                            stats_df = pd.DataFrame.from_dict(
                                speaker_stats, orient="index"
                            )
                            stats_df["words_per_minute"] = (
                                stats_df["word_count"] / (stats_df["duration"] / 60)
                            ).round(1)
                            stats_df = stats_df.round(2)

                            st.dataframe(
                                stats_df,
                                column_config={
                                    "word_count": "Total Words",
                                    "duration": "Speaking Time (s)",
                                    "turns": "Speaking Turns",
                                    "words_per_minute": "Words per Minute",
                                },
                            )

                    with tabs[2]:
                        if transcript.words:
                            # Word frequency analysis
                            st.subheader("📊 Word Frequency")
                            word_freq = pd.Series(
                                " ".join([w.text for w in transcript.words])
                                .lower()
                                .split()
                            ).value_counts()
                            common_words = word_freq.head(15)

                            fig = px.bar(
                                x=common_words.index,
                                y=common_words.values,
                                labels={"x": "Word", "y": "Frequency"},
                                title="Most Common Words",
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            # Speaker timeline
                            if transcript.utterances:
                                st.subheader("⏱️ Speaker Timeline")
                                timeline_data = []
                                for utterance in transcript.utterances:
                                    timeline_data.append(
                                        {
                                            "Speaker": utterance.speaker,
                                            "Start": utterance.start / 1000,
                                            "End": utterance.end / 1000,
                                            "Duration": (
                                                utterance.end - utterance.start
                                            )
                                            / 1000,
                                            "Text": utterance.text,
                                        }
                                    )

                                timeline_df = pd.DataFrame(timeline_data)
                                fig = px.timeline(
                                    timeline_df,
                                    x_start="Start",
                                    x_end="End",
                                    y="Speaker",
                                    color="Speaker",
                                    hover_data=["Text", "Duration"],
                                    title="Conversation Flow",
                                )
                                fig.update_layout(
                                    xaxis_title="Time (seconds)", yaxis_title="Speaker"
                                )
                                st.plotly_chart(fig, use_container_width=True)

                    with tabs[3]:
                        # Feedback section
                        st.subheader("💭 Feedback")

                        # Add new feedback
                        with st.expander("✍️ Add Feedback", expanded=True):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                feedback_text = st.text_area(
                                    "Feedback",
                                    placeholder="Enter your feedback here...",
                                    key="new_feedback",
                                )
                            with col2:
                                feedback_type = st.selectbox(
                                    "Type",
                                    [
                                        "General",
                                        "Questioning",
                                        "Engagement",
                                        "Pacing",
                                        "Content",
                                    ],
                                )

                            if st.button("Save Feedback", type="primary"):
                                if feedback_text:
                                    if selected_id not in st.session_state.annotations:
                                        st.session_state.annotations[selected_id] = []

                                    st.session_state.annotations[selected_id].append(
                                        {
                                            "timestamp": datetime.now().timestamp(),
                                            "type": feedback_type,
                                            "feedback": feedback_text,
                                            "created": datetime.now().strftime(
                                                "%Y-%m-%d %H:%M"
                                            ),
                                        }
                                    )
                                    st.success("Feedback saved!")
                                    st.rerun()

                        # Display existing feedback
                        if (
                            selected_id in st.session_state.annotations
                            and st.session_state.annotations[selected_id]
                        ):
                            for annotation in sorted(
                                st.session_state.annotations[selected_id],
                                key=lambda x: x["timestamp"],
                                reverse=True,
                            ):
                                with st.expander(
                                    f"📝 {annotation['type']} - {annotation['created']}",
                                    expanded=True,
                                ):
                                    st.write(annotation["feedback"])
                        else:
                            st.info("No feedback added yet.")
                else:
                    st.warning(f"Transcript status: {transcript.status}")
                    if transcript.status == aai.TranscriptStatus.error:
                        st.error(
                            "Transcription failed. Please check the logs for details."
                        )
                    elif transcript.status in [
                        aai.TranscriptStatus.queued,
                        aai.TranscriptStatus.processing,
                    ]:
                        st.info(
                            "Transcript is still being processed. Please check back later."
                        )

            except Exception as e:
                st.error(f"Error loading transcript details: {str(e)}")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
