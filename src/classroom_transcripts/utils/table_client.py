from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential
import os
from functools import lru_cache
import logging


@lru_cache(maxsize=1)
def get_table_client(table_name: str):
    """Get a cached table client for Azure Table Storage.

    Supports both connection string (for local development) and managed identity authentication.
    Creates the table if it doesn't exist.
    """
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    if not account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT_NAME environment variable is required")

    logging.debug(f"Initializing table client for table: {table_name}")
    logging.debug(f"Using account: {account_name}")
    logging.debug(f"Connection string present: {bool(connection_string)}")

    try:
        # Try connection string first for local development
        if connection_string:
            logging.debug("Using connection string authentication")
            table_service = TableServiceClient.from_connection_string(connection_string)
        else:
            # Fall back to managed identity
            logging.debug("Using managed identity authentication")
            credential = DefaultAzureCredential()
            table_service = TableServiceClient(
                endpoint=f"https://{account_name}.table.core.windows.net",
                credential=credential,
            )

        # Create table if it doesn't exist
        try:
            table_service.create_table(table_name)
            logging.info(f"Created table: {table_name}")
        except Exception as e:
            if "TableAlreadyExists" not in str(e):
                logging.error(f"Error creating table: {str(e)}")
                raise
            logging.debug(f"Table {table_name} already exists")

        client = table_service.get_table_client(table_name)
        logging.debug(f"Successfully got table client for {table_name}")
        return client

    except Exception as e:
        logging.error(f"Failed to get table client: {str(e)}")
        raise


def list_table_items(table_name: str, filter_query=None):
    """List items from the table with optional filtering."""
    client = get_table_client(table_name)
    try:
        logging.debug(f"Listing items from table {table_name}")
        if filter_query:
            logging.debug(f"Using filter: {filter_query}")
            items = list(client.query_entities(filter_query))
        else:
            logging.debug("No filter applied, listing all items")
            items = list(client.list_entities())

        logging.debug(f"Found {len(items)} items in table {table_name}")
        return items
    except Exception as e:
        logging.error(f"Error listing table items: {e}")
        raise
