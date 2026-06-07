import logging
import asyncio
import os
import re
import aiohttp
import shutil
import time
import yt_dlp
from fastapi import FastAPI, Request, Response, Depends, HTTPException, Security, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import database
import config
from backend.processor import fetch_channel_videos

logger = logging.getLogger(__name__)

app = FastAPI(title="Video Reup Automation Dashboard & API")

# Setup CORS for Frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Header definition
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if config.API_KEY:
        if api_key != config.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

# ==================== HELPERS PORTED FROM SETTINGS ====================

def are_credentials_matching(cred1, cred2):
    if not cred1 or not cred2:
        return False
    import json
    if isinstance(cred1, str) and cred1.strip().startswith('{'):
        try:
            cred1 = json.loads(cred1)
        except:
            pass
    if isinstance(cred2, str) and cred2.strip().startswith('{'):
        try:
            cred2 = json.loads(cred2)
        except:
            pass
            
    if isinstance(cred1, dict) and isinstance(cred2, dict):
        if 'installed' in cred1:
            cred1 = cred1['installed']
        if 'web' in cred1:
            cred1 = cred1['web']
        if 'installed' in cred2:
            cred2 = cred2['installed']
        if 'web' in cred2:
            cred2 = cred2['web']
            
        if 'refresh_token' in cred1 and 'refresh_token' in cred2:
            return cred1['refresh_token'] == cred2['refresh_token']
        return cred1 == cred2
        
    return str(cred1).strip() == str(cred2).strip()

