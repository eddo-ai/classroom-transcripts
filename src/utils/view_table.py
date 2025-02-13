"""Utility script to view Azure Table Storage contents."""
from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential
import os
from dotenv import load_dotenv


def view_transcript_mappings():
    """View all entries in the TranscriptMappings table."""
    load_dotenv()

    # Get storage account name and connection string from environment
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    
    if not account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT environment variable is required")

    try:
        # Try connection string first for local development
        if connection_string:
            table_service = TableServiceClient.from_connection_string(connection_string)
        else:
            # Fall back to managed identity for production
            credential = DefaultAzureCredential()
            
            # If client credentials are available, use them as fallback
            if all(
                os.getenv(key)
                for key in ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"]
            ):
                credential = ClientSecretCredential(
                    tenant_id=os.getenv("AZURE_TENANT_ID"),
                    client_id=os.getenv("AZURE_CLIENT_ID"),
                    client_secret=os.getenv("AZURE_CLIENT_SECRET"),
                )

            # Create the table service client
            table_service = TableServiceClient(
                endpoint=f"https://{account_name}.table.core.windows.net",
                credential=credential,
            )

        # Get the table client
        table_client = table_service.get_table_client("TranscriptMappings")

        # Query all entities
        entities = table_client.list_entities()

        print("\nTranscript Mappings:")
        print("-" * 100)
        print(
            f"{'Blob Name':<40} | "
            f"{'AssemblyAI ID':<36} | "
            f"{'Status':<10} | "
            f"{'Created':<20}"
        )
        print("-" * 100)

        for entity in entities:
            # Debug: print full entity to see all fields
            print("\nDebug - Full entity data:", entity)
            
            print(
                f"{entity.get('BlobName', entity['PartitionKey']):<40} | "
                f"{entity.get('TranscriptId', entity['RowKey']):<36} | "
                f"{entity.get('Status', 'N/A'):<10} | "
                f"{entity.get('Created', 'N/A'):<20}"
            )

    except Exception as e:
        print("Error accessing table storage:")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("\nPlease verify:")
        print("1. Azure credentials are correct")
        print("2. Storage account name is correct")
        print("3. Required roles are assigned (Storage Table Data Contributor)")
        print("4. The table 'TranscriptMappings' exists")
        print("5. AZURE_STORAGE_CONNECTION_STRING is set for local development")


if __name__ == "__main__":
    view_transcript_mappings()
