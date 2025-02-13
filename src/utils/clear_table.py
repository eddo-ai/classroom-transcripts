"""Utility script to clear all entries from the TranscriptMappings table."""
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError
import os
from dotenv import load_dotenv

def clear_table():
    """Clear all entries from the TranscriptMappings table."""
    load_dotenv()
    
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is required")

    # Create table service client
    table_service = TableServiceClient.from_connection_string(connection_string)
    
    try:
        table_client = table_service.get_table_client("TranscriptMappings")
        # Test if table exists
        entities = list(table_client.list_entities())
        print(f"Found {len(entities)} entities")
        
        for entity in entities:
            table_client.delete_entity(
                partition_key=entity["PartitionKey"],
                row_key=entity["RowKey"]
            )
            print(f"Deleted entity: {entity['PartitionKey']}/{entity['RowKey']}")
        
        print("Table cleared successfully")
    except ResourceNotFoundError:
        print("Table does not exist")

if __name__ == "__main__":
    clear_table() 