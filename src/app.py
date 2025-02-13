import streamlit as st
from azure.identity import ClientSecretCredential
import os
import assemblyai as aai
from datetime import datetime, timezone, timedelta
from azure.storage.blob import BlobSasPermissions, generate_blob_sas, BlobServiceClient
from streamlit.runtime.uploaded_file_manager import UploadedFile
import json
import logging
import io
from dotenv import load_dotenv
import asyncio
from azure.data.tables import TableServiceClient, TableEntity

load_dotenv()

st.set_page_config(
    page_title="AI Transcripts for Coaching",
    page_icon="🎤",
    initial_sidebar_state="collapsed",
)

# Initialize AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Configure AssemblyAI transcription settings
transcription_config = aai.TranscriptionConfig(
    speech_model=aai.SpeechModel.best,
    iab_categories=True,
    auto_chapters=True,
    content_safety=True,
    auto_highlights=True,
    sentiment_analysis=True,
    speaker_labels=True,
    filter_profanity=True,
    language_detection=True,
).set_redact_pii(
    policies=[
        aai.PIIRedactionPolicy.medical_condition,
        aai.PIIRedactionPolicy.email_address,
        aai.PIIRedactionPolicy.phone_number,
        aai.PIIRedactionPolicy.banking_information,
        aai.PIIRedactionPolicy.credit_card_number,
        aai.PIIRedactionPolicy.credit_card_cvv,
        aai.PIIRedactionPolicy.date_of_birth,
        aai.PIIRedactionPolicy.person_name,
        aai.PIIRedactionPolicy.organization,
        aai.PIIRedactionPolicy.location,
    ],
    redact_audio=True,
    substitution=aai.PIISubstitutionPolicy.hash,
)


def get_azure_credential():
    """Get Azure credential using service principal."""
    try:
        # Get service principal credentials from environment
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            raise ValueError(
                "Missing required Azure credentials in environment variables"
            )

        # Create service principal credential
        credential = ClientSecretCredential(
            tenant_id=str(tenant_id),
            client_id=str(client_id),
            client_secret=str(client_secret),
        )

        # Test the credential
        credential.get_token("https://storage.azure.com/.default")
        logging.debug(
            "Successfully authenticated with Azure using service principal")
        return credential
    except Exception as e:
        logging.error(f"Error authenticating with Azure: {e}")
        raise e


# Get storage account name from environment
storage_account = os.getenv("AZURE_STORAGE_ACCOUNT", "classroomtranscripts")
if not storage_account:
    logging.warning(
        "Environment variable AZURE_STORAGE_ACCOUNT not found. Using default value 'classroomtranscripts'."
    )

