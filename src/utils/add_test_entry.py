"""Utility script to add a test entry to the TranscriptMappings table."""
from azure.data.tables import TableServiceClient, EntityProperty
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.data.tables import EdmType
import os
from dotenv import load_dotenv
from datetime import datetime

def add_test_entry():
    """Add a test entry to the TranscriptMappings table."""
    load_dotenv()
    
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")

    # Create table service client
    table_service = TableServiceClient.from_connection_string(connection_string)
    table_name = "TranscriptMappings"
    
    # Try to get table client, create if doesn't exist
    try:
        table_client = table_service.get_table_client(table_name)
        # Test if table exists by trying to query it
        next(table_client.list_entities(), None)
        print(f"Using existing table: {table_name}")
    except ResourceNotFoundError:
        table_service.create_table(table_name)
        table_client = table_service.get_table_client(table_name)
        print(f"Created new table: {table_name}")
    
    # Create test entity with blob metadata
    current_time = datetime.now().isoformat()
    test_entity = {
        'PartitionKey': 'test_audio.mp3',
        'RowKey': f'test_transcript_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'BlobName': 'test_audio.mp3',
        'transcriptId': f'test_id_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'Status': 'queued',
        'uploadTime': EntityProperty(current_time, EdmType.STRING),
        'container': 'audio-files',
        'audioUrl': 'https://example.com/test.mp3',
        # Blob metadata
        'blobSize': EntityProperty('1024', EdmType.INT32),
        'blobContentType': 'audio/mp3',
        'blobLastModified': EntityProperty(current_time, EdmType.STRING),
        'blobETag': '"0x8D8F8F8F8F8F8F8"',
        'blobLeaseState': 'available',
        'blobLeaseStatus': 'unlocked'
    }
    
    # Add entity to table
    entity = table_client.create_entity(entity=test_entity)
    print(f"Added test entity: {entity}")

if __name__ == "__main__":
    add_test_entry() 