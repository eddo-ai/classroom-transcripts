import os
import json
import logging
import azure.functions as func
import assemblyai as aai
from assemblyai import Transcript
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from datetime import datetime, timedelta
import requests


def get_azure_credential():
    """Get the appropriate Azure credential based on the environment."""
    try:
        # First try Managed Identity
        credential = ManagedIdentityCredential()
        # Test the credential
        credential.get_token("https://storage.azure.com/.default")
        logging.info("Using Managed Identity credential")
        return credential
    except Exception as e:
        logging.info(f"Managed Identity not available: {str(e)}")
        try:
            # Fall back to DefaultAzureCredential
            credential = DefaultAzureCredential()
            credential.get_token("https://storage.azure.com/.default")
            logging.info("Using Default Azure credential")
            return credential
        except Exception as e:
            logging.error(f"Failed to get Azure credential: {str(e)}")
            raise


def submit_transcription(myblob: func.InputStream):
    """Submit an audio file for transcription when uploaded to blob storage."""
    logging.info(f"Python blob trigger function processed blob: {myblob.name}")
    logging.info(f"Blob URI: {myblob.uri}")

    try:
        # Set AssemblyAI API key
        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")
        logging.info("AssemblyAI API key found")
        aai.settings.api_key = api_key

        # Check if we're running locally
        storage_conn = os.getenv("AzureWebJobsStorage", "")
        is_local = "UseDevelopmentStorage=true" in storage_conn

        if is_local:
            # Use connection string for local development
            connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if not connection_string:
                raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found")
            blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
            logging.info("Connected to local storage using connection string")
        else:
            # Use Azure AD auth for production
            credential = get_azure_credential()
            storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
            if not storage_account:
                raise ValueError("AZURE_STORAGE_ACCOUNT not found")
            account_url = f"https://{storage_account}.blob.core.windows.net"
            blob_service_client = BlobServiceClient(account_url, credential=credential)
            logging.info(f"Connected to storage account: {account_url}")

        # Get the uploads container client
        uploads_container = blob_service_client.get_container_client("uploads")
        if not myblob.name:
            raise ValueError("Blob name is required")

        # Clean up blob name - remove any 'uploads/' prefix if present
        clean_blob_name = myblob.name.replace("uploads/", "", 1)
        blob_client = uploads_container.get_blob_client(clean_blob_name)

        # Get the audio URL
        if is_local:
            # For local development, use the blob URL directly
            audio_url = blob_client.url
            logging.info(f"Using local blob URL: {audio_url}")
        else:
            # Generate SAS token for the blob with read permission
            logging.info(f"\n=== Generating SAS Token ===")
            logging.info(f"Blob: {clean_blob_name}")
            try:
                # Get user delegation key
                user_delegation_key = blob_service_client.get_user_delegation_key(
                    key_start_time=datetime.utcnow(),
                    key_expiry_time=datetime.utcnow() + timedelta(hours=2),
                )

                sas_token = generate_blob_sas(
                    account_name=storage_account,
                    container_name="uploads",
                    blob_name=clean_blob_name,
                    user_delegation_key=user_delegation_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.utcnow() + timedelta(hours=1),
                )
                audio_url = f"{blob_client.url}?{sas_token}"

                # Test if blob exists and is accessible
                blob_properties = blob_client.get_blob_properties()
                logging.info("\n=== Blob Properties ===")
                logging.info(
                    f"Content Type: {blob_properties.content_settings.content_type}"
                )
                logging.info(f"Size: {blob_properties.size:,} bytes")
                logging.info(f"Created: {blob_properties.creation_time}")
                logging.info(f"Base URL: {blob_client.url}")
                logging.info("SAS URL generated successfully (token redacted)")

                # Verify SAS URL works
                logging.info("\n=== Testing SAS URL ===")
                response = requests.head(audio_url)
                logging.info(f"Status Code: {response.status_code}")
                logging.info(
                    f"Content Type: {response.headers.get('content-type', 'N/A')}"
                )
                logging.info(
                    f"Content Length: {response.headers.get('content-length', 'N/A'):,} bytes"
                )

            except Exception as e:
                logging.error(f"\n❌ Error generating/testing SAS token:")
                logging.error(str(e))
                raise

        # Construct webhook URL using WEBSITE_HOSTNAME
        website_hostname = os.getenv("WEBSITE_HOSTNAME", "localhost:7071")
        webhook_url = (
            f"http://{website_hostname}/api/webhook"
            if "localhost" in website_hostname
            else f"https://{website_hostname}/api/webhook"
        )
        logging.info(f"\n=== Webhook Configuration ===")
        logging.info(f"URL: {webhook_url}")
        logging.info(f"Auth Header: x-functions-key")

        # Use the AssemblyAI API to transcribe the audio file
        logging.info("\n=== Submitting to AssemblyAI ===")
        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(
            speaker_labels=True,
            webhook_url=webhook_url,
            webhook_auth_header_name="x-functions-key",
            webhook_auth_header_value=os.getenv("AZURE_FUNCTION_KEY", ""),
        )
        logging.info("Configuration:")
        logging.info(f"- Speaker Labels: Enabled")
        logging.info(f"- Webhook URL: {webhook_url}")
        logging.info("- Webhook Auth: Configured")

        transcript = transcriber.submit(audio_url, config)
        logging.info("\n=== AssemblyAI Response ===")
        logging.info(f"Transcript ID: {transcript.id}")
        logging.info(f"Status: {transcript.status}")
        if hasattr(transcript, "error") and transcript.error:
            logging.error(f"❌ Error: {transcript.error}")

    except Exception as e:
        logging.error(f"Error submitting transcription: {str(e)}")
        raise