async def auto_discover_destinations(platform: str, token_input):
    if isinstance(token_input, str):
        tokens_list = database.parse_multiple_api_tokens(token_input)
    elif isinstance(token_input, list):
        tokens_list = token_input
    else:
        tokens_list = [token_input]
        
    existing_channels = []
    try:
        existing_channels = [c for c in database.get_destination_channels() if c['platform'] == platform]
    except Exception as e:
        logger.error(f"Error fetching existing destinations: {e}")
        
    valid_destination_ids = set()
    
    for token in tokens_list:
        success = False
        discovered_channels = []
        
        try:
            if platform == 'youtube':
                import json
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                
                creds_dict = {}
                if isinstance(token, dict):
                    creds_dict = token
                else:
                    creds_dict = json.loads(token)
                    
                if 'installed' in creds_dict:
                    creds_dict = creds_dict['installed']
                elif 'web' in creds_dict:
                    creds_dict = creds_dict['web']
                    
                creds = Credentials(
                    token=creds_dict.get('token'),
                    refresh_token=creds_dict.get('refresh_token'),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=creds_dict.get('client_id'),
                    client_secret=creds_dict.get('client_secret')
                )
                
                def fetch_yt_channels():
                    youtube = build('youtube', 'v3', credentials=creds)
                    request = youtube.channels().list(part="snippet", mine=True)
                    return request.execute()
                    
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, fetch_yt_channels)
                
                if 'items' in res:
                    for item in res['items']:
                        channel_name = item['snippet']['title']
                        channel_id = item['id']
                        discovered_channels.append((channel_name, channel_id, creds_dict))
                    success = True
                        
            elif platform == 'facebook':
                import aiohttp
                url = f"https://graph.facebook.com/v19.0/me?fields=name,id&access_token={token}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            page_name = data.get('name', 'Facebook Page')
                            page_id = data.get('id')
                            discovered_channels.append((page_name, page_id, token))
                            success = True
                            
            elif platform == 'tiktok':
                channel_name = "TikTok Profile"
                channel_id = "tiktok_user"
                try:
                    import aiohttp
                    if isinstance(token, str):
                        headers = {
                            "Cookie": f"sessionid={token}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        async with aiohttp.ClientSession() as session:
                            async with session.get("https://www.tiktok.com/passport/web/user/info/", headers=headers) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if data.get('message') == 'success' and 'data' in data:
                                        channel_name = data['data'].get('nickname') or data['data'].get('username') or channel_name
                                        channel_id = data['data'].get('username') or channel_id
                except Exception as tk_err:
                    logger.warning(f"TikTok username discovery failed: {tk_err}")
                
                discovered_channels.append((channel_name, channel_id, token))
                success = True
                
        except Exception as e:
            logger.error(f"Error auto-discovering destinations for {platform} token: {e}")
            
        if success:
            for name, cid, creds in discovered_channels:
                try:
                    dest_id = database.add_destination_channel(platform, name, cid, creds)
                    valid_destination_ids.add(dest_id)
                    logger.info(f"Auto-discovered/updated {platform} channel: {name}")
                except Exception as db_err:
                    logger.error(f"Failed to add/update destination channel: {db_err}")
        else:
            for ech in existing_channels:
                if are_credentials_matching(ech.get('credentials'), token):
                    valid_destination_ids.add(ech['id'])
                    logger.info(f"Preserved existing {platform} channel {ech['channel_name']} due to connection test failure.")
                    
    for ech in existing_channels:
        if ech['id'] not in valid_destination_ids:
            try:
                database.delete_destination_channel(ech['id'])
                logger.info(f"Removed obsolete destination channel {ech['channel_name']} ({platform}) and its mappings.")
            except Exception as del_err:
                logger.error(f"Failed to delete obsolete channel {ech['channel_name']}: {del_err}")

async def extract_channel_metadata(url, platform):
    if platform == 'facebook':
        from backend.playwright_scraper import scrape_facebook_channel_info
        return await scrape_facebook_channel_info(url)
    elif platform == 'tiktok':
        from backend.playwright_scraper import scrape_tiktok_channel_info
        return await scrape_tiktok_channel_info(url)
        
    def _extract():
        ydl_opts = {
            'extract_flat': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'playlistend': 1,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            channel_name = info.get('title') or info.get('uploader') or "Unknown Channel"
            channel_id = info.get('id') or info.get('channel_id') or url.split('/')[-1]
            return channel_name, channel_id

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract)

# ==================== HTML Dashboard Page ====================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Reup Automation Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-primary: #3b82f6;
            --accent-secondary: #8b5cf6;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --success: #10b981;
            --failed: #ef4444;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            background: radial-gradient(circle at top right, #1e1b4b, var(--bg-color));
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            min-height: 100vh;
            padding: 2rem 1rem;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }
        
        h1 {
            font-weight: 800;
            background: linear-gradient(to right, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.2rem;
            letter-spacing: -0.5px;
        }
        
        .badge {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(16, 185, 129, 0.3);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .badge.off {
            background: rgba(239, 68, 68, 0.15);
            color: var(--failed);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }
        
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        }
        
        .card-title {
            font-size: 0.9rem;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 1px;
            margin-bottom: 0.75rem;
        }
        
        .card-value {
            font-size: 2rem;
            font-weight: 800;
            color: #ffffff;
        }
        
        .card-sub {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 0.5rem;
        }
        
        .log-section {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
        }
        
        .section-title {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            color: #ffffff;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }
        
        th {
            text-align: left;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-muted);
            font-weight: 600;
        }
        
        td {
            padding: 0.85rem 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        
        tr:hover td {
            background: rgba(255,255,255,0.02);
        }
        
        .level-info {
            color: var(--accent-primary);
        }
        .level-warning {
            color: #f59e0b;
        }
        .level-error {
            color: var(--failed);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Reup Automation Panel</h1>
                <p style="color: var(--text-muted); margin-top: 0.25rem;">Hugging Face Spaces Engine v1.0</p>
            </div>
            <div class="badge {scheduler_class}">
                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:currentColor;"></span>
                {scheduler_status}
            </div>
        </header>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">Monitored Channels</div>
                <div class="card-value">{monitored_count}</div>
                <div class="card-sub">Active content sources scanned</div>
            </div>
            
            <div class="card">
                <div class="card-title">Destination Channels</div>
                <div class="card-value">{destination_count}</div>
                <div class="card-sub">Link targets mapped</div>
            </div>
            
            <div class="card">
                <div class="card-title">Scan Interval</div>
                <div class="card-value">{scan_interval}</div>
                <div class="card-sub">Time cycle HH:MM:SS</div>
            </div>
            
            <div class="card">
                <div class="card-title">Processed Queue</div>
                <div class="card-value">{queue_count}</div>
                <div class="card-sub">Total cataloged video items</div>
            </div>
        </div>
        
        <div class="log-section">
            <div class="section-title">System Activity Log</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th style="width: 20%;">Timestamp</th>
                            <th style="width: 15%;">Level</th>
                            <th style="width: 65%;">Message</th>
                        </tr>
                    </thead>
                    <tbody>
                        {log_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        setInterval(() => {
            fetch('/')
                .then(r => console.log('Self-ping successful, status:', r.status))
                .catch(e => console.error('Self-ping failed:', e));
        }, 60000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    monitored_channels = database.get_monitored_channels()
    destinations = database.get_destination_channels()
    scan_interval = database.get_setting("scan_interval", "01:00:00")
    auto_mode_enabled = database.get_setting("auto_mode_enabled") == "true"
    
    conn = database.get_db_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM video_queue").fetchone()
    queue_count = row['count'] if row else 0
    conn.close()
    
    logs = database.get_logs(15)
    log_rows = ""
    for log in logs:
        level_class = f"level-{log['level'].lower()}"
        log_rows += f"""
        <tr>
            <td style="color: var(--text-muted);">{log['timestamp']}</td>
            <td><span class="{level_class}" style="font-weight: 600;">{log['level']}</span></td>
            <td>{log['message']}</td>
        </tr>
        """
    if not log_rows:
        log_rows = "<tr><td colspan='3' style='text-align:center; color:var(--text-muted);'>No log entries.</td></tr>"
        
    scheduler_status = "Scheduler Active" if auto_mode_enabled else "Scheduler Paused"
    scheduler_class = "" if auto_mode_enabled else "off"
    
    html_content = DASHBOARD_HTML.format(
        scheduler_status=scheduler_status,
        scheduler_class=scheduler_class,
        monitored_count=len(monitored_channels),
        destination_count=len(destinations),
        scan_interval=scan_interval,
        queue_count=queue_count,
        log_rows=log_rows
    )
    
    return html_content

@app.get("/debug", dependencies=[Depends(verify_api_key)])
async def get_debug_info():
    info = {}
    
    try:
        info["db_path"] = str(config.DB_PATH)
        info["db_exists"] = config.DB_PATH.exists()
        if info["db_exists"]:
            info["db_size"] = config.DB_PATH.stat().st_size
    except Exception as e:
        info["db_check_error"] = str(e)
        
    try:
        info["db_logs"] = database.get_logs(20)
    except Exception as e:
        info["db_logs_error"] = str(e)
        
    try:
        log_path = config.DATA_DIR / "app.log"
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                info["app_log_tail"] = lines[-100:]
        else:
            info["app_log_tail"] = "app.log does not exist yet."
    except Exception as e:
        info["app_log_error"] = str(e)
        
    return info

# ==================== REST API ENDPOINTS FOR WEB FRONTEND ====================

@app.get("/api/status", dependencies=[Depends(verify_api_key)])
async def get_api_status():
    monitored_channels = database.get_monitored_channels()
    destinations = database.get_destination_channels()
    scan_interval = database.get_setting("scan_interval", "01:00:00")
    auto_mode_enabled = database.get_setting("auto_mode_enabled") == "true"
    
    conn = database.get_db_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM video_queue").fetchone()
    queue_count = row['count'] if row else 0
    conn.close()
    
    return {
        "scheduler_status": "Active" if auto_mode_enabled else "Paused",
        "auto_mode_enabled": auto_mode_enabled,
        "monitored_count": len(monitored_channels),
        "destination_count": len(destinations),
        "scan_interval": scan_interval,
        "queue_count": queue_count,
    }

@app.get("/api/logs", dependencies=[Depends(verify_api_key)])
async def get_api_logs(limit: int = 50):
    return database.get_logs(limit)

@app.post("/api/scheduler/toggle", dependencies=[Depends(verify_api_key)])
async def toggle_scheduler():
    from backend.scheduler import start_scheduler, stop_scheduler
    auto_mode_enabled = database.get_setting("auto_mode_enabled") == "true"
    new_state = not auto_mode_enabled
    database.set_setting("auto_mode_enabled", "true" if new_state else "false")
    
    if new_state:
        start_scheduler()
        database.log_event("INFO", "Scheduler started via Web UI.")
    else:
        stop_scheduler()
        database.log_event("INFO", "Scheduler paused via Web UI.")
        
    return {"status": "success", "auto_mode_enabled": new_state}

@app.post("/api/scheduler/scan", dependencies=[Depends(verify_api_key)])
async def trigger_auto_scan():
    from backend.scheduler import scan_monitored_channels_job
    asyncio.create_task(scan_monitored_channels_job())
    database.log_event("INFO", "Manual trigger of auto-scan job initiated via Web UI.")
    return {"status": "success", "message": "Auto-scan initiated"}

@app.get("/api/apis", dependencies=[Depends(verify_api_key)])
async def get_apis():
    platforms = ['google_ai_studio', 'groq', 'youtube', 'tiktok', 'facebook']
    result = []
    for platform in platforms:
        token = database.get_api_token(platform)
        result.append({
            "platform": platform,
            "connected": token is not None,
        })
    return result

class ApiTokenUpdate(BaseModel):
    platform: str
    token: str

@app.post("/api/apis", dependencies=[Depends(verify_api_key)])
async def update_api_token(data: ApiTokenUpdate):
    platform = data.platform.lower()
    token_input = data.token.strip()
    
    parsed_tokens = database.parse_multiple_api_tokens(token_input)
    database.save_api_token(platform, parsed_tokens)
    database.log_event("INFO", f"Updated API credentials for {platform} via Web UI.")
    
    asyncio.create_task(auto_discover_destinations(platform, parsed_tokens))
    return {"status": "success"}

@app.delete("/api/apis/{platform}", dependencies=[Depends(verify_api_key)])
async def delete_api_token(platform: str):
    database.delete_api_token(platform)
    database.log_event("INFO", f"Deleted API credentials for {platform} via Web UI.")
    return {"status": "success"}

@app.post("/api/apis/{platform}/test", dependencies=[Depends(verify_api_key)])
async def test_api_token(platform: str):
    tokens_list = database.get_api_tokens_list(platform)
    if not tokens_list:
        return {"status": "failed", "error": "No credentials configured."}
        
    results = []
    for idx, token in enumerate(tokens_list, 1):
        success = False
        error_msg = ""
        channel_name = None
        
        try:
            if platform == 'google_ai_studio':
                from google import genai
                api_key = token
                if isinstance(token, dict) and 'api_key' in token:
                    api_key = token['api_key']
                elif isinstance(token, dict):
                    api_key = list(token.values())[0] if token else ""
                    
                client = genai.Client(api_key=str(api_key))
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents='Hello',
                ))
                success = True
            elif platform == 'groq':
                from groq import Groq
                api_key = token
                if isinstance(token, dict) and 'api_key' in token:
                    api_key = token['api_key']
                elif isinstance(token, dict):
                    api_key = list(token.values())[0] if token else ""
                    
                client = Groq(api_key=str(api_key))
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5
                ))
                success = True
            elif platform == 'facebook':
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://graph.facebook.com/v19.0/me?fields=name,id&access_token={token}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            channel_name = data.get('name', 'Facebook Page')
                            success = True
                        else:
                            data = await resp.json()
                            error_msg = data.get('error', {}).get('message', 'Facebook error')
            elif platform == 'youtube':
                import json
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds_dict = token if isinstance(token, dict) else json.loads(token)
                if 'installed' in creds_dict:
                    creds_dict = creds_dict['installed']
                elif 'web' in creds_dict:
                    creds_dict = creds_dict['web']
                creds = Credentials(
                    token=creds_dict.get('token'),
                    refresh_token=creds_dict.get('refresh_token'),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=creds_dict.get('client_id'),
                    client_secret=creds_dict.get('client_secret')
                )
                def fetch_yt_channels():
                    youtube = build('youtube', 'v3', credentials=creds)
                    return youtube.channels().list(part="snippet", mine=True).execute()
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, fetch_yt_channels)
                if 'items' in res and len(res['items']) > 0:
                    channel_name = res['items'][0]['snippet']['title']
                    success = True
                else:
                    error_msg = "No YouTube channel found."
            elif platform == 'tiktok':
                is_official = False
                config_dict = {}
                if isinstance(token, str) and token.strip().startswith('{'):
                    try:
                        config_dict = json.loads(token)
                        is_official = 'access_token' in config_dict
                    except: pass
                elif isinstance(token, dict) and 'access_token' in token:
                    config_dict = token
                    is_official = True
                if is_official:
                    access_token = config_dict['access_token']
                    url = "https://open.tiktokapis.com/v2/user/info/?fields=display_name,username"
                    headers = {"Authorization": f"Bearer {access_token}"}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                user_data = data.get('data', {}).get('user', {})
                                channel_name = user_data.get('display_name') or user_data.get('username') or 'TikTok Profile'
                                success = True
                            else:
                                error_msg = f"TikTok API error: {await resp.text()}"
                else:
                    session_id = token.strip()
                    headers = {
                        "Cookie": f"sessionid={session_id}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://www.tiktok.com/passport/web/user/info/", headers=headers) as resp:
                            if resp.status == 200:
                                try:
                                    data = await resp.json()
                                    if data.get('message') == 'success' and 'data' in data:
                                        channel_name = data['data'].get('nickname') or data['data'].get('username')
                                        if channel_name: success = True
                                except: pass
                        if not success:
                            async with session.get("https://www.tiktok.com/upload/", headers=headers) as resp:
                                if resp.status == 200:
                                    html = await resp.text()
                                    match_nick = re.search(r'"nickname"\s*:\s*"([^"]+)"', html)
                                    match_uname = re.search(r'"uniqueId"\s*:\s*"([^"]+)"', html)
                                    if match_nick:
                                        channel_name = match_nick.group(1)
                                        success = True
                                    elif match_uname:
                                        channel_name = match_uname.group(1)
                                        success = True
                                    else:
                                        error_msg = "TikTok session cookie invalid."
                                else:
                                    error_msg = f"Upload page HTTP {resp.status}"
        except Exception as e:
            error_msg = str(e)
            
        results.append({
            "idx": idx,
            "success": success,
            "channel_name": channel_name,
            "error": error_msg
        })
    return {"status": "success", "results": results}

