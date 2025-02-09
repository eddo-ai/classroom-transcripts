import os
from azure.storage.blob import BlobServiceClient
from pathlib import Path
import time
import json
from dotenv import load_dotenv
from tests.utils.test_helpers import setup_test_environment

# Load environment variables from .env.local
load_dotenv(".env.local")


def test_blob_trigger():
    """Test the blob trigger function using local storage."""
    # Set up test environment
    env_vars = setup_test_environment()

    try:
        # Create the blob service client
        blob_service_client = BlobServiceClient.from_connection_string(
            env_vars["AZURE_STORAGE_CONNECTION_STRING"]
        )

        # Create containers if they don't exist
        for container_name in ["uploads", "transcriptions"]:
            try:
                container_client = blob_service_client.create_container(container_name)
                print(f"Created container: {container_name}")
            except Exception as e:
                print(f"Container {container_name} already exists")

        # Upload test file
        test_file = Path("tests/fixtures/audio/short-classroom-sample.m4a")
        if not test_file.exists():
            print(f"Test file not found at {test_file}")
            return

        # Upload to uploads container
        uploads_container = blob_service_client.get_container_client("uploads")
        blob_name = test_file.name
        with open(test_file, "rb") as data:
            blob_client = uploads_container.upload_blob(
                name=blob_name, data=data, overwrite=True
            )
            print(f"Uploaded {blob_name} to container uploads")

        print("\nInitial container contents:")
        print("\nContents of 'uploads' container:")
        for blob in uploads_container.list_blobs():
            print(f"- {blob.name} ({blob.size} bytes)")

        print("\nContents of 'transcriptions' container:")
        transcriptions_container = blob_service_client.get_container_client(
            "transcriptions"
        )
        for blob in transcriptions_container.list_blobs():
            print(f"- {blob.name} ({blob.size} bytes)")

        # Monitor for transcription output
        print("\nMonitoring for transcription output...")
        print("(Press Ctrl+C to stop monitoring)")

        seen_transcripts = set()
        while True:
            for blob in transcriptions_container.list_blobs():
                if blob.name not in seen_transcripts:
                    print(f"\nNew transcript found: {blob.name}")
                    # Download and display the transcript
                    transcript_client = transcriptions_container.get_blob_client(
                        blob.name
                    )
                    transcript_data = transcript_client.download_blob().readall()
                    try:
                        transcript_json = json.loads(transcript_data)
                        print("\nTranscript contents:")
                        if "utterances" in transcript_json:
                            for utterance in transcript_json["utterances"]:
                                print(
                                    f"{utterance['timestamp']} - {utterance['speaker']}: {utterance['text']}"
                                )
                        else:
                            print(transcript_json)
                    except json.JSONDecodeError:
                        print(f"Transcript content: {transcript_data.decode()}")

                    seen_transcripts.add(blob.name)

            time.sleep(5)  # Check every 5 seconds

    except KeyboardInterrupt:
        print("\nStopped monitoring")
    except Exception as e:
        print(f"\nError: {str(e)}")


if __name__ == "__main__":
    test_blob_trigger()
