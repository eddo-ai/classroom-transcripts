from azure.data.tables import TableServiceClient
import os
from functools import lru_cache
import logging

@lru_cache(maxsize=1)
def get_table_client(table_name: str):
    """Get a cached table client for TranscriptMappings."""
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING environment variable not set")

    table_service = TableServiceClient.from_connection_string(connection_string)
    return table_service.get_table_client(table_name)

def list_table_items(filter_query=None):
    """List items from the table with optional filtering."""
    client = get_table_client()
    try:
        if filter_query:
            return list(client.query_entities(filter_query))
        return list(client.list_entities())
    except Exception as e:
        logging.error(f"Error listing table items: {e}")
        raise 