@app.get("/api/monitored-channels", dependencies=[Depends(verify_api_key)])
async def get_monitored_channels():
    return database.get_monitored_channels()

class AddMonitoredChannel(BaseModel):
    platform: str
    url: str

@app.post("/api/monitored-channels", dependencies=[Depends(verify_api_key)])
async def add_monitored_channel(data: AddMonitoredChannel):
    try:
        channel_name, channel_id = await extract_channel_metadata(data.url, data.platform)
        success = database.add_monitored_channel(data.platform, data.url, channel_name, channel_id)
        if success:
            database.log_event("INFO", f"Added monitored channel {channel_name} via Web UI.")
            return {"status": "success", "channel_name": channel_name}
        else:
            return {"status": "failed", "error": "Channel already exists."}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

@app.delete("/api/monitored-channels/{id}", dependencies=[Depends(verify_api_key)])
async def delete_monitored_channel(id: int):
    database.delete_monitored_channel(id)
    database.log_event("INFO", f"Deleted monitored channel ID {id} via Web UI.")
    return {"status": "success"}

@app.get("/api/destination-channels", dependencies=[Depends(verify_api_key)])
async def get_destination_channels():
    return database.get_destination_channels()

@app.delete("/api/destination-channels/{id}", dependencies=[Depends(verify_api_key)])
async def delete_destination_channel(id: int):
    database.delete_destination_channel(id)
    database.log_event("INFO", f"Deleted destination channel ID {id} via Web UI.")
    return {"status": "success"}

