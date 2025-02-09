import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import os
from urllib.parse import urlparse, parse_qs
import plotly.express as px
import plotly.graph_objects as go

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
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "list"

# Sidebar filters
with st.sidebar:
    st.title("🔍 Filters")

    # View mode selector
    view_mode = st.radio(
        "View Mode",
        options=["List View", "Detail View"],
        index=0 if st.session_state.view_mode == "list" else 1,
    )
    # Update view mode in session state
    st.session_state.view_mode = "list" if view_mode == "List View" else "detail"

    # Search box
    search_query = st.text_input(
        "Search transcripts", placeholder="Search by teacher or content..."
    )

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

# Main content
st.title("📚 Transcript Review Dashboard")

# Initialize the transcriber
transcriber = aai.Transcriber()

try:
    # Get list of transcripts
    response = transcriber.list_transcripts()

    # Process transcripts for display
    transcript_data = []
    for item in response.transcripts:
        try:
            status = (
                item.status.value if hasattr(item.status, "value") else str(item.status)
            )

            # Extract teacher name from audio URL if available
            audio_url = item.audio_url or ""
            teacher_name = "Unknown"  # Default value
            if "teacher=" in audio_url:
                teacher_name = audio_url.split("teacher=")[1].split("&")[0]

            transcript_data.append(
                {
                    "ID": item.id,
                    "Teacher": teacher_name,
                    "Status": status,
                    "Created": item.created,
                    "Duration": f"{item.audio_duration:.1f}s"
                    if hasattr(item, "audio_duration")
                    else "N/A",
                    "Audio URL": audio_url,
                    "Error": item.error
                    if hasattr(item, "error") and status == "error"
                    else "",
                }
            )
        except Exception as e:
            st.warning(f"Error processing transcript: {str(e)}")
            continue

    if not transcript_data:
        st.info("No transcripts found.")
    else:
        # Create display dataframe
        df = pd.DataFrame(transcript_data)
        df["Created"] = pd.to_datetime(df["Created"])

        # Apply filters
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            df = df[
                (df["Created"].dt.date >= start_date)
                & (df["Created"].dt.date <= end_date)
            ]

        # Apply search filter
        if search_query:
            search_mask = df["Teacher"].str.contains(search_query, case=False, na=False)
            df = df[search_mask]

        # Apply status filter
        if status_filter:
            df = df[df["Status"].str.lower().isin([s.lower() for s in status_filter])]

        # Format dates
        df["Created"] = df["Created"].dt.strftime("%Y-%m-%d %H:%M:%S")

        if st.session_state.view_mode == "detail":
            # Detail View
            selected_id = st.selectbox(
                "Select Transcript",
                options=df["ID"].tolist(),
                format_func=lambda x: f"{df[df['ID'] == x]['Teacher'].iloc[0]} - {df[df['ID'] == x]['Created'].iloc[0]}",
            )

            if selected_id:
                try:
                    transcript = aai.Transcript.get_by_id(selected_id)

                    if transcript.status == aai.TranscriptStatus.completed:
                        # Debug expander for full transcript object
                        with st.expander(
                            "🔍 Debug: Full Transcript Object", expanded=False
                        ):
                            st.json(
                                {
                                    "id": transcript.id,
                                    "status": str(transcript.status),
                                    "text": transcript.text,
                                    "words": [
                                        {
                                            "text": w.text,
                                            "start": w.start,
                                            "end": w.end,
                                            "confidence": w.confidence,
                                            "speaker": w.speaker,
                                        }
                                        for w in (transcript.words or [])
                                    ],
                                    "utterances": [
                                        {
                                            "text": u.text,
                                            "start": u.start,
                                            "end": u.end,
                                            "confidence": u.confidence,
                                            "speaker": u.speaker,
                                        }
                                        for u in (transcript.utterances or [])
                                    ],
                                    "audio_url": transcript.audio_url,
                                    "audio_duration": transcript.audio_duration,
                                    "confidence": getattr(
                                        transcript, "confidence", None
                                    ),
                                    # Optional attributes
                                    "language": {
                                        "code": getattr(
                                            transcript, "language_code", None
                                        ),
                                        "model": getattr(
                                            transcript, "language_model", None
                                        ),
                                        "acoustic_model": getattr(
                                            transcript, "acoustic_model", None
                                        ),
                                        "speech_model": getattr(
                                            transcript, "speech_model", None
                                        ),
                                    },
                                    # Analysis results
                                    "analysis": {
                                        "sentiment": getattr(
                                            transcript,
                                            "sentiment_analysis_results",
                                            None,
                                        ),
                                        "iab_categories": getattr(
                                            transcript, "iab_categories_results", None
                                        ),
                                        "content_safety": getattr(
                                            transcript, "content_safety_labels", None
                                        ),
                                        "chapters": getattr(
                                            transcript, "chapters", None
                                        ),
                                    },
                                }
                            )

                        # Top-level metrics
                        st.header("📊 Transcript Overview")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1:
                            st.metric(
                                "Teacher",
                                df[df["ID"] == selected_id]["Teacher"].iloc[0],
                            )
                        with col2:
                            st.metric(
                                "Duration",
                                f"{transcript.audio_duration:.1f}s"
                                if transcript.audio_duration
                                else "N/A",
                            )
                        with col3:
                            st.metric(
                                "Words",
                                len(transcript.words) if transcript.words else 0,
                            )
                        with col4:
                            st.metric(
                                "Speakers",
                                len(set(w.speaker for w in transcript.words))
                                if transcript.words
                                else 0,
                            )
                        with col5:
                            st.metric(
                                "Avg Words/Min",
                                f"{(len(transcript.words or []) / (transcript.audio_duration or 1) * 60):.1f}"
                                if transcript.words and transcript.audio_duration
                                else "N/A",
                            )

                        # Tabs for different analysis views
                        analysis_tab1, analysis_tab2, analysis_tab3, analysis_tab4 = (
                            st.tabs(
                                [
                                    "📝 Transcript Analysis",
                                    "👥 Speaker Analysis",
                                    "⏱️ Timeline",
                                    "💭 Feedback",
                                ]
                            )
                        )

                        with analysis_tab1:
                            # Word frequency analysis
                            if transcript.words:
                                word_freq = pd.Series(
                                    " ".join([w.text for w in transcript.words])
                                    .lower()
                                    .split()
                                ).value_counts()
                                common_words = word_freq.head(20)

                                st.subheader("📊 Word Frequency Analysis")
                                fig = px.bar(
                                    x=common_words.index,
                                    y=common_words.values,
                                    labels={"x": "Word", "y": "Frequency"},
                                    title="Most Common Words",
                                )
                                st.plotly_chart(fig, use_container_width=True)

                            # Full transcript with highlights
                            st.subheader("📜 Full Transcript")
                            st.text_area(
                                "Transcript Text",
                                transcript.text if transcript.text else "",
                                height=300,
                                disabled=True,
                            )

                        with analysis_tab2:
                            if transcript.utterances:
                                # Speaker statistics
                                st.subheader("👥 Speaker Analysis")
                                speaker_stats = {}
                                for utterance in transcript.utterances:
                                    if utterance.speaker not in speaker_stats:
                                        speaker_stats[utterance.speaker] = {
                                            "word_count": len(utterance.text.split()),
                                            "duration": (
                                                utterance.end - utterance.start
                                            )
                                            / 1000,
                                            "turns": 1,
                                        }
                                    else:
                                        speaker_stats[utterance.speaker][
                                            "word_count"
                                        ] += len(utterance.text.split())
                                        speaker_stats[utterance.speaker][
                                            "duration"
                                        ] += (utterance.end - utterance.start) / 1000
                                        speaker_stats[utterance.speaker]["turns"] += 1

                                # Create speaker statistics table
                                stats_df = pd.DataFrame.from_dict(
                                    speaker_stats, orient="index"
                                )
                                stats_df["words_per_minute"] = stats_df[
                                    "word_count"
                                ] / (stats_df["duration"] / 60)
                                stats_df = stats_df.round(2)

                                # Display speaker statistics
                                st.dataframe(
                                    stats_df,
                                    column_config={
                                        "word_count": "Total Words",
                                        "duration": "Speaking Time (s)",
                                        "turns": "Speaking Turns",
                                        "words_per_minute": "Words per Minute",
                                    },
                                )

                                # Speaker timeline visualization
                                st.subheader("🎯 Speaker Timeline")
                                fig = go.Figure()
                                colors = px.colors.qualitative.Set3
                                for i, utterance in enumerate(transcript.utterances):
                                    # Safely extract speaker number, defaulting to index if parsing fails
                                    try:
                                        speaker_idx = (
                                            int(utterance.speaker.split()[-1]) - 1
                                            if utterance.speaker
                                            else i
                                        )
                                    except (AttributeError, ValueError, IndexError):
                                        speaker_idx = i

                                    color = colors[speaker_idx % len(colors)]
                                    fig.add_trace(
                                        go.Scatter(
                                            x=[
                                                utterance.start / 1000,
                                                utterance.end / 1000,
                                            ],
                                            y=[speaker_idx, speaker_idx],
                                            mode="lines",
                                            name=f"Speaker {utterance.speaker or f'Unknown {i + 1}'}",
                                            line=dict(color=color, width=10),
                                            showlegend=True,
                                        )
                                    )
                                fig.update_layout(
                                    title="Speaker Timeline",
                                    xaxis_title="Time (seconds)",
                                    yaxis_title="Speaker",
                                    showlegend=True,
                                )
                                st.plotly_chart(fig, use_container_width=True)

                        with analysis_tab3:
                            if transcript.utterances:
                                st.subheader("⏱️ Conversation Flow")
                                # Create timeline of utterances
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

                                # Display timeline
                                fig = px.timeline(
                                    timeline_df,
                                    x_start="Start",
                                    x_end="End",
                                    y="Speaker",
                                    color="Speaker",
                                    hover_data=["Text", "Duration"],
                                    title="Conversation Timeline",
                                )
                                fig.update_layout(
                                    xaxis_title="Time (seconds)", yaxis_title="Speaker"
                                )
                                st.plotly_chart(fig, use_container_width=True)

                        with analysis_tab4:
                            # Feedback and annotations section
                            st.subheader("💭 Feedback History")

                            # Initialize annotations if needed
                            if selected_id not in st.session_state.annotations:
                                st.session_state.annotations[selected_id] = []

                            # Add new feedback
                            with st.expander("✍️ Add New Feedback", expanded=True):
                                feedback_text = st.text_area(
                                    "Feedback",
                                    placeholder="Enter your feedback here...",
                                    key="new_feedback",
                                )

                                feedback_type = st.selectbox(
                                    "Feedback Type",
                                    [
                                        "General",
                                        "Questioning Technique",
                                        "Student Engagement",
                                        "Pacing",
                                        "Content Delivery",
                                    ],
                                )

                                if st.button("Save Feedback"):
                                    if feedback_text:
                                        st.session_state.annotations[
                                            selected_id
                                        ].append(
                                            {
                                                "timestamp": datetime.now().timestamp(),
                                                "type": feedback_type,
                                                "feedback": feedback_text,
                                                "created": datetime.now().isoformat(),
                                            }
                                        )
                                        st.success("Feedback saved!")

                            # Display existing feedback
                            if st.session_state.annotations[selected_id]:
                                for annotation in sorted(
                                    st.session_state.annotations[selected_id],
                                    key=lambda x: x["created"],
                                    reverse=True,
                                ):
                                    with st.expander(
                                        f"{annotation['type']} - {annotation['created']}"
                                    ):
                                        st.write(annotation["feedback"])

                except Exception as e:
                    st.error(f"Error loading transcript details: {str(e)}")

        else:
            # List View
            tab1, tab2, tab3 = st.tabs(
                ["📋 All Transcripts", "📝 Review & Annotate", "❌ Error Details"]
            )

            with tab1:
                if len(df) == 0:
                    st.info("No transcripts match the selected filters.")
                else:
                    # Display table with transcripts
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "ID": st.column_config.TextColumn("ID", width="medium"),
                            "Teacher": st.column_config.TextColumn(
                                "Teacher", width="medium"
                            ),
                            "Status": st.column_config.TextColumn(
                                "Status", width="small"
                            ),
                            "Created": st.column_config.TextColumn(
                                "Created", width="medium"
                            ),
                            "Duration": st.column_config.TextColumn(
                                "Duration", width="small"
                            ),
                            "Audio URL": st.column_config.LinkColumn("Audio URL"),
                            "Error": st.column_config.TextColumn(
                                "Error", width="large"
                            ),
                        },
                    )

            with tab2:
                # Transcript review and annotation section
                selected_id = st.selectbox(
                    "Select Transcript to Review",
                    options=df["ID"].tolist(),
                    format_func=lambda x: f"{df[df['ID'] == x]['Teacher'].iloc[0]} - {df[df['ID'] == x]['Created'].iloc[0]}",
                    key="transcript_selector",
                )

                if selected_id:
                    try:
                        transcript = aai.Transcript.get_by_id(selected_id)

                        if transcript.status == aai.TranscriptStatus.completed:
                            # Display transcript info
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(
                                    "Teacher",
                                    df[df["ID"] == selected_id]["Teacher"].iloc[0],
                                )
                            with col2:
                                st.metric(
                                    "Duration",
                                    f"{transcript.audio_duration:.1f}s"
                                    if transcript.audio_duration
                                    else "N/A",
                                )
                            with col3:
                                st.metric(
                                    "Words",
                                    len(transcript.words) if transcript.words else 0,
                                )
                            with col4:
                                st.metric(
                                    "Speakers",
                                    len(set(w.speaker for w in transcript.words))
                                    if transcript.words
                                    else 0,
                                )

                            # Initialize annotations for this transcript
                            if selected_id not in st.session_state.annotations:
                                st.session_state.annotations[selected_id] = []

                            # Display utterances with annotation capability
                            st.subheader("Transcript with Annotations")

                            if transcript.utterances:
                                for idx, utterance in enumerate(transcript.utterances):
                                    with st.expander(
                                        f"{utterance.start / 1000:.1f}s - Speaker {utterance.speaker}",
                                        expanded=True,
                                    ):
                                        st.write(utterance.text)

                                        # Annotation input for this utterance
                                        annotation_key = f"{selected_id}_{idx}"
                                        annotation = st.text_area(
                                            "Add feedback for this segment",
                                            key=annotation_key,
                                            help="Add instructional feedback, suggestions, or comments",
                                        )

                                        if annotation:
                                            if (
                                                annotation_key
                                                not in st.session_state.annotations[
                                                    selected_id
                                                ]
                                            ):
                                                st.session_state.annotations[
                                                    selected_id
                                                ].append(
                                                    {
                                                        "timestamp": utterance.start
                                                        / 1000,
                                                        "speaker": utterance.speaker,
                                                        "text": utterance.text,
                                                        "feedback": annotation,
                                                        "created": datetime.now().isoformat(),
                                                    }
                                                )

                            # Display all annotations for this transcript
                            if st.session_state.annotations[selected_id]:
                                st.subheader("📝 Feedback Summary")
                                for annotation in st.session_state.annotations[
                                    selected_id
                                ]:
                                    with st.expander(
                                        f"Feedback at {annotation['timestamp']:.1f}s"
                                    ):
                                        st.write("**Original:**")
                                        st.write(annotation["text"])
                                        st.write("**Feedback:**")
                                        st.write(annotation["feedback"])
                                        st.caption(f"Added on {annotation['created']}")

                    except Exception as e:
                        st.error(f"Error loading transcript: {str(e)}")

            with tab3:
                error_df = df[df["Status"] == "error"]
                if len(error_df) > 0:
                    st.dataframe(
                        error_df[["ID", "Teacher", "Created", "Error"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.success("No errors found!")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")
