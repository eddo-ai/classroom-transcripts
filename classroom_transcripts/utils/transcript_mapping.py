from datetime import datetime
from azure.data.tables import TableEntity, TableClient
import logging
import warnings

class TranscriptMapper:
    """
    DEPRECATED: This class is deprecated in favor of using the standalone functions create_upload_entity() and update_transcript_status().
    Will be removed in a future version.
    """
    
    def __init__(self, table_client: TableClient):
        warnings.warn(
            "TranscriptMapper class is deprecated. Use create_upload_entity() and update_transcript_status() functions instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.table_client = table_client
    
    def create_upload_entity(self, blob_name: str, original_name: str, transcript_id: str) -> TableEntity:
        """
        Create a standardized entity for storing audio file and transcript mappings.
        
        Args:
            blob_name: Unique name of blob in storage
            original_name: Original filename before uniquification
            transcript_id: AssemblyAI transcript ID
        """
        timestamp = datetime.utcnow().isoformat()
        
        return TableEntity(
            PartitionKey="AudioFiles",
            RowKey=blob_name,
            uploadTime=timestamp,
            originalFileName=original_name,
            transcriptId=transcript_id,
            status="queued"
        )
    
    def update_transcript_status(self, blob_name: str, status: str):
        """Update the transcription status for a given blob."""
        try:
            entity = {
                'PartitionKey': 'AudioFiles',
                'RowKey': blob_name,
                'status': status,
                'lastUpdated': datetime.utcnow().isoformat()
            }
            self.table_client.update_entity(mode='merge', entity=entity)
            logging.info(f"Updated status for {blob_name} to {status}")
        except Exception as e:
            logging.error(f"Failed to update status for {blob_name}: {e}")
            raise
    
    def get_transcript_mapping(self, blob_name: str) -> dict:
        """Retrieve transcript mapping for a given blob name."""
        try:
            entity = self.table_client.get_entity("AudioFiles", blob_name)
            return {
                "transcriptId": entity["transcriptId"],
                "audioUrl": entity["audioUrl"],
                "uploadTime": entity["uploadTime"],
                "status": entity.get("status", "unknown")
            }
        except Exception as e:
            logging.warning(f"No mapping found for blob {blob_name}: {e}")
            return None

# For backward compatibility, keep the original functions
def create_upload_entity(blob_name: str, original_name: str, transcript_id: str) -> TableEntity:
    """
    Create a standardized entity for storing audio file and transcript mappings.
    
    Args:
        blob_name: Unique name of blob in storage
        original_name: Original filename before uniquification
        transcript_id: AssemblyAI transcript ID
    """
    timestamp = datetime.utcnow().isoformat()
    
    return TableEntity(
        PartitionKey="AudioFiles",
        RowKey=blob_name,
        uploadTime=timestamp,
        originalFileName=original_name,
        transcriptId=transcript_id,
        status="queued"
    )

def update_transcript_status(table_client, blob_name: str, status: str):
    """Update the transcription status for a given blob."""
    try:
        entity = {
            'PartitionKey': 'AudioFiles',
            'RowKey': blob_name,
            'status': status,
            'lastUpdated': datetime.utcnow().isoformat()
        }
        table_client.update_entity(mode='merge', entity=entity)
        logging.info(f"Updated status for {blob_name} to {status}")
    except Exception as e:
        logging.error(f"Failed to update status for {blob_name}: {e}")
        raise 