@app.get("/api/mappings/{monitored_id}", dependencies=[Depends(verify_api_key)])
async def get_mappings(monitored_id: int):
    return database.get_channel_mappings(monitored_id)

class UpdateMapping(BaseModel):
    destination_ids: list[int]

@app.post("/api/mappings/{monitored_id}", dependencies=[Depends(verify_api_key)])
async def update_mappings(monitored_id: int, data: UpdateMapping):
    database.save_channel_mappings(monitored_id, data.destination_ids)
    database.log_event("INFO", f"Updated mappings for monitored channel ID {monitored_id} via Web UI.")
    return {"status": "success"}

@app.get("/api/reup-settings", dependencies=[Depends(verify_api_key)])
async def get_reup_settings():
    return database.get_reup_settings()

@app.post("/api/reup-settings", dependencies=[Depends(verify_api_key)])
async def update_reup_settings(settings: dict):
    database.save_reup_settings(settings)
    database.log_event("INFO", "Updated Reup Settings via Web UI.")
    return {"status": "success"}

@app.get("/api/music", dependencies=[Depends(verify_api_key)])
async def get_music():
    return database.get_music_files()

@app.post("/api/music", dependencies=[Depends(verify_api_key)])
async def upload_music(file: UploadFile = File(...)):
    filename = file.filename
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    target_path = config.MUSIC_DIR / filename
    
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size = target_path.stat().st_size
    success = database.add_music_file(filename, filename, file_size)
    if success:
        database.log_event("INFO", f"Uploaded music file {filename} via Web UI.")
        return {"status": "success", "filename": filename}
    else:
        return {"status": "success", "filename": filename, "note": "file already in library DB"}

