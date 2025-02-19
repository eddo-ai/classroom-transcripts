from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential
import os
from functools import lru_cache
import logging


@lru_cache(maxsize=1)
def get_table_client(table_name: str):
    """Get a cached table client for Azure Table Storage.

    Supports both connection string (for local development) and managed identity authentication.
    """
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT_NAME environment variable is required")

    try:
        # Try connection string first for local development
        if connection_string:
            table_service = TableServiceClient.from_connection_string(connection_string)
        else:
            # Fall back to managed identity
            credential = DefaultAzureCredential()
            table_service = TableServiceClient(
                endpoint=f"https://{account_name}.table.core.windows.net",
                credential=credential,
            )

        return table_service.get_table_client(table_name)

    except Exception as e:
        logging.error(f"Failed to get table client: {str(e)}")
        raise


def list_table_items(table_name: str, filter_query=None):
    """List items from the table with optional filtering."""
    client = get_table_client(table_name)
    try:
        if filter_query:
            return list(client.query_entities(filter_query))
        return list(client.list_entities())
    except Exception as e:
        logging.error(f"Error listing table items: {e}")
        raise
