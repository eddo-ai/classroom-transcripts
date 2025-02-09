"""Global test fixtures and configuration."""

import os
import pytest
import logging
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import AzureError
from dotenv import load_dotenv
import assemblyai as aai
from tests.fixtures.fixtures import (
    get_assemblyai_completed_response,
    get_assemblyai_error_response,
    get_azure_storage_response,
    get_test_audio_path,
    get_invalid_audio_path,
    get_empty_audio_path,
)
from tests.unit.test_logging import setup_test_logging

# Load environment variables
load_dotenv(".env")

# Set up logging for all tests
log_file = setup_test_logging()
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """Set up test session."""
    logger.info(f"Starting test session. Logs will be written to: {log_file}")
    yield
    logger.info("Test session completed.")


@pytest.fixture(scope="session")
def azure_credential():
    """Get Azure credential for the test session."""
    try:
        credential = DefaultAzureCredential()
        logger.info("Successfully obtained Azure credentials")
        return credential
    except Exception as e:
        logger.error(f"Failed to obtain Azure credentials: {str(e)}", exc_info=True)
        pytest.skip("Azure credentials not available")


@pytest.fixture(scope="session")
def storage_account():
    """Get storage account name from environment."""
    account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not account:
        logger.error("AZURE_STORAGE_ACCOUNT not found in environment variables")
        pytest.skip("AZURE_STORAGE_ACCOUNT not found in environment variables")
    logger.info(f"Using storage account: {account}")
    return account


@pytest.fixture(scope="session")
def blob_service_client():
    """Create a blob service client for testing."""
    # First try local development storage
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string is not None and (
        "UseDevelopmentStorage=true" in connection_string
        or "127.0.0.1:10000" in connection_string
    ):
        logger.info("Using local development storage")
        return BlobServiceClient.from_connection_string(connection_string)

    # Fall back to Azure cloud storage if configured
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if storage_account:
        try:
            credential = DefaultAzureCredential()
            account_url = f"https://{storage_account}.blob.core.windows.net"
            client = BlobServiceClient(account_url, credential=credential)
            # Test the connection
            client.get_service_properties()
            logger.info(
                f"Successfully connected to Azure cloud storage at {account_url}"
            )
            return client
        except Exception as e:
            logger.error(
                f"Failed to connect to Azure cloud storage: {str(e)}", exc_info=True
            )

    pytest.skip(
        "No valid storage configuration found. Set AZURE_STORAGE_CONNECTION_STRING for local development."
    )


@pytest.fixture(scope="session")
def test_containers(blob_service_client):
    """Ensure test containers exist."""
    containers = ["uploads", "transcripts"]
    created = []

    for container_name in containers:
        try:
            container_client = blob_service_client.create_container(container_name)
            created.append(container_client)
            logger.info(f"Created container: {container_name}")
        except Exception as e:
            logger.warning(f"Container {container_name} already exists: {str(e)}")
            container_client = blob_service_client.get_container_client(container_name)
            created.append(container_client)

    yield created

    # Cleanup containers after tests
    for container in created:
        try:
            container.delete_container()
            logger.info(f"Deleted container: {container.container_name}")
        except Exception as e:
            logger.warning(
                f"Failed to delete container {container.container_name}: {str(e)}"
            )


@pytest.fixture(scope="session")
def assemblyai_client():
    """Configure and return AssemblyAI client."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        logger.error("ASSEMBLYAI_API_KEY not found in environment variables")
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    try:
        aai.settings.api_key = api_key
        transcriber = aai.Transcriber()
        # Test the API key with a simple request
        transcriber.transcribe("Hello world")  # Simple test
        logger.info("Successfully configured AssemblyAI client")
        return transcriber
    except Exception as e:
        logger.error(f"Failed to initialize AssemblyAI client: {str(e)}", exc_info=True)
        pytest.skip("AssemblyAI client initialization failed")


# Test Data Fixtures
@pytest.fixture
def assemblyai_completed():
    """Get sample completed AssemblyAI response."""
    return get_assemblyai_completed_response()


@pytest.fixture
def assemblyai_error():
    """Get sample error AssemblyAI response."""
    return get_assemblyai_error_response()


@pytest.fixture
def azure_storage_data():
    """Get sample Azure Storage response."""
    return get_azure_storage_response()


@pytest.fixture
def test_audio_file():
    """Get the test audio file path."""
    audio_path = get_test_audio_path()
    if not audio_path.exists():
        pytest.skip(f"Test audio file not found at {audio_path}")
    return audio_path


@pytest.fixture
def invalid_audio_file():
    """Get the invalid test audio file path."""
    return get_invalid_audio_path()


@pytest.fixture
def empty_audio_file():
    """Get the empty test audio file path."""
    return get_empty_audio_path()


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test_api_key",
        "AZURE_STORAGE_SAS_URL": "http://example.com/container?sas=token",
        "AZURE_FUNCTION_KEY": "test_function_key",
        "WEBSITE_HOSTNAME": "test.azurewebsites.net",
        "AZURE_STORAGE_ACCOUNT": "teststorage",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
        logger.debug(f"Mocked environment variable: {key}")
    return env_vars


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture test results."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def log_test_case(request):
    """Log the start and end of each test case."""
    test_name = request.node.name
    logger.info(f"Starting test: {test_name}")
    yield
    # Log test result
    if hasattr(request.node, "rep_call"):
        if request.node.rep_call.passed:
            logger.info(f"Test result for {test_name}: PASS")
        elif request.node.rep_call.failed:
            logger.info(f"Test result for {test_name}: FAIL")
        elif request.node.rep_call.skipped:
            logger.info(f"Test result for {test_name}: SKIP")