@app.delete("/api/music/{id}", dependencies=[Depends(verify_api_key)])
async def delete_music(id: int):
    music_files = database.get_music_files()
    target = next((m for m in music_files if m['id'] == id), None)
    if target:
        filepath = config.MUSIC_DIR / target['filename']
        try:
            if filepath.exists():
                filepath.unlink()
        except Exception as e:
            logger.error(f"Failed to delete music file from disk: {e}")
        database.delete_music_file(id)
        database.log_event("INFO", f"Deleted music file {target['filename']} via Web UI.")
        return {"status": "success"}
    else:
        return {"status": "failed", "error": "Music file not found"}

@app.get("/api/system-settings", dependencies=[Depends(verify_api_key)])
async def get_system_settings():
    return {
        "ping_alive_enabled": database.get_setting("ping_alive_enabled") == "true",
        "ping_chat_id": database.get_setting("ping_chat_id", ""),
        "backup_bot_token": database.get_setting("backup_bot_token", ""),
        "backup_chat_id": database.get_setting("backup_chat_id", ""),
        "keep_awake_url": database.get_setting("keep_awake_url", "")
    }

@app.post("/api/system-settings", dependencies=[Depends(verify_api_key)])
async def update_system_settings(settings: dict):
    for key, value in settings.items():
        if isinstance(value, bool):
            value_str = "true" if value else "false"
        else:
            value_str = str(value)
        database.set_setting(key, value_str)
    database.log_event("INFO", "Updated System Settings via Web UI.")
    return {"status": "success"}

