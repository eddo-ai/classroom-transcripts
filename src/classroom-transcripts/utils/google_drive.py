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