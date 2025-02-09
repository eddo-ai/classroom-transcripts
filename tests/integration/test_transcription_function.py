import os
import pytest
from pathlib import Path
import time
from azure.storage.blob import BlobServiceClient, BlobClient
import json
import assemblyai as aai
from dotenv import load_dotenv
import azure.functions as func
from src.functions.transcription_function import (
    submit_transcription,
    handle_webhook,
)
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from tests.utils.test_helpers import setup_test_environment

# Load environment variables from .env.local
load_dotenv()


# Mock classes for Azure Functions
class MockInputStream(func.InputStream):
    def __init__(self, name):
        self._name = name
        self._bytes = b""  # Empty bytes for testing
        self._length = 0
        self._uri = f"http://localhost/api/audio/{name}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def length(self) -> int:
        return self._length

    @property
    def uri(self) -> str:
        return self._uri

    def read(self) -> bytes:
        return self._bytes

    def seek(self, offset: int, whence: int) -> None:
        pass

    def close(self) -> None:
        pass


class MockHttpRequest(func.HttpRequest):
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")
        self._json = body
        super().__init__(
            method="POST",
            url="http://localhost/api/webhook",
            body=self._body,
            params={},
            headers={},
        )

    def get_json(self):
        return self._json


@pytest.fixture
def blob_service_client():
    """Create a blob service client for testing."""
    connection_string = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    return BlobServiceClient.from_connection_string(connection_string)


@pytest.fixture
def test_containers(blob_service_client):
    """Ensure test container exists."""
    try:
        container_client = blob_service_client.create_container("uploads")
        print(f"Created container: uploads")
    except Exception as e:
        print(f"Container uploads already exists")
        container_client = blob_service_client.get_container_client("uploads")
    return container_client


@pytest.fixture
def test_audio_file():
    """Get the test audio file path."""
    test_file = Path("tests/fixtures/audio/short-classroom-sample.m4a")
    if not test_file.exists():
        pytest.fail(f"Test file not found at {test_file}")
    return test_file


@pytest.mark.integration
def test_container_setup(test_containers):
    """Test that the Azure Storage container is properly set up."""
    # Verify container exists and is accessible
    assert test_containers.exists()


@pytest.mark.integration
def test_audio_file_upload(blob_service_client, test_containers, test_audio_file):
    """Test uploading an audio file to the uploads container."""
    # Upload test file
    blob_name = test_audio_file.name
    with open(test_audio_file, "rb") as data:
        blob_client = test_containers.upload_blob(
            name=blob_name, data=data, overwrite=True
        )

    # Verify upload
    blob_properties = blob_client.get_blob_properties()
    assert blob_properties.size > 0
    print(f"Uploaded {blob_name} ({blob_properties.size} bytes) to container uploads")


@pytest.mark.integration
def test_assemblyai_configuration():
    """Test AssemblyAI API configuration."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    assert api_key is not None, "ASSEMBLYAI_API_KEY not found in environment variables"

    # Test API key validity
    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()
    assert transcriber is not None


@pytest.fixture(autouse=True)
def setup_local_env():
    """Set up local development environment for all tests."""
    env_vars = setup_test_environment()
    with patch.dict(os.environ, env_vars, clear=True):
        yield


@pytest.fixture
def mock_local_blob():
    """Create a mock blob for local testing."""
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"
    return mock_blob


@pytest.fixture
def mock_local_storage():
    """Set up mock storage for local testing."""
    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    return mock_service_client


@pytest.mark.integration
def test_simple():
    """A simple test to verify our test environment."""
    assert True


@pytest.mark.integration
def test_sas_token_generation_local():
    """Test SAS token generation in local development environment."""
    # Mock the input blob
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"

    # Set up local development environment
    env_vars = {
        "AZURE_STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
        "ASSEMBLYAI_API_KEY": "test-key",
        "WEBSITE_HOSTNAME": "localhost:7071",
    }

    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    # Mock the transcriber
    mock_transcriber = MagicMock()
    mock_transcriber.submit.return_value = MagicMock()

    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            return_value=mock_service_client,
        ),
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
    ):
        try:
            # Call the function
            submit_transcription(mock_blob)

            # Get the audio_url that was passed to transcriber.submit
            call_args = mock_transcriber.submit.call_args
            if not call_args:
                pytest.fail("transcriber.submit was not called")

            audio_url = call_args[0][0]  # First positional argument
            print(f"\nConstructed audio URL: {audio_url}")

            # Verify URL components for local development
            assert "http://127.0.0.1:10000/devstoreaccount1/uploads/" in audio_url
            assert "test-audio.m4a" in audio_url
            assert "sig=" in audio_url  # SAS token signature
            assert "se=" in audio_url  # SAS token expiry
            assert "sp=r" in audio_url  # Read permission

        except Exception as e:
            pytest.fail(f"Test failed with error: {str(e)}")