class ManualScanRequest(BaseModel):
    channel_id: int
    scan_type: str = 'all'

@app.post("/api/manual/scan", dependencies=[Depends(verify_api_key)])
async def manual_scan(data: ManualScanRequest):
    monitored_channels = database.get_monitored_channels()
    mon_chan = next((c for c in monitored_channels if c['id'] == data.channel_id), None)
    if not mon_chan:
        raise HTTPException(status_code=404, detail="Monitored channel not found")
        
    limit = 1 if data.scan_type == 'latest' else None
    videos = await fetch_channel_videos(mon_chan['url'], limit=limit, scan_type=data.scan_type)
    return {"status": "success", "videos": videos}

class ManualProcessRequest(BaseModel):
    video_url: str
    video_title: str
    video_id: str
    destination_ids: list[int]

manual_tasks_progress = {}

@app.post("/api/manual/process", dependencies=[Depends(verify_api_key)])
async def manual_process(data: ManualProcessRequest):
    task_id = f"manual_{int(time.time())}"
    manual_tasks_progress[task_id] = {
        "status": "processing",
        "percent": 0,
        "step": "Initializing...",
        "error": None
    }
    
    async def progress_cb(percent, step):
        manual_tasks_progress[task_id]["percent"] = percent
        manual_tasks_progress[task_id]["step"] = step
        
    async def run_pipeline():
        from backend.processor import process_video_pipeline
        try:
            result = await process_video_pipeline(
                video_url=data.video_url,
                video_title=data.video_title,
                video_id=data.video_id,
                monitored_channel_id=None,
                destination_ids=data.destination_ids,
                progress_callback=progress_cb
            )
            if result:
                manual_tasks_progress[task_id]["status"] = "completed"
                manual_tasks_progress[task_id]["percent"] = 100
                manual_tasks_progress[task_id]["step"] = "Done"
            else:
                manual_tasks_progress[task_id]["status"] = "failed"
                manual_tasks_progress[task_id]["step"] = "Failed"
        except Exception as e:
            manual_tasks_progress[task_id]["status"] = "failed"
            manual_tasks_progress[task_id]["error"] = str(e)
            
    asyncio.create_task(run_pipeline())
    return {"status": "success", "task_id": task_id}

@app.get("/api/manual/process/{task_id}", dependencies=[Depends(verify_api_key)])
async def get_manual_process_status(task_id: str):
    if task_id not in manual_tasks_progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return manual_tasks_progress[task_id]

# ==================== AUTO QUEUE API ENDPOINTS ====================

@app.get("/api/queue", dependencies=[Depends(verify_api_key)])
async def get_video_queue():
    conn = database.get_db_connection()
    try:
        # Get all video queue items with source channel name and platform
        queue_rows = conn.execute("""
            SELECT q.id, q.monitored_channel_id, q.video_id, q.title, q.url, q.status, q.attempts, q.error_msg, q.created_at,
                   m.channel_name as source_channel_name, m.platform as source_platform
            FROM video_queue q
            LEFT JOIN monitored_channels m ON q.monitored_channel_id = m.id
            ORDER BY q.created_at DESC
        """).fetchall()
        
        # Get upload history with destination channel name and platform
        history_rows = conn.execute("""
            SELECT h.id, h.video_queue_id, h.destination_channel_id, h.status, h.video_url_or_id, h.error_msg, h.uploaded_at,
                   d.channel_name as dest_channel_name, d.platform as dest_platform
            FROM upload_history h
            LEFT JOIN destination_channels d ON h.destination_channel_id = d.id
            ORDER BY h.uploaded_at ASC
        """).fetchall()
        
        # Format output
        queue_list = []
        for row in queue_rows:
            item = dict(row)
            # Filter history entries for this video (match string IDs)
            item_history = []
            for hist in history_rows:
                if str(hist['video_queue_id']) == str(row['video_id']):
                    item_history.append(dict(hist))
            item['uploads'] = item_history
            queue_list.append(item)
            
        return queue_list
    except Exception as e:
        logger.error(f"Error fetching video queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/queue/{id}/retry", dependencies=[Depends(verify_api_key)])
