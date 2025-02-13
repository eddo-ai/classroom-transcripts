import os
import pytest
import pytest_asyncio
import asyncio
import time
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
import assemblyai as aai
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()


@pytest.fixture
def blob_service_client():
    """Create a blob service client for testing."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    assert conn_str, "AZURE_STORAGE_CONNECTION_STRING must be set"
    return BlobServiceClient.from_connection_string(conn_str)


@pytest.fixture
def table_service_client():
    """Create a table service client for testing."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    assert conn_str, "AZURE_STORAGE_CONNECTION_STRING must be set"
    return TableServiceClient.from_connection_string(conn_str)


@pytest.fixture
def test_audio_file():
    """Get path to test audio file."""
    file_path = "tests/data/audio/short-classroom-sample.m4a"
    assert os.path.exists(file_path), f"Test file {file_path} not found"
    return file_path


@pytest_asyncio.fixture(autouse=True)
async def setup_and_cleanup(blob_service_client, table_service_client):
    """Setup test containers and tables, and clean them up after."""
    # Create test containers
    test_container = "test-uploads"
    test_table = "TestTranscriptMappings"
    container_client = None

    try:
        # Create container if it doesn't exist
        container_client = blob_service_client.get_container_client(
            test_container)
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                if not container_client.exists():
                    container_client = blob_service_client.create_container(
                        test_container)
                break
            except ResourceExistsError as e:
                if "ContainerBeingDeleted" in str(e):
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(2)  # Wait 2 seconds before retrying
                    continue
                raise

        # Create table if it doesn't exist
        retry_count = 0
        while retry_count < max_retries:
            try:
                table_service_client.create_table(test_table)
                break
            except ResourceExistsError as e:
                if "TableBeingDeleted" in str(e):
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(2)  # Wait 2 seconds before retrying
                    continue
                # If table already exists (not being deleted), that's fine
                if "TableAlreadyExists" in str(e):
                    break
                raise

        yield
    finally:
        # Cleanup
        if container_client:
            try:
                container_client.delete_container()
            except Exception as e:
                print(f"Error deleting container: {e}")

        try:
            table_service_client.delete_table(test_table)
        except Exception as e:
            print(f"Error deleting table: {e}")


@pytest.fixture
def invalid_audio_file(tmp_path):
    """Create an invalid audio file for testing."""
    file_path = tmp_path / "invalid.wav"
    with open(file_path, "wb") as f:
        f.write(b"This is not a valid audio file")
    return str(file_path)


@pytest.fixture
def large_audio_file(tmp_path):
    """Create a large audio file for testing."""
    import numpy as np
    from scipy.io import wavfile

    # Create a 1-minute sine wave at 44.1kHz
    duration = 60  # seconds
    sample_rate = 44100
    t = np.linspace(0, duration, duration * sample_rate)
    audio_data = np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave

    file_path = tmp_path / "large_file.wav"
    wavfile.write(file_path, sample_rate, audio_data.astype(np.float32))
    return str(file_path)


@pytest.mark.asyncio
async def test_transcript_mapping_flow(blob_service_client, table_service_client, test_audio_file):
    """Test the complete flow of uploading, transcribing, and mapping."""
    # Setup
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    blob_name = os.path.basename(test_audio_file)

    # Upload file to blob storage
    container_client = blob_service_client.get_container_client(container_name)
    with open(test_audio_file, "rb") as data:
        blob_client = container_client.upload_blob(name=blob_name, data=data)

    # Submit for transcription
    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    transcriber = aai.Transcriber()

    with open(test_audio_file, "rb") as audio_file:
        transcript = transcriber.transcribe(audio_file)

    assert transcript.status == aai.TranscriptStatus.completed, "Transcription failed"

    # Store mapping
    table_client = table_service_client.get_table_client(table_name)
    entity = {
        "PartitionKey": "AudioFiles",
        "RowKey": blob_name,
        "transcriptId": transcript.id,
        "audioUrl": blob_client.url
    }
    table_client.create_entity(entity=entity)

    # Verify mapping
    retrieved_entity = table_client.get_entity("AudioFiles", blob_name)
    assert retrieved_entity["transcriptId"] == transcript.id
    assert retrieved_entity["audioUrl"] == blob_client.url