try:
    # Get Azure credential
    credential = get_azure_credential()

    # Create BlobServiceClient
    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url, credential=credential)

    # Fixed container names
    uploads_container = "uploads"
    transcripts_container = "transcriptions"

    # Get container clients and create if they don't exist
    uploads_container_client = blob_service_client.get_container_client(
        uploads_container
    )
    transcripts_container_client = blob_service_client.get_container_client(
        transcripts_container
    )

    # Create containers if they don't exist
    try:
        uploads_container_client.get_container_properties()
    except Exception:
        st.info(f"Creating {uploads_container} container...")
        uploads_container_client = blob_service_client.create_container(
            uploads_container
        )

    try:
        transcripts_container_client.get_container_properties()
    except Exception:
        st.info(f"Creating {transcripts_container} container...")
        transcripts_container_client = blob_service_client.create_container(
            transcripts_container
        )

    # Create table service client and ensure TranscriptMappings table exists
    try:
        table_service_client = TableServiceClient.from_connection_string(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
        table_client = table_service_client.get_table_client(
            "TranscriptMappings")
        try:
            table_client.get_table_properties()
            logging.info("TranscriptMappings table exists")
        except Exception:
            st.info("Creating TranscriptMappings table...")
            table_service_client.create_table("TranscriptMappings")
            logging.info("Created TranscriptMappings table")
    except Exception as e:
        logging.error(f"Error setting up table storage: {e}")

except Exception as e:
    logging.error(f"Error connecting to Azure Storage: {e}")

logging.debug("Debug information:")
logging.debug(f"Account URL: {account_url}")
logging.debug(f"Upload Container: {uploads_container}")
logging.debug(f"Transcripts Container: {transcripts_container}")
logging.debug("Azure Identity: Using service principal authentication")

st.title("🎤 Classroom Transcripts")
if org_name := os.getenv('ORGANIZATION_NAME'):
    st.caption(f"Internal tool for testing by {org_name}.")

st.subheader("Upload a Class Recording")
st.write(
    "We'll generate a transcript and post it to Google Drive for you and your coach."
)


def upload_to_azure(file):
    try:
        # Create BlobClient for upload
        blob_client = uploads_container_client.get_blob_client(file.name)

        blob = blob_client.upload_blob(file, overwrite=True)

        # Verify the blob exists by trying to get its properties
        try:
            blob_client.get_blob_properties()
            return blob
        except Exception as e:
            logging.error(f"Error uploading to Azure: {e}")
            return False

    except Exception as e:
        logging.error(f"Error uploading to Azure: {e}")
        return False


async def submit_transcription(file: UploadedFile) -> aai.TranscriptStatus:
    try:
        transcriber = aai.Transcriber(config=transcription_config)
        file_bytes = io.BytesIO(file.getvalue())
        if file_bytes:
            logging.info(f"Starting transcription for file: {file.name}")
            transcript_future = transcriber.transcribe_async(file_bytes)

            # Check if we got immediate status
            if transcript_future.done():
                transcript = transcript_future.result()
                logging.info(
                    f"Got immediate transcription result for {file.name} with ID {transcript.id}")
                await store_mapping_in_table(file.name, transcript.id, transcript.audio_url)

                # Verify mapping was stored
                mapping = await get_transcript_mapping(file.name)
                if mapping:
                    logging.info(
                        f"Verified mapping for {file.name}: {mapping}")
                else:
                    logging.warning(
                        f"Could not verify mapping for {file.name}")

                return transcript.status

            # If not, wait briefly for completion
            try:
                await asyncio.wait_for(
                    asyncio.wrap_future(transcript_future), timeout=3
                )
            except asyncio.TimeoutError:
                st.info(
                    "This one might take a little longer - we'll post the transcript to Google Drive as soon as it's ready."
                )

            transcript = transcript_future.result()
            logging.info(
                f"Got delayed transcription result for {file.name} with ID {transcript.id}")
            await store_mapping_in_table(file.name, transcript.id, transcript.audio_url)

            # Verify mapping was stored
            mapping = await get_transcript_mapping(file.name)
            if mapping:
                logging.info(f"Verified mapping for {file.name}: {mapping}")
            else:
                logging.warning(f"Could not verify mapping for {file.name}")

            return transcript.status

        else:
            logging.error("File is empty: %s", file.name)
            st.error("File is empty. Is that the right file?")
            return aai.TranscriptStatus.error

    except Exception as e:
        logging.error(f"Error submitting transcription: {e}")
        st.error("We couldn't transcribe that file. Is that the right file?")
        st.expander("Error details").write(f"{e}")
        return aai.TranscriptStatus.error


async def store_mapping_in_table(blob_name, transcript_id, audio_url):
    try:
        table_service_client = TableServiceClient.from_connection_string(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
        table_client = table_service_client.get_table_client(
            "TranscriptMappings")

        entity = TableEntity()
        entity["PartitionKey"] = "AudioFiles"
        entity["RowKey"] = blob_name
        entity["transcriptId"] = transcript_id
        entity["audioUrl"] = audio_url
        entity["uploadTime"] = datetime.utcnow().isoformat()

        table_client.create_entity(entity=entity)
        logging.info(
            f"Stored mapping in table: {blob_name} -> {transcript_id}")

    except Exception as e:
        logging.error(f"Error storing mapping in table: {e}")

async def get_transcript_mapping(blob_name):
    """Retrieve transcript mapping for a given blob name."""
    try:
        table_service_client = TableServiceClient.from_connection_string(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
        table_client = table_service_client.get_table_client(
            "TranscriptMappings")

        try:
            entity = table_client.get_entity("AudioFiles", blob_name)
            return {
                "transcriptId": entity["transcriptId"],
                "audioUrl": entity["audioUrl"],
                "uploadTime": entity["uploadTime"]
            }
        except Exception as e:
            logging.warning(f"No mapping found for blob {blob_name}: {e}")
            return None

    except Exception as e:
        logging.error(f"Error retrieving mapping from table: {e}")
        return None


with st.container(border=True):
    uploaded_file = st.file_uploader(
        "Choose an audio file",
        type=[
            "3ga",
            "8svx",
            "aac",
            "ac3",
            "aif",
            "aiff",
            "alac",
            "amr",
            "ape",
            "au",
            "dss",
            "flac",
            "flv",
            "m4a",
            "m4b",
            "m4p",
            "m4r",
            "mp3",
            "mpga",
            "ogg",
            "oga",
            "mogg",
            "opus",
            "qcp",
            "tta",
            "voc",
            "wav",
            "wma",
            "wv",
        ],
    )


async def handle_upload(uploaded_file: UploadedFile):
    if upload_to_azure(uploaded_file):
        with st.spinner("Submitting for transcription..."):
            status = await submit_transcription(uploaded_file)
            logging.info(
                f"✅  '{uploaded_file.name}' submitted for transcription.")

            if status == aai.TranscriptStatus.processing:
                st.info(
                    "Transcription processing - you can close this window or upload another file"
                )
            elif status == aai.TranscriptStatus.completed:
                st.success(
                    "✅  Transcription complete! We'll post the transcript to Google Drive as soon as it's ready."
                )
            elif status == aai.TranscriptStatus.error:
                st.error("Upload failed - please try again.")
                logging.error(f"Transcription failed with status: {status}")
    else:
        st.error("Upload to storage failed - please try again")


if uploaded_file is not None:
    asyncio.run(handle_upload(uploaded_file))


if feedback_email := os.getenv('FEEDBACK_EMAIL'):
    st.caption(f"📧 Help and feedback: {feedback_email}")

with st.sidebar:
    if os.getenv('DEBUG'):
        st.write(st.experimental_user)
