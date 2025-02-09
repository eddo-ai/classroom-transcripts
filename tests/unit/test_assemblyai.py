import os
import pytest
import assemblyai as aai
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
import time
from pathlib import Path
from io import BytesIO
import json
from typing import cast

# Load environment variables from .env.local if it exists
if os.path.exists(".env.local"):
    load_dotenv(".env.local")


def get_blob_service_client():
    """Create a blob service client for testing, supporting both local dev and CI."""
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not storage_account:
        pytest.skip("AZURE_STORAGE_ACCOUNT not found in environment variables")

    if connection_string:  # We're in CI using Azurite
        return BlobServiceClient.from_connection_string(connection_string)
    else:  # We're in local dev using Azure proper
        credential = DefaultAzureCredential()
        account_url = f"https://{storage_account}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=credential)


@pytest.fixture
def blob_service_client():
    """Create a blob service client for testing."""
    return get_blob_service_client()


@pytest.fixture
def test_containers(blob_service_client):
    """Ensure test container exists."""
    try:
        container_client = blob_service_client.create_container("uploads")
        print(f"Created container: uploads")
    except Exception as e:
        print(f"Container uploads already exists or error: {str(e)}")
        container_client = blob_service_client.get_container_client("uploads")
    return container_client


@pytest.fixture
def test_audio_file():
    """Provide a test audio file path, skipping if not available."""
    test_file = Path("tests/fixtures/audio/short-classroom-sample.m4a")
    if not test_file.exists():
        pytest.skip("Test audio file not found at: {}".format(test_file))
    return test_file


@pytest.mark.integration
@pytest.mark.external_api
def test_assemblyai_integration(test_audio_file):
    """Integration test for AssemblyAI API connectivity using local file."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    print(f"\nTesting AssemblyAI API key: {api_key[:4]}...{api_key[-4:]}")
    aai.settings.api_key = api_key

    print(f"\nSubmitting test transcription for local file: {test_audio_file}")

    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(str(test_audio_file))

        # Ensure we have a transcript ID
        assert transcript.id is not None, "Failed to get transcript ID"
        transcript_id: str = cast(str, transcript.id)

        # Wait for completion with timeout
        start_time = time.time()
        while transcript.status not in ["completed", "error"]:
            if time.time() - start_time > 600:  # 10 minute timeout
                pytest.fail("Transcription timed out after 10 minutes")
            time.sleep(10)
            transcript = aai.Transcript.get_by_id(transcript_id)

        assert transcript.status != "error", f"Transcription failed: {transcript.error}"
        assert transcript.text, "Transcript text is empty"

        print("\nTranscription successful!")
        print(f"Transcript ID: {transcript.id}")
        print(f"Status: {transcript.status}")
        print(f"Text: {transcript.text[:200]}...")
    except Exception as e:
        pytest.fail(f"AssemblyAI API test failed: {str(e)}")


@pytest.mark.integration
@pytest.mark.external_api
def test_azure_blob_transcription(test_containers, test_audio_file):
    """Integration test for transcribing audio from Azure blob storage."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    print("\nTesting Azure blob transcription")
    aai.settings.api_key = api_key

    try:
        # Upload test file to blob storage
        blob_name = f"test-{int(time.time())}.m4a"
        print(f"\nUploading test file as: {blob_name}")

        with open(test_audio_file, "rb") as data:
            blob_client = test_containers.upload_blob(name=blob_name, data=data)
            print(f"Successfully uploaded blob")

        # Download the blob content
        print(f"\nDownloading blob: {blob_name}")
        blob_data = blob_client.download_blob().readall()

        # Upload to AssemblyAI
        print("\nUploading to AssemblyAI...")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(BytesIO(blob_data))

        # Ensure we have a transcript ID
        assert transcript.id is not None, "Failed to get transcript ID"
        transcript_id: str = cast(str, transcript.id)

        # Wait for completion with timeout
        start_time = time.time()
        while transcript.status not in ["completed", "error"]:
            if time.time() - start_time > 600:  # 10 minute timeout
                pytest.fail("Transcription timed out after 10 minutes")
            time.sleep(10)
            transcript = aai.Transcript.get_by_id(transcript_id)

        assert transcript.status != "error", f"Transcription failed: {transcript.error}"
        assert transcript.text, "Transcript text is empty"

        print("\nAzure blob transcription successful!")
        print(f"Transcript ID: {transcript.id}")
        print(f"Audio file: {blob_name}")
        print(f"Text preview: {transcript.text[:200]}...")

    except Exception as e:
        pytest.fail(f"Azure blob transcription test failed: {str(e)}")
    finally:
        # Cleanup
        try:
            blob_client.delete_blob()
            print(f"Cleaned up test blob: {blob_name}")
        except Exception as e:
            print(f"Cleanup error (can ignore): {str(e)}")


@pytest.mark.integration
@pytest.mark.external_api
def test_blob_trigger_transcription(test_containers, test_audio_file):
    """Integration test for the blob trigger function."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    print("\nTesting blob trigger function")

    try:
        # Generate a unique blob name
        blob_name = f"test-trigger-{int(time.time())}.m4a"
        print(f"\nUploading test file as: {blob_name}")

        # Upload the test file
        with open(test_audio_file, "rb") as data:
            blob_client = test_containers.upload_blob(name=blob_name, data=data)
            print(f"Successfully uploaded blob")

        # Wait for the function to process and create a transcript
        max_wait_time = 600  # 10 minutes
        start_time = time.time()
        transcription_started = False

        print("\nWaiting for transcription file to appear...")
        transcripts_dir = Path("transcripts")
        while time.time() - start_time < max_wait_time:
            try:
                # Check if transcripts directory exists
                if transcripts_dir.exists():
                    # List all transcript files
                    transcript_files = list(transcripts_dir.glob("transcript_*.json"))

                    if transcript_files:
                        print(
                            f"\nFound transcript files: {[f.name for f in transcript_files]}"
                        )
                        # Read the most recent transcript file
                        latest_transcript = max(
                            transcript_files, key=lambda x: x.stat().st_mtime
                        )
                        with open(latest_transcript) as f:
                            transcript_data = json.load(f)
                            print(f"\nTranscript content preview:")
                            print(
                                f"Transcript ID: {transcript_data.get('transcript_id')}"
                            )
                            print(f"Status: {transcript_data.get('status')}")
                            if transcript_data.get("utterances"):
                                print(
                                    f"First utterance: {transcript_data['utterances'][0]}"
                                )
                        transcription_started = True
                        break

            except Exception as e:
                print(f"\nError checking status: {str(e)}")

            time.sleep(10)  # Check every 10 seconds
            elapsed = int(time.time() - start_time)
            print(f"Elapsed time: {elapsed}s / {max_wait_time}s", end="\r", flush=True)

        if transcription_started:
            print("\nBlob trigger processed the file successfully!")
        else:
            print("\nTimeout reached. Transcript file was not created.")
            if transcripts_dir.exists():
                print("\nCurrent transcripts directory contents:")
                for file in transcripts_dir.glob("*"):
                    print(f"- {file.name}")

        assert transcription_started, (
            "Blob trigger did not process the file within the expected time"
        )

    except Exception as e:
        pytest.fail(f"Blob trigger test failed: {str(e)}")
    finally:
        # Cleanup
        try:
            blob_client.delete_blob()
            print(f"Cleaned up test blob: {blob_name}")
        except Exception as e:
            print(f"Cleanup error (can ignore): {str(e)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