def handle_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """Handle the webhook callback from AssemblyAI."""
    logging.info("Received webhook from AssemblyAI")
    logging.info(f"Request URL: {req.url}")
    logging.info(f"Request headers: {dict(req.headers)}")

    try:
        # Get the transcript from the webhook
        webhook_body = req.get_json()
        logging.info(f"Webhook body: {webhook_body}")

        if webhook_body.get("status") != "completed":
            logging.info(f"Received non-completed status: {webhook_body.get('status')}")
            return func.HttpResponse(
                status_code=200
            )  # Acknowledge non-completed webhooks

        transcript_id = webhook_body.get("transcript_id")
        logging.info(f"Processing transcript ID: {transcript_id}")

        # Retrieve the complete transcript from AssemblyAI
        transcript = Transcript.get_by_id(transcript_id)
        logging.info("Retrieved transcript from AssemblyAI")

        # Format the transcript content
        formatted_transcript = []
        if hasattr(transcript, "utterances") and transcript.utterances:
            logging.info("Transcript content:")
            for utterance in transcript.utterances:
                start_time = int(utterance.start / 1000)  # Convert to seconds
                hours = start_time // 3600
                minutes = (start_time % 3600) // 60
                seconds = start_time % 60
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                # Log each utterance
                logging.info(
                    f"{timestamp} - Speaker {utterance.speaker}: {utterance.text}"
                )

                # Format for storage
                formatted_transcript.append(
                    {
                        "timestamp": timestamp,
                        "speaker": f"Speaker {utterance.speaker}",
                        "text": utterance.text,
                    }
                )

        # Prepare transcript data
        transcript_data = {
            "transcript_id": transcript_id,
            "status": "completed",
            "utterances": formatted_transcript,
            "metadata": {
                "audio_url": transcript.audio_url,
                "duration": transcript.audio_duration,
            },
        }

        # Store the transcript
        storage_conn = os.getenv("AzureWebJobsStorage", "")
        is_local = "UseDevelopmentStorage=true" in storage_conn

        if is_local:
            # Local development - store in local directory
            try:
                os.makedirs("transcripts", exist_ok=True)
                output_path = f"transcripts/transcript_{transcript_id}.json"
                with open(output_path, "w") as f:
                    json.dump(transcript_data, f, indent=2)
                logging.info(f"Stored transcript JSON locally at: {output_path}")
            except Exception as e:
                logging.error(f"Error storing local transcript: {str(e)}")

        # Always store in Azure Storage (both local and production)
        try:
            if is_local:
                # Use connection string for local development
                connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
                if not connection_string:
                    raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found")
                blob_service_client = BlobServiceClient.from_connection_string(
                    connection_string
                )
                logging.info("Connected to local storage using connection string")
            else:
                # Use Azure AD auth for production
                storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
                if not storage_account:
                    raise ValueError("AZURE_STORAGE_ACCOUNT not found")
                credential = get_azure_credential()
                account_url = f"https://{storage_account}.blob.core.windows.net"
                blob_service_client = BlobServiceClient(
                    account_url, credential=credential
                )
                logging.info(f"Connected to storage account: {account_url}")

            # Get or create transcriptions container
            container_client = blob_service_client.get_container_client(
                "transcriptions"
            )
            if not container_client.exists():
                container_client.create_container()
                logging.info("Created transcriptions container")

            # Generate blob name with timestamp for uniqueness
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"transcript_{timestamp}_{transcript_id}.json"

            # Upload transcript JSON
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(json.dumps(transcript_data, indent=2))
            logging.info(f"Stored transcript in Azure Storage: {blob_name}")

        except Exception as e:
            logging.error(f"Error storing transcript in Azure Storage: {str(e)}")
            # Continue execution to return success response

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "success",
                    "transcript_id": transcript_id,
                    "message": "Transcript received and stored",
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        return func.HttpResponse(f"Error processing webhook: {str(e)}", status_code=500)
