"""Utility script to list blobs in Azure Storage."""
from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv

def list_blobs():
    """List all blobs in the storage account."""
    load_dotenv()
    
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")

    # Create blob service client
    blob_service = BlobServiceClient.from_connection_string(connection_string)
    
    # List all containers
    print("\nContainers:")
    print("-" * 80)
    for container in blob_service.list_containers():
        print(f"\nContainer: {container.name}")
        print("-" * 40)
        
        # Get container client
        container_client = blob_service.get_container_client(container.name)
        
        # List blobs in container
        for blob in container_client.list_blobs():
            print(f"Blob name: {blob.name}")
            print(f"Size: {blob.size:,} bytes")
            print(f"Last modified: {blob.last_modified}")
            print(f"Content type: {blob.content_settings.content_type}")
            print("-" * 40)

if __name__ == "__main__":
    list_blobs() 