async def retry_queue_item(id: int):
    conn = database.get_db_connection()
    try:
        row = conn.execute("SELECT * FROM video_queue WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Queue item not found")
        
        # Reset status
        conn.execute("UPDATE video_queue SET status = 'pending', attempts = 0, error_msg = NULL WHERE id = ?", (id,))
        # Delete previous upload histories for this item so we start clean
        conn.execute("DELETE FROM upload_history WHERE video_queue_id = ?", (row['video_id'],))
        conn.commit()
        
        database.log_event("INFO", f"Queued video '{row['title']}' for retry via Web UI.")
        
        # Trigger the scheduler queue worker
        from backend.scheduler import process_pending_queue_worker
        asyncio.create_task(process_pending_queue_worker())
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error retrying queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/queue/{id}", dependencies=[Depends(verify_api_key)])
async def delete_queue_item(id: int):
    conn = database.get_db_connection()
    try:
        row = conn.execute("SELECT * FROM video_queue WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Queue item not found")
        
        conn.execute("DELETE FROM video_queue WHERE id = ?", (id,))
        conn.execute("DELETE FROM upload_history WHERE video_queue_id = ?", (row['video_id'],))
        conn.commit()
        
        database.log_event("INFO", f"Deleted video '{row['title']}' from queue via Web UI.")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/queue", dependencies=[Depends(verify_api_key)])
async def clear_queue(status: str = None):
    conn = database.get_db_connection()
    try:
        if status:
            if status not in ('pending', 'processing', 'completed', 'failed'):
                raise HTTPException(status_code=400, detail="Invalid status filter")
                
            # Get video_ids for items to delete
            rows = conn.execute("SELECT video_id FROM video_queue WHERE status = ?", (status,)).fetchall()
            video_ids = [r['video_id'] for r in rows]
            
            if video_ids:
                conn.execute("DELETE FROM video_queue WHERE status = ?", (status,))
                # Delete related upload history using parameter list
                placeholders = ",".join("?" for _ in video_ids)
                conn.execute(f"DELETE FROM upload_history WHERE video_queue_id IN ({placeholders})", video_ids)
                
            database.log_event("INFO", f"Cleared queue items with status '{status}' via Web UI.")
        else:
            conn.execute("DELETE FROM video_queue")
            conn.execute("DELETE FROM upload_history")
            database.log_event("INFO", "Cleared entire video queue and history via Web UI.")
            
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error clearing queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ==================== VIRTUAL BROWSER QUICK LOGIN ====================

import uuid
import time
import io
from fastapi.responses import StreamingResponse

class BrowserSession:
    def __init__(self, platform: str):
        self.id = str(uuid.uuid4())
        self.platform = platform
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.last_active = time.time()
        self.status = "initializing"
        self.error = None

    async def start(self):
        from playwright.async_api import async_playwright
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            self.context = await self.browser.new_context(
                viewport={"width": 1024, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            self.page = await self.context.new_page()
            
            # Stealth script overrides
            await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            if self.platform == 'tiktok':
                await self.page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=60000)
            elif self.platform == 'facebook':
                await self.page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=60000)
                
            self.status = "active"
            self.last_active = time.time()
        except Exception as e:
            self.status = "failed"
            self.error = str(e)
            await self.close()
            raise e

    async def get_screenshot(self) -> bytes:
        self.last_active = time.time()
        return await self.page.screenshot(type="jpeg", quality=75)

    async def click(self, x_pct: float, y_pct: float):
        self.last_active = time.time()
        x = int(x_pct * 1024)
        y = int(y_pct * 768)
        await self.page.mouse.click(x, y)

    async def type(self, text: str):
        self.last_active = time.time()
        await self.page.keyboard.type(text)

    async def press_key(self, key: str):
        self.last_active = time.time()
        await self.page.keyboard.press(key)

    async def reload(self):
        self.last_active = time.time()
        await self.page.reload(wait_until="domcontentloaded")

    async def check_login(self) -> dict:
        self.last_active = time.time()
        cookies = await self.context.cookies()
        
        if self.platform == 'tiktok':
            sessionid_cookie = next((c for c in cookies if c['name'] in ('sessionid', 'sessionid_ss')), None)
            if sessionid_cookie:
                val = sessionid_cookie['value']
                # Save plain session ID
                database.save_api_token('tiktok', val)
                database.log_event("INFO", "Successfully captured TikTok session cookie via Quick Login!")
                
                # Auto discover destinations
                asyncio.create_task(auto_discover_destinations('tiktok', val))
                return {"logged_in": True, "cookie_name": sessionid_cookie['name'], "url": self.page.url}
                
        elif self.platform == 'facebook':
            c_user = next((c for c in cookies if c['name'] == 'c_user'), None)
            xs = next((c for c in cookies if c['name'] == 'xs'), None)
            if c_user and xs:
                # Save all cookies as JSON for scraper
                import json
                cookie_str = json.dumps(cookies)
                database.save_api_token('facebook_cookies', cookie_str)
                database.log_event("INFO", "Successfully captured Facebook cookies for Playwright scraper via Quick Login!")
                return {"logged_in": True, "cookie_name": "c_user & xs", "url": self.page.url}
                
        return {"logged_in": False, "url": self.page.url}

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        except: pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except: pass
        self.status = "closed"