@pytest.mark.asyncio
async def test_transcript_mapping_retrieval(blob_service_client, table_service_client, test_audio_file):
    """Test retrieving transcript mapping for a blob."""
    # Setup - reuse the mapping created in the previous test
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    blob_name = os.path.basename(test_audio_file)

    # Try to retrieve mapping
    table_client = table_service_client.get_table_client(table_name)
    entity = table_client.get_entity("AudioFiles", blob_name)

    # Verify the mapping exists and has required fields
    assert entity is not None
    assert "transcriptId" in entity
    assert "audioUrl" in entity

    # Verify the transcript exists in AssemblyAI
    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    transcript = aai.Transcript.get_by_id(entity["transcriptId"])
    assert transcript is not None
    assert transcript.status == aai.TranscriptStatus.completed


@pytest.mark.asyncio
async def test_duplicate_file_uploads(blob_service_client, table_service_client, test_audio_file):
    """Test that uploading the same file twice creates unique IDs and mappings."""
    # Setup
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    base_name = os.path.basename(test_audio_file)

    # First upload
    container_client = blob_service_client.get_container_client(container_name)
    with open(test_audio_file, "rb") as data:
        blob_client1 = container_client.upload_blob(
            name=base_name,
            data=data,
            overwrite=True
        )

    # Submit first transcription
    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    transcriber = aai.Transcriber()
    with open(test_audio_file, "rb") as audio_file:
        transcript1 = transcriber.transcribe(audio_file)

    # Store first mapping
    table_client = table_service_client.get_table_client(table_name)
    entity1 = {
        "PartitionKey": "AudioFiles",
        "RowKey": base_name,
        "transcriptId": transcript1.id,
        "audioUrl": blob_client1.url,
        "uploadTime": datetime.utcnow().isoformat()
    }
    table_client.create_entity(entity=entity1)

    # Second upload - with a timestamp in the name
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    second_name = f"{os.path.splitext(base_name)[0]}_{timestamp}{os.path.splitext(base_name)[1]}"

    with open(test_audio_file, "rb") as data:
        blob_client2 = container_client.upload_blob(
            name=second_name,
            data=data
        )

    # Submit second transcription
    with open(test_audio_file, "rb") as audio_file:
        transcript2 = transcriber.transcribe(audio_file)

    # Store second mapping
    entity2 = {
        "PartitionKey": "AudioFiles",
        "RowKey": second_name,
        "transcriptId": transcript2.id,
        "audioUrl": blob_client2.url,
        "uploadTime": datetime.utcnow().isoformat()
    }
    table_client.create_entity(entity=entity2)

    # Verify both blobs exist and have different IDs
    assert blob_client1.blob_name != blob_client2.blob_name
    assert blob_client1.url != blob_client2.url

    # Verify both transcripts exist and have different IDs
    assert transcript1.id != transcript2.id

    # Verify both mappings exist and are different
    mapping1 = table_client.get_entity("AudioFiles", base_name)
    mapping2 = table_client.get_entity("AudioFiles", second_name)

    assert mapping1["transcriptId"] != mapping2["transcriptId"]
    assert mapping1["audioUrl"] != mapping2["audioUrl"]

    # Verify both transcripts are accessible in AssemblyAI
    transcript1_check = aai.Transcript.get_by_id(mapping1["transcriptId"])
    transcript2_check = aai.Transcript.get_by_id(mapping2["transcriptId"])

    assert transcript1_check is not None
    assert transcript2_check is not None
    assert transcript1_check.id != transcript2_check.id


