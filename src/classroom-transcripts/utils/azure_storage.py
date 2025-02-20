from datetime import datetime, timedelta
import os
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
import logging

account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
storage_account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")


def get_sas_url_for_audio_file_name(audio_file_name: str, expiry_hours: int = 24) -> str:
    """
    Get a SAS URL for an audio file name.

    Args:
        audio_file_name: Name of the audio file
        expiry_hours: Number of hours until SAS token expires (default 24)
    
    Returns:
        str: Full URL with SAS token
    """

    container_name = "uploads"

    if not account_name:
        raise ValueError(f"Error getting SAS URL for audio file: {audio_file_name} - Azure Storage account name is not set")

    if not storage_account_key:
        raise ValueError(f"Error getting SAS URL for audio file: {audio_file_name} - Azure Storage account key is not set")

    # Set start time to now and expiry time to 24 hours from now
    start_time = datetime.now()
    expiry_time = start_time + timedelta(hours=expiry_hours)

    try:
        sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=audio_file_name,
        account_key=storage_account_key,
        permission=BlobSasPermissions(read=True),
        start=start_time,
        expiry=expiry_time
        )

        logging.debug(f"Generated SAS URL for audio file {audio_file_name}")

        return f"https://{account_name}.blob.core.windows.net/{container_name}/{audio_file_name}?{sas_token}"

    except Exception as e:
        logging.error(f"Error generating SAS URL for audio file {audio_file_name}: {e}")
        raise