active_browser_sessions = {}

def cleanup_old_sessions():
    now = time.time()
    to_delete = []
    for sid, sess in active_browser_sessions.items():
        if now - sess.last_active > 300: # 5 minutes
            to_delete.append(sid)
            
    for sid in to_delete:
        sess = active_browser_sessions.pop(sid, None)
        if sess:
            asyncio.create_task(sess.close())

# API models
class BrowserStartRequest(BaseModel):
    platform: str

class BrowserClickRequest(BaseModel):
    x_pct: float
    y_pct: float

class BrowserTypeRequest(BaseModel):
    text: str

class BrowserPressRequest(BaseModel):
    key: str

@app.post("/api/browser/start", dependencies=[Depends(verify_api_key)])
async def api_browser_start(data: BrowserStartRequest):
    cleanup_old_sessions()
    
    if data.platform not in ('tiktok', 'facebook'):
        raise HTTPException(status_code=400, detail="Unsupported platform for quick login")
        
    session = BrowserSession(data.platform)
    active_browser_sessions[session.id] = session
    
    try:
        await session.start()
        return {"status": "success", "session_id": session.id}
    except Exception as e:
        active_browser_sessions.pop(session.id, None)
        raise HTTPException(status_code=500, detail=f"Failed to start browser session: {e}")

@app.get("/api/browser/screenshot/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_screenshot(session_id: str):
    session = active_browser_sessions.get(session_id)
    if not session or session.status != "active":
        raise HTTPException(status_code=404, detail="Active browser session not found")
        
    try:
        img_bytes = await session.get_screenshot()
        return StreamingResponse(io.BytesIO(img_bytes), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/browser/click/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_click(session_id: str, data: BrowserClickRequest):
    session = active_browser_sessions.get(session_id)
    if not session or session.status != "active":
        raise HTTPException(status_code=404, detail="Active browser session not found")
        
    try:
        await session.click(data.x_pct, data.y_pct)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/browser/type/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_type(session_id: str, data: BrowserTypeRequest):
    session = active_browser_sessions.get(session_id)
    if not session or session.status != "active":
        raise HTTPException(status_code=404, detail="Active browser session not found")
        
    try:
        await session.type(data.text)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/browser/press/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_press(session_id: str, data: BrowserPressRequest):
    session = active_browser_sessions.get(session_id)
    if not session or session.status != "active":
        raise HTTPException(status_code=404, detail="Active browser session not found")
        
    try:
        if data.key == "Reload":
            await session.reload()
        else:
            await session.press_key(data.key)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/browser/status/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_status(session_id: str):
    session = active_browser_sessions.get(session_id)
    if not session or session.status != "active":
        raise HTTPException(status_code=404, detail="Active browser session not found")
        
    try:
        result = await session.check_login()
        if result.get("logged_in"):
            # Close session
            active_browser_sessions.pop(session_id, None)
            asyncio.create_task(session.close())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/browser/stop/{session_id}", dependencies=[Depends(verify_api_key)])
async def api_browser_stop(session_id: str):
    session = active_browser_sessions.pop(session_id, None)
    if not session:
        return {"status": "success", "note": "session already closed"}
        
    try:
        await session.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