@pytest.mark.asyncio
async def test_invalid_audio_file_handling(blob_service_client, table_service_client, invalid_audio_file):
    """Test handling of invalid audio files."""
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    blob_name = os.path.basename(invalid_audio_file)

    # Upload invalid file
    container_client = blob_service_client.get_container_client(container_name)
    with open(invalid_audio_file, "rb") as data:
        blob_client = container_client.upload_blob(name=blob_name, data=data)

    # Attempt transcription
    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    transcriber = aai.Transcriber()

    with pytest.raises(aai.error.AssemblyAIError):
        with open(invalid_audio_file, "rb") as audio_file:
            transcript = transcriber.transcribe(audio_file)


@pytest.mark.asyncio
async def test_concurrent_uploads(blob_service_client, table_service_client, test_audio_file):
    """Test handling of concurrent uploads of the same file."""
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    base_name = os.path.basename(test_audio_file)

    async def upload_and_transcribe(index):
        # Create unique name for this upload
        file_name = f"{os.path.splitext(base_name)[0]}_{index}{os.path.splitext(base_name)[1]}"

        # Upload file
        container_client = blob_service_client.get_container_client(
            container_name)
        with open(test_audio_file, "rb") as data:
            blob_client = container_client.upload_blob(
                name=file_name, data=data)

        # Transcribe
        aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
        transcriber = aai.Transcriber()
        with open(test_audio_file, "rb") as audio_file:
            transcript = transcriber.transcribe(audio_file)

        # Store mapping
        table_client = table_service_client.get_table_client(table_name)
        entity = {
            "PartitionKey": "AudioFiles",
            "RowKey": file_name,
            "transcriptId": transcript.id,
            "audioUrl": blob_client.url,
            "uploadTime": datetime.utcnow().isoformat()
        }
        table_client.create_entity(entity=entity)
        return file_name, transcript.id

    # Perform concurrent uploads
    tasks = [upload_and_transcribe(i) for i in range(3)]
    results = await asyncio.gather(*tasks)

    # Verify all uploads were successful and have unique IDs
    transcript_ids = [result[1] for result in results]
    assert len(set(transcript_ids)) == len(
        transcript_ids), "Duplicate transcript IDs found"


@pytest.mark.asyncio
async def test_missing_api_key_handling():
    """Test handling of missing AssemblyAI API key."""
    original_api_key = os.environ.get("ASSEMBLYAI_API_KEY")

    try:
        # Temporarily remove API key
        if "ASSEMBLYAI_API_KEY" in os.environ:
            del os.environ["ASSEMBLYAI_API_KEY"]

        # AssemblyAI raises a generic Exception for auth errors
        with pytest.raises(Exception) as exc_info:
            transcriber = aai.Transcriber()
            transcriber.transcribe("dummy_input")
        assert "API key" in str(exc_info.value)
    finally:
        # Restore API key
        if original_api_key:
            os.environ["ASSEMBLYAI_API_KEY"] = original_api_key


@pytest.mark.asyncio
async def test_large_file_handling(blob_service_client, table_service_client, large_audio_file):
    """Test handling of large audio files."""
    container_name = "test-uploads"
    table_name = "TestTranscriptMappings"
    blob_name = os.path.basename(large_audio_file)

    # Upload large file
    container_client = blob_service_client.get_container_client(container_name)
    with open(large_audio_file, "rb") as data:
        blob_client = container_client.upload_blob(name=blob_name, data=data)

    # Submit for transcription
    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    transcriber = aai.Transcriber()

    with open(large_audio_file, "rb") as audio_file:
        transcript = transcriber.transcribe(audio_file)

    assert transcript.status == aai.TranscriptStatus.completed, "Large file transcription failed"

    # Verify the transcript exists and is complete
    table_client = table_service_client.get_table_client(table_name)
    entity = {
        "PartitionKey": "AudioFiles",
        "RowKey": blob_name,
        "transcriptId": transcript.id,
        "audioUrl": blob_client.url,
        "uploadTime": datetime.utcnow().isoformat()
    }
    table_client.create_entity(entity=entity)

    # Verify mapping
    retrieved_entity = table_client.get_entity("AudioFiles", blob_name)
    assert retrieved_entity["transcriptId"] == transcript.id
    assert retrieved_entity["audioUrl"] == blob_client.url
