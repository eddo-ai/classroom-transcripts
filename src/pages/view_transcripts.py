import os
import assemblyai
import pandas as pd
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.data.tables import TableServiceClient
import streamlit as st
from datetime import datetime


def get_transcript_status(transcript_id: str) -> dict:
    """Get transcript status from AssemblyAI."""
    try:
        transcript = assemblyai.Transcript.get_by_id(transcript_id)
        return {
            "status": transcript.status,
            "words": transcript.words or [],
            "confidence": transcript.confidence,
            "audio_duration": transcript.audio_duration,
            "error": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "words": [],
            "confidence": None,
            "audio_duration": None,
            "error": str(e),
        }


def load_transcript_mappings():
    """Load all entries from the TranscriptMappings table."""
    load_dotenv()

    # Get environment variables
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    assemblyai_key = os.getenv("ASSEMBLYAI_API_KEY")

    if not account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT environment variable is required")
    if not assemblyai_key:
        raise ValueError("ASSEMBLYAI_API_KEY environment variable is required")

    try:
        # Connect to table storage
        with st.spinner("Connecting to Azure Table Storage..."):
            if connection_string:
                table_service = TableServiceClient.from_connection_string(
                    connection_string
                )
            else:
                credential = DefaultAzureCredential()
                if all(
                    os.getenv(key)
                    for key in [
                        "AZURE_TENANT_ID",
                        "AZURE_CLIENT_ID",
                        "AZURE_CLIENT_SECRET",
                    ]
                ):
                    # Get environment variables and assert they are not None
                    tenant_id = os.getenv("AZURE_TENANT_ID")
                    client_id = os.getenv("AZURE_CLIENT_ID")
                    client_secret = os.getenv("AZURE_CLIENT_SECRET")

                    assert tenant_id is not None
                    assert client_id is not None
                    assert client_secret is not None

                    credential = ClientSecretCredential(
                        tenant_id=tenant_id,
                        client_id=client_id,
                        client_secret=client_secret,
                    )

                table_service = TableServiceClient(
                    endpoint=f"https://{account_name}.table.core.windows.net",
                    credential=credential,
                )

        # Get the table client and fetch entities
        with st.spinner("Fetching transcript mappings..."):
            table_client = table_service.get_table_client("TranscriptMappings")
            entities = list(table_client.list_entities())
            st.toast(f"Found {len(entities)} transcript mappings")

        # Process entities
        processed_entities = []
        with st.spinner("Checking transcript statuses..."):
            success_count = 0
            error_count = 0

            for entity in entities:
                # Get transcript ID and blob info
                blob_name = entity.get("BlobName", entity["PartitionKey"])
                transcript_id = entity.get("transcriptId")
                audio_url = entity.get("audioUrl")
                container = entity.get("container", "audio-files")

                # Construct Azure blob URL
                azure_blob_url = (
                    f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"
                    if blob_name and container
                    else None
                )

                if not transcript_id:
                    error_count += 1
                    api_status = {
                        "status": "unknown",
                        "words": [],
                        "confidence": None,
                        "audio_duration": None,
                    }
                else:
                    api_status = get_transcript_status(transcript_id)
                    success = api_status["error"] is None
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

                # Convert datetime objects to strings
                created = entity.get("uploadTime")
                if isinstance(created, datetime):
                    created = created.strftime("%Y-%m-%d %H:%M:%S")

                timestamp = entity.get("Timestamp")
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")

                entry = {
                    "Container": container,
                    "Blob Name": blob_name,
                    "Azure URL": azure_blob_url or "N/A",
                    "AssemblyAI URL": audio_url or "N/A",
                    "AssemblyAI ID": transcript_id or "Not assigned",
                    "Status": api_status["status"],
                    "Words": len(api_status["words"]),
                    "Confidence": f"{api_status['confidence']:.1%}"
                    if api_status["confidence"]
                    else "N/A",
                    "Duration": f"{api_status['audio_duration']:.1f}s"
                    if api_status["audio_duration"]
                    else "N/A",
                    "Created": created,
                    "Last Updated": timestamp,
                }

                # Add raw data as a string representation
                entry["Raw Data"] = str(dict(entity))
                processed_entities.append(entry)

            # Show final status
            if success_count > 0:
                st.toast(
                    f"Successfully checked status of {success_count} transcripts",
                )

        return pd.DataFrame(processed_entities)

    except Exception as e:
        st.error(f"Error accessing table storage: {str(e)}")
        st.toast("Failed to load transcript mappings", icon="❌")
        return pd.DataFrame()


def main():
    """Main function for the transcript mappings view."""
    st.title("mapping madness")

    # Add prominent refresh button in the header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header("Audio File Transcripts")
    with col2:
        refresh = st.button("🔄 Refresh", type="primary", use_container_width=True)

    # Load data
    if "data" not in st.session_state or refresh:
        with st.spinner("Refreshing data..."):
            st.session_state.data = load_transcript_mappings()
            if not st.session_state.data.empty:
                st.toast("Data refresh complete", icon="✅")

    # Display data
    st.dataframe(st.session_state.data)


if __name__ == "__main__":
    main()
