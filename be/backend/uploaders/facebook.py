import logging
import aiohttp
import os
import database

logger = logging.getLogger(__name__)

async def upload_to_facebook(filepath: str, title: str, description: str, credentials=None) -> str:
    """
    Uploads a video to Facebook Page using Facebook Graph API.
    Supports token rotation.
    Returns the Facebook watch link.
    """
    if credentials:
        tokens = credentials
    else:
        tokens = database.get_api_token("facebook")
        
    if not tokens:
        raise Exception("Facebook Page Access Token not configured.")
        
    if not os.path.exists(filepath):
        raise Exception(f"Video file does not exist: {filepath}")
        
    # Get list of tokens
    tokens_list = database.parse_multiple_api_tokens(tokens) if isinstance(tokens, str) else (tokens if isinstance(tokens, list) else [tokens])
    if not tokens_list:
        raise Exception("No Facebook tokens found.")
        
    last_err = None
    for token in tokens_list:
        try:
            url = "https://graph.facebook.com/v19.0/me/videos"
            
            # We prepare multipart/form-data payload
            data = aiohttp.FormData()
            data.add_field('access_token', token)
            data.add_field('title', title)
            data.add_field('description', description)
            
            with open(filepath, 'rb') as f:
                video_data = f.read()
                data.add_field('source', video_data, filename=os.path.basename(filepath), content_type='video/mp4')
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, data=data) as response:
                        resp_json = await response.json()
                        if response.status == 200 and 'id' in resp_json:
                            fb_video_id = resp_json['id']
                            logger.info(f"Successfully uploaded video to Facebook page. Video ID: {fb_video_id}")
                            return f"https://www.facebook.com/watch/?v={fb_video_id}"
                        else:
                            error_msg = resp_json.get('error', {}).get('message', 'Unknown Facebook API error')
                            logger.error(f"Facebook upload attempt failed: {error_msg}")
                            raise Exception(error_msg)
        except Exception as err:
            logger.warning(f"Facebook token upload failed: {err}. Trying next token...")
            last_err = err
            
    raise last_err
