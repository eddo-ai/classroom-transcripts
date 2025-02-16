from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import streamlit as st
import io
import os
from datetime import datetime

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'

def get_google_credentials():
    """Get or refresh Google credentials"""
    creds = None
    
    # Try to load credentials from session state first
    if 'google_creds' in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state.google_creds, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                st.error(f"Missing {CREDENTIALS_FILE}. Please set up Google OAuth credentials.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=8501)
        
        # Save credentials in session state
        st.session_state.google_creds = creds.to_json()
    
    return creds

def upload_transcript_to_drive(transcript, filename=None):
    """Upload transcript content to Google Drive"""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        # Prepare transcript content
        if transcript.utterances:
            content = "\n\n".join([
                f"{u.speaker} ({u.start/1000:.1f}s - {u.end/1000:.1f}s):\n{u.text}"
                for u in transcript.utterances
            ])
        else:
            content = transcript.text or "No transcript text available"
        
        # Generate filename if not provided
        if not filename:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transcript_{date_str}.txt"
        
        # Prepare file metadata and media
        file_metadata = {
            'name': filename,
            'mimeType': 'text/plain'
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode()),
            mimetype='text/plain',
            resumable=True
        )
        
        # Upload file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        
        return {
            'success': True,
            'file_id': file.get('id'),
            'link': file.get('webViewLink')
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def create_folder(folder_name, parent_folder_id=None):
    """Create a folder in Google Drive"""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return {
            'success': True,
            'folder_id': folder.get('id')
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def rename_folder(folder_id, new_name):
    """Rename a folder in Google Drive"""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': new_name
        }
        
        folder = service.files().update(fileId=folder_id, body=file_metadata, fields='id, name').execute()
        return {
            'success': True,
            'folder_id': folder.get('id'),
            'folder_name': folder.get('name')
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def delete_folder(folder_id):
    """Delete a folder in Google Drive"""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        service.files().delete(fileId=folder_id).execute()
        return {
            'success': True
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def move_file_to_folder(file_id, folder_id):
    """Move a file to a different folder in Google Drive"""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        # Retrieve the existing parents to remove
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        
        # Move the file to the new folder
        file = service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        
        return {
            'success': True,
            'file_id': file.get('id')
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
