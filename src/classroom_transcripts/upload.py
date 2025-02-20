import streamlit as st
import assemblyai as aai
import os
import logging
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from datetime import datetime
import asyncio
from classroom_transcripts.utils.transcript_mapping import create_upload_entity
from urllib.parse import quote
from classroom_transcripts.utils.table_client import get_table_client
from classroom_transcripts.utils.azure_storage import get_sas_url_for_audio_file_name

DEBUG = bool(st.secrets.get("DEBUG", False))
table_name = st.secrets.get("AZURE_STORAGE_TABLE_NAME", "TranscriptionMappings")
st.session_state["table_name"] = table_name


def get_azure_credential():
    """Get Azure credential using service principal."""
    try:
        # Get service principal credentials from environment
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            logging.error("Missing required Azure credentials in environment variables")
            st.error(
                "Missing Azure credentials. Please check your environment configuration."
            )
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
        logging.debug("Successfully authenticated with Azure using service principal")
        return credential
    except Exception as e:
        logging.error(f"Error authenticating with Azure: {e}", exc_info=True)
        # Try DefaultAzureCredential as fallback
        try:
            logging.debug("Attempting to use DefaultAzureCredential as fallback")
            credential = DefaultAzureCredential()
            credential.get_token("https://storage.azure.com/.default")
            logging.debug("Successfully authenticated using DefaultAzureCredential")
            return credential
        except Exception as default_error:
            logging.error(
                f"DefaultAzureCredential also failed: {default_error}", exc_info=True
            )
            raise ValueError(f"Failed to authenticate with Azure: {str(e)}")


# Initialize variables for logging
account_url = None
uploads_container = "uploads"
transcripts_container = "transcripts"
uploads_container_client = None
transcripts_container_client = None
storage_account_key = None

try:
    # Get Azure credential
    credential = get_azure_credential()
    logging.debug("Successfully obtained Azure credential")

    # Create BlobServiceClient
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT", "classroomtranscripts")
    if not storage_account:
        raise ValueError("AZURE_STORAGE_ACCOUNT environment variable is not set")

    account_url = f"https://{storage_account}.blob.core.windows.net"
    logging.debug(f"Connecting to storage account: {account_url}")
    blob_service_client = BlobServiceClient(account_url, credential=credential)
    logging.debug("Successfully created BlobServiceClient")

    # Get container clients and create if they don't exist
    uploads_container_client = blob_service_client.get_container_client(
        uploads_container
    )
    transcripts_container_client = blob_service_client.get_container_client(
        transcripts_container
    )
    logging.debug("Got container clients")

    # Create containers if they don't exist
    try:
        uploads_container_client.get_container_properties()
        logging.debug(f"Container {uploads_container} exists")
    except Exception as e:
        logging.debug(f"Creating {uploads_container} container... Error: {str(e)}")
        uploads_container_client = blob_service_client.create_container(
            uploads_container,
            enable_versioning=True,  # Enable versioning
        )

    try:
        transcripts_container_client.get_container_properties()
        logging.debug(f"Container {transcripts_container} exists")
    except Exception as e:
        logging.debug(f"Creating {transcripts_container} container... Error: {str(e)}")
        transcripts_container_client = blob_service_client.create_container(
            transcripts_container
        )

except ValueError as ve:
    logging.error(f"Configuration error: {str(ve)}", exc_info=True)
    st.error(str(ve))
except Exception as e:
    logging.error(f"Error connecting to Azure Storage: {e}", exc_info=True)
    st.error("Could not connect to storage. Please try again later or contact support.")

# Log debug information after variables are defined
logging.debug("Debug information:")
logging.debug(f"Account URL: {account_url}")
logging.debug(f"Upload Container: {uploads_container}")
logging.debug(f"Transcripts Container: {transcripts_container}")
logging.debug("Azure Identity: Using service principal authentication")

# Initialize AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")


st.title("🎤 Classroom Transcripts")
if org_name := os.getenv("ORGANIZATION_NAME"):
    st.caption(f"Internal tool for testing by {org_name}.")


