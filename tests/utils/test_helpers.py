"""Test utilities and helper functions."""

import os
import tempfile
import wave
import numpy as np
from pathlib import Path
from typing import Optional
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential


def create_test_audio_file(
    duration: float = 1.0, sample_rate: int = 44100, filename: Optional[str] = None
) -> Path:
    """
    Create a test WAV audio file with specified duration and sample rate.

    Args:
        duration: Length of the audio in seconds
        sample_rate: Sample rate in Hz
        filename: Optional filename, if None a temporary file is created

    Returns:
        Path to the created audio file
    """
    # Generate a simple sine wave
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio_data = np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave
    audio_data = (audio_data * 32767).astype(np.int16)

    # Create output file
    if filename:
        output_path = Path(filename)
    else:
        temp_dir = Path(tempfile.gettempdir())
        output_path = temp_dir / f"test_audio_{duration}s.wav"

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

    return output_path


def get_test_blob_client(connection_string: Optional[str] = None) -> BlobServiceClient:
    """
    Get a blob service client for testing, supporting both local and cloud environments.

    Args:
        connection_string: Optional connection string for local testing

    Returns:
        BlobServiceClient instance
    """
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")

    if connection_string:  # Local testing with Azurite
        return BlobServiceClient.from_connection_string(connection_string)
    elif storage_account:  # Cloud testing with managed identity
        credential = DefaultAzureCredential()
        account_url = f"https://{storage_account}.blob.core.windows.net"
        return BlobServiceClient(account_url, credential=credential)
    else:
        raise ValueError(
            "Either connection_string or AZURE_STORAGE_ACCOUNT must be provided"
        )


def setup_test_environment() -> dict:
    """
    Set up a test environment with required variables.

    Returns:
        Dictionary of environment variables
    """
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test_api_key",
        "AZURE_STORAGE_ACCOUNT": "devstoreaccount1",
        "AZURE_STORAGE_CONNECTION_STRING": (
            "DefaultEndpointsProtocol=http;"
            "AccountName=devstoreaccount1;"
            "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
            "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1"
        ),
        "WEBSITE_HOSTNAME": "localhost:7071",
        "AZURE_FUNCTION_KEY": "test_function_key",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    }

    # Update environment
    for key, value in env_vars.items():
        os.environ[key] = value

    return env_vars


def cleanup_test_resources(paths: list[Path]) -> None:
    """
    Clean up test resources (files, directories).

    Args:
        paths: List of paths to clean up
    """
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except Exception as e:
            print(f"Warning: Failed to clean up {path}: {e}")
