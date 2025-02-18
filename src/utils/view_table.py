"""Utility script to view Azure Table Storage contents."""
from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential
import os
from dotenv import load_dotenv


def get_table_client():
    """Get a table client for the TranscriptMappings table."""
    load_dotenv()

    # Get storage account name and connection string from environment
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT environment variable is required")

    try:
        # Try connection string first for local development
        if connection_string:
            table_service = TableServiceClient.from_connection_string(connection_string)
        else:
            # Fall back to managed identity
            credential = DefaultAzureCredential()
            table_service = TableServiceClient(
                endpoint=f"https://{account_name}.table.core.windows.net",
                credential=credential
            )
        
        # Get the table client
        table_client = table_service.get_table_client("TranscriptMappings")
        return table_client
        
    except Exception as e:
        raise Exception(f"Failed to get table client: {str(e)}")


def list_table_items(table_client):
    """List all items in the table."""
    try:
        items = list(table_client.list_entities())
        return items
    except Exception as e:
        raise Exception(f"Failed to list table items: {str(e)}")
