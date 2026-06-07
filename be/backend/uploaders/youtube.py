import os
import json
import logging
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import database

logger = logging.getLogger(__name__)

def run_sync_youtube_upload(filepath: str, title: str, description: str, tags: list, creds_dict: dict) -> str:
    """
    Synchronous execution of YouTube upload, to be run in a thread executor.
    """
    creds = Credentials(
        token=creds_dict.get('token'),
        refresh_token=creds_dict.get('refresh_token'),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_dict.get('client_id'),
        client_secret=creds_dict.get('client_secret')
    )
    
    # Build client
    youtube = build('youtube', 'v3', credentials=creds)
    
    # Body config
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags or [],
            'categoryId': '22'  # 'People & Blogs'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(
        filepath,
        chunksize=1024*1024,
        resumable=True,
        mimetype='video/*'
    )
    
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"YouTube upload progress: {int(status.progress() * 100)}%")
            
    video_id = response.get('id', '')
    logger.info(f"Successfully uploaded to YouTube. Video ID: {video_id}")
    return video_id

async def upload_to_youtube(filepath: str, title: str, description: str, tags: list = None, credentials=None) -> str:
    """
    Asynchronously triggers YouTube upload by wrapping the Google API client in a thread executor.
    Supports credentials rotation.
    Returns the watch link.
    """
    if credentials:
        token_data = credentials
    else:
        token_data = database.get_api_token("youtube")
        
    if not token_data:
        raise Exception("YouTube credentials not configured in API/TOKEN settings.")
        
    tokens_list = database.parse_multiple_api_tokens(token_data) if isinstance(token_data, str) else (token_data if isinstance(token_data, list) else [token_data])
    if not tokens_list:
        raise Exception("No YouTube credentials found.")
        
    if not os.path.exists(filepath):
        raise Exception(f"Video file does not exist: {filepath}")
        
    last_err = None
    for token in tokens_list:
        try:
            creds_dict = {}
            if isinstance(token, dict):
                creds_dict = token
            elif isinstance(token, str):
                try:
                    creds_dict = json.loads(token)
                except json.JSONDecodeError:
                    raise Exception("Invalid JSON structure in YouTube credentials.")
            else:
                continue
                
            if 'installed' in creds_dict:
                creds_dict = creds_dict['installed']
            elif 'web' in creds_dict:
                creds_dict = creds_dict['web']
                
            required = ['client_id', 'client_secret', 'refresh_token']
            missing = [f for f in required if f not in creds_dict]
            if missing:
                raise Exception(f"YouTube credentials missing key fields: {', '.join(missing)}")
                
            video_id = await asyncio.to_thread(
                run_sync_youtube_upload, filepath, title, description, tags, creds_dict
            )
            return f"https://www.youtube.com/watch?v={video_id}"
        except Exception as err:
            logger.warning(f"YouTube upload attempt failed: {err}. Trying next credentials...")
            last_err = err
            
    raise last_err