def generate_unique_blob_name(original_filename: str) -> str:
    """Generate a unique blob name using timestamp and original filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Remove any potentially problematic characters from original filename
    clean_filename = "".join(c for c in original_filename if c.isalnum() or c in "._- ")
    return f"{timestamp}_{clean_filename}"


def upload_to_azure(file):
    try:
        if uploads_container_client is None:
            logging.error("Azure Storage not initialized")
            st.error(
                "Storage connection not initialized. Please refresh the page and try again."
            )
            return False

        # Generate unique blob name
        unique_blob_name = generate_unique_blob_name(file.name)
        logging.debug(f"Generated unique blob name: {unique_blob_name}")

        blob_client = uploads_container_client.get_blob_client(unique_blob_name)
        logging.debug(f"Created blob client for {unique_blob_name}")

        # Upload as block blob
        file.seek(0)
        try:
            blob_client.upload_blob(
                file,
                overwrite=False,  # No need for overwrite with unique names
            )
            logging.debug(f"Successfully uploaded blob: {unique_blob_name}")

            # Get blob properties to ensure we have all metadata
            properties = blob_client.get_blob_properties()

            return {
                "name": unique_blob_name,
                "original_name": file.name,
                "etag": properties.etag,
                "last_modified": properties.last_modified.isoformat(),
                "size": properties.size,
                "url": blob_client.url,
            }

        except Exception as upload_error:
            logging.error(f"Failed to upload blob: {str(upload_error)}", exc_info=True)
            st.error("Failed to upload file. Please try again.")
            return False

    except Exception as e:
        logging.error(f"Error uploading to Azure: {str(e)}", exc_info=True)
        st.error(
            "Upload failed. Please try again or contact support if the problem persists."
        )
        return False


async def submit_transcription(url: str, config: aai.TranscriptionConfig) -> dict:
    try:
        # Get the callback URL from environment
        callback_url = os.getenv("ASSEMBLYAI_CALLBACK_URL")

        # Configure transcription with webhook if available
        if callback_url:
            config = config.set_webhook(callback_url)
            logging.info(f"Using callback URL: {callback_url}")

        transcriber = aai.Transcriber(config=config)

        transcript = transcriber.submit(data=url, config=config)
        return {"id": transcript.id, "file_url": url, "status": transcript.status}

    except Exception as e:
        logging.error(f"Error submitting transcription: {e}")
        st.error("We couldn't transcribe that file. Is that the right file?")
        st.expander("Error details").write(f"{e}")
        return {"id": "error", "file_url": url, "status": "error", "error": str(e)}


async def store_mapping_in_table(
    blob_dict: dict, transcript_dict: dict, class_name: str, description: str
):
    """Store the mapping between uploaded file and its transcript."""
    try:
        table_client = get_table_client(table_name)
        # Get user information
        user = st.experimental_user

        entity = create_upload_entity(
            blob_name=blob_dict["name"],
            original_name=blob_dict["original_name"],
            transcript_id=transcript_dict["id"],
        )

        # Add additional metadata
        entity["etag"] = blob_dict["etag"]
        entity["lastModified"] = blob_dict["last_modified"]
        entity["blobSize"] = blob_dict["size"]
        entity["audioUrl"] = transcript_dict["file_url"]

        # Add user information
        entity["uploaderEmail"] = user.email
        entity["uploaderName"] = user.name
        entity["uploaderEmailVerified"] = getattr(user, "email_verified", False)
        entity["uploaderExternalId"] = getattr(user, "external_id", None)  # sid

        # Add class name and description
        entity["className"] = class_name
        entity["description"] = description

        table_client.create_entity(entity=entity)
        logging.info(f"Stored mapping: {blob_dict['name']} -> {transcript_dict['id']}")

    except Exception as e:
        logging.error(f"Error storing mapping: {e}")
        raise


def handle_successful_upload(
    upload_result: dict, transcript: dict, class_name: str
) -> None:
    """Handle successful upload and transcription submission.

    Args:
        upload_result: Dictionary containing upload details (name, original_name, size)
        transcript: Dictionary containing transcript details (id)
        class_name: Name of the class for the recording
    """
    # Validate required keys
    required_keys = {"name", "original_name", "size"}
    if not all(key in upload_result for key in required_keys):
        logging.error(f"Missing required keys in upload_result: {upload_result}")
        st.error("Invalid upload result format")
        return

    if "id" not in transcript:
        logging.error(f"Missing id in transcript result: {transcript}")
        st.error("Invalid transcript format")
        return

    # Store the upload info in session state
    if "recent_uploads" not in st.session_state:
        st.session_state.recent_uploads = []

    st.session_state.recent_uploads.append(
        {
            "blob_name": upload_result["name"],
            "transcript_id": transcript["id"],
            "timestamp": datetime.now().isoformat(),
        }
    )

    # Show confirmation with details
    st.success("✅ File uploaded successfully!")

    with st.expander("Submission Details", expanded=True):
        st.markdown(f"""
        ### 📝 Transcript Details
        - **Class**: {class_name}
        - **File**: {upload_result["original_name"]}
        - **Size**: {upload_result["size"] / 1024 / 1024:.1f} MB
        - **Transcript ID**: `{transcript["id"]}`
        
        Your file is being processed. You can:
        - Upload another recording
        - View your transcripts in the sidebar menu
        """)

    logging.info(
        f"'{upload_result['name']}' (original: '{upload_result['original_name']}') "
        f"submitted for transcription"
    )


if st.experimental_user.get("is_logged_in"):
    st.subheader("Upload a Class Recording", divider=True)
    st.write("We'll generate a transcript and post it for you and your coach.")

    if uploaded_file := st.file_uploader(
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
    ):
        # Get filename without extension for default class name
        default_class_name = os.path.splitext(uploaded_file.name)[0]

        # Initialize session state
        if "speaker_count" not in st.session_state:
            st.session_state.speaker_count = 2
        if "use_speaker_count" not in st.session_state:
            st.session_state.use_speaker_count = True
        if "description" not in st.session_state:
            st.session_state.description = ""

        # Create a container with a border for the form-like interface
        with st.container(border=True):
            st.write("### Add Details")

            # Class name input
            st.session_state.class_name = st.text_input(
                "Class Name", key="class_name_input", value=default_class_name
            )

            # Speaker settings section
            st.toggle(
                "Set expected number of speakers",
                value=st.session_state.use_speaker_count,
                key="use_speaker_count",
                help="""If you know how many speakers are in the recording, 
                set the expected number of speakers. The default is 2, which will
                work for most recordings, with Speaker A being teacher and Speaker B being any student.""",
            )

            if st.session_state.use_speaker_count:
                st.slider(
                    "Expected Number of Speakers",
                    min_value=1,
                    max_value=10,
                    value=st.session_state.speaker_count,
                    key="speaker_count",
                    help="Estimate how many different speakers are in this recording",
                )

            # Description input
            st.text_area(
                "Description (optional)",
                value=st.session_state.description,
                key="description",
                help="Optional: Add any notes about this recording that might be helpful for your coach.",
            )

            # Submit button
            if st.button("Submit", type="primary", use_container_width=True):
                if not st.session_state.class_name:
                    st.error("Please enter a class name")
                else:
                    if upload_result := upload_to_azure(uploaded_file):
                        blob_sas_url = get_sas_url_for_audio_file_name(
                            upload_result["name"]
                        )

                        # Create new config with selected speaker count
                        config = (
                            aai.TranscriptionConfig(
                                speaker_labels=True,
                                speakers_expected=st.session_state.speaker_count
                                if st.session_state.use_speaker_count
                                else None,
                                speech_model=aai.SpeechModel.best,
                                iab_categories=True,
                                auto_chapters=True,
                                content_safety=True,
                                auto_highlights=False,
                                sentiment_analysis=True,
                                filter_profanity=True,
                                language_detection=False,
                                language_code="en",
                            )
                            .set_redact_pii(
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
                            .set_webhook(
                                os.getenv("ASSEMBLYAI_CALLBACK_URL"),
                                "X-Transcript-Webhook-Secret",
                                st.secrets.get("ASSEMBLYAI_WEBHOOK_AUTH_HEADER_VALUE"),
                            )
                        )

                        safe_url = quote(blob_sas_url, safe=":/?&=%")
                        markdown_link = (
                            f"[{upload_result['original_name']}]({safe_url})"
                        )
                        st.success(f"Uploaded file to Azure: {markdown_link}")

                        transcript = asyncio.run(submit_transcription(safe_url, config))
                        if transcript["status"] == "queued":
                            # Store mapping in table
                            asyncio.run(
                                store_mapping_in_table(
                                    upload_result,
                                    transcript,
                                    st.session_state.class_name,
                                    st.session_state.description,
                                )
                            )

                            # Pass class_name to the handler function
                            handle_successful_upload(
                                upload_result, transcript, st.session_state.class_name
                            )

                        else:
                            st.error(
                                "Transcription submission failed - please try again."
                            )
                            logging.error(
                                f"Transcription failed with status: {transcript['status']}"
                            )
                    else:
                        st.error("Upload to storage failed - please try again")

else:
    provider = os.getenv("STREAMLIT_AUTH_PROVIDER", None)
    if DEBUG:
        st.write(f"Provider: {provider}")
    if st.button(
        "Sign In", key="sign_in_button", use_container_width=True, type="primary"
    ):
        st.login()


if feedback_email := os.getenv("FEEDBACK_EMAIL"):
    st.caption(f"📧 Help and feedback: {feedback_email}")
