import os
import random
import logging
import asyncio
import subprocess
import json
import shutil
import yt_dlp
import re
import math
import aiohttp
from pathlib import Path
from datetime import datetime
import config
import database
from backend.uploaders import upload_to_youtube, upload_to_facebook, upload_to_tiktok

logger = logging.getLogger(__name__)

# Helper to send system alerts (was Telegram, now logger)
async def send_system_notification(text: str):
    logger.info(f"[Notification] {text}")

# Check disk storage warning
def check_disk_space():
    total, used, free = shutil.disk_usage("/")
    # Check if free space is less than 2GB (2 * 1024 * 1024 * 1024 bytes)
    if free < 2 * 1024 * 1024 * 1024:
        pass

# Get video duration using ffprobe
async def get_video_duration(filepath: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return float(stdout.decode().strip())
    except Exception as e:
        logger.error(f"ffprobe duration extract failed: {e}")
    return 0.0

# Check if video has audio stream using ffprobe
async def check_audio_stream(filepath: str) -> bool:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
        "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0 and stdout.decode().strip() == "audio":
            return True
    except Exception as e:
        logger.error(f"ffprobe audio check failed: {e}")
    return False

# Fetch latest videos from a channel
async def fetch_channel_videos(url, limit=30, scan_type='all'):
    if 'tiktok.com' in url:
        from backend.playwright_scraper import scrape_tiktok_videos
        return await scrape_tiktok_videos(url, limit=limit)
    elif 'facebook.com' in url or 'fb.watch' in url:
        from backend.playwright_scraper import scrape_facebook_videos
        return await scrape_facebook_videos(url, limit=limit)
        
    def _extract():
        from urllib.parse import urlparse, urlunparse
        
        is_youtube = 'youtube.com' in url or 'youtu.be' in url
        
        # Adjust URL for YouTube channel tabs
        if is_youtube and scan_type in ('long', 'short'):
            try:
                parsed = urlparse(url)
                path = parsed.path.rstrip('/')
                if path.endswith('/videos'):
                    path = path[:-7]
                elif path.endswith('/shorts'):
                    path = path[:-7]
                    
                if scan_type == 'long':
                    path = f"{path}/videos"
                elif scan_type == 'short':
                    path = f"{path}/shorts"
                    
                scan_url = urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))
            except Exception as url_err:
                logger.error(f"Failed to parse and adjust YouTube URL: {url_err}")
                scan_url = url
        else:
            scan_url = url

        ydl_opts = {
            'extract_flat': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'sleep_interval': 1,
            'max_sleep_interval': 3,
        }
        if limit is not None:
            ydl_opts['playlistend'] = limit
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(scan_url, download=False)
                if not info:
                    return []
                entries = info.get('entries', [])
                videos = []
                
                # Counter for valid videos added
                valid_idx = 1
                for e in entries:
                    if e:
                        # Filter out private/deleted videos or channel tabs that aren't videos
                        title = e.get('title') or "No Title"
                        if title in ('[Private video]', '[Deleted video]'):
                            continue
                            
                        video_id = e.get('id')
                        
                        # For YouTube, enforce 11-char video ID constraint to skip related channels / tabs
                        if is_youtube:
                            if not video_id or len(video_id) != 11:
                                continue
                                
                        video_url = e.get('url')
                        # Standardize YouTube URLs if id present
                        if video_id and is_youtube:
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                        elif not video_url:
                            video_url = scan_url
                            
                        videos.append({
                            'index': valid_idx,
                            'title': title,
                            'url': video_url,
                            'id': video_id or video_url
                        })
                        valid_idx += 1
                return videos
            except Exception as e:
                logger.error(f"Error fetching channel videos: {e}")
                return []

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract)

# Build atempo filter chain for audio speed adjustment
def get_atempo_filter(speed: float) -> str:
    if speed == 1.0:
        return ""
    filters = []
    curr = speed
    while curr > 2.0:
        filters.append("atempo=2.0")
        curr /= 2.0
    while curr < 0.5:
        filters.append("atempo=0.5")
        curr /= 0.5
    filters.append(f"atempo={curr}")
    return ",".join(filters)

# Build audio speed + pitch adjustment filter
def get_audio_filter(speed: float, pitch_enabled: bool, pitch_factor: float) -> str:
    if not pitch_enabled or pitch_factor == 1.0:
        return get_atempo_filter(speed)
        
    # Pitch shift using asetrate
    filters = [f"asetrate=44100*{pitch_factor}"]
    
    # Compensate duration using atempo to reach final target speed
    comp_speed = speed / pitch_factor
    curr = comp_speed
    atempo_parts = []
    while curr > 2.0:
        atempo_parts.append("atempo=2.0")
        curr /= 2.0
    while curr < 0.5:
        atempo_parts.append("atempo=0.5")
        curr /= 0.5
    atempo_parts.append(f"atempo={curr}")
    
    filters.extend(atempo_parts)
    filters.append("aresample=44100")
    return ",".join(filters)

# Helper to send notifications and backup videos to a secondary Telegram Bot removed
async def upload_to_backup_bot(filepath: str, title: str, message_text: str):
    pass

# Models for Google AI Studio and Groq
GEMINI_MODELS = [
    'gemini-3.5-flash',
    'gemini-3.1-flash-lite',
    'gemini-3-flash-preview',
    'gemini-3.1-pro-preview',
    'gemini-pro-latest',
    'gemini-flash-latest',
    'gemini-flash-lite-latest',
    'gemma-4-26b-a4b-it',
    'gemma-4-31b-it'
]

GROQ_MODELS = [
    "llama3-8b-8192",
    "llama3-70b-8192",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
]

import time
cooldowns = {}

def is_cooldown(platform, key, model):
    key_str = str(key) if isinstance(key, dict) else key
    ts = cooldowns.get((platform, key_str, model), 0)
    return time.time() < ts

def set_cooldown(platform, key, model, duration=60):
    key_str = str(key) if isinstance(key, dict) else key
    cooldowns[(platform, key_str, model)] = time.time() + duration

async def extract_title_and_hashtags(video_url: str) -> tuple[str, list[str]]:
    """
    Extracts video title and hashtags from the video description/title using yt-dlp metadata.
    """
    def _extract():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get('title') or ""
            description = info.get('description') or ""
            text = title + " " + description
            # Extract hashtags
            hashtags = re.findall(r'#\w+', text)
            clean_hashtags = list(set([h.strip() for h in hashtags if h.strip()]))
            
            # Clean title by removing hashtags
            clean_title = re.sub(r'#\w+', '', title).strip()
            clean_title = re.sub(r'\s+', ' ', clean_title)
            if not clean_title:
                clean_title = title
            return clean_title, clean_hashtags
            
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _extract)
    except Exception as e:
        logger.error(f"Failed to extract title/hashtags using yt-dlp: {e}")
        return "Video", []

# Metadata rewrite using Gemini or Groq
async def rewrite_metadata(title: str, hashtags: list[str]) -> dict:
    reup = database.get_reup_settings()
    platform = reup.get('metadata_rewrite_platform', 'google_ai_studio')
    tokens_list = database.get_api_tokens_list(platform)
    
    rewritten = {"title": title, "hashtags": hashtags}
    if not tokens_list:
        logger.info(f"Metadata rewrite skipped: API Token for {platform} not set.")
        return rewritten
        
    prompt = f"""
You are a professional video editor and social media optimizer.
Rewrite the video title and hashtags below.
Rules:
1. The meaning of the title must remain unchanged, but it must be highly engaging, click-inducing, and optimized for search SEO to increase Click-Through Rate (CTR).
2. Generate a list of relevant, viral hashtags. You can keep/adapt the original hashtags or add new relevant ones.
3. Provide the output ONLY as a JSON string containing the keys 'title' (string) and 'hashtags' (list of strings).
4. Do not include any formatting, markdown blocks (like ```json), or explanatory notes.

Original Title: {title}
Original Hashtags: {', '.join(hashtags)}
"""
    
    loop = asyncio.get_running_loop()
    models = GEMINI_MODELS if platform == 'google_ai_studio' else GROQ_MODELS
    
    success = False
    for token in tokens_list:
        if success:
            break
        for model in models:
            if is_cooldown(platform, token, model):
                continue
                
            try:
                txt = None
                if platform == 'google_ai_studio':
                    from google import genai
                    # Google AI Studio token could be string or dict
                    api_key = token
                    if isinstance(token, dict) and 'api_key' in token:
                        api_key = token['api_key']
                    elif isinstance(token, dict):
                        api_key = list(token.values())[0] if token else ""
                        
                    client = genai.Client(api_key=str(api_key))
                    response = await loop.run_in_executor(None, lambda: client.models.generate_content(
                        model=model,
                        contents=prompt,
                    ))
                    txt = response.text
                elif platform == 'groq':
                    from groq import Groq
                    api_key = token
                    if isinstance(token, dict) and 'api_key' in token:
                        api_key = token['api_key']
                    elif isinstance(token, dict):
                        api_key = list(token.values())[0] if token else ""
                        
                    client = Groq(api_key=str(api_key))
                    chat_completion = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=400
                    ))
                    txt = chat_completion.choices[0].message.content
                
                if txt:
                    txt = txt.strip()
                    if txt.startswith("```json"):
                        txt = txt[7:]
                    if txt.endswith("```"):
                        txt = txt[:-3]
                    txt = txt.strip()
                    parsed = json.loads(txt)
                    if 'title' in parsed and 'hashtags' in parsed:
                        rewritten = parsed
                        success = True
                        logger.info(f"AI metadata rewrite successful using model: {model}")
                        break
            except Exception as api_err:
                err_str = str(api_err).lower()
                # Check if rate limited
                if any(x in err_str for x in ("rate limit", "429", "quota", "resource exhausted", "limit exceeded")):
                    logger.warning(f"Rate limit hit for platform {platform}, model {model}: {api_err}. Setting cooldown.")
                    set_cooldown(platform, token, model, duration=300)
                else:
                    logger.error(f"API call failed with platform {platform}, model {model}: {api_err}")
                    
    return rewritten

# Single video processing orchestrator pipeline
async def process_video_pipeline(
    video_url: str,
    video_title: str,
    video_id: str,
    monitored_channel_id=None,
    destination_ids=None,
    progress_callback=None
) -> bool:
    """
    Core pipeline: Download -> Metadata Rewrite -> Segment splitting -> FFmpeg Render -> Telegram Storage -> Backup Bot -> Uploads.
    """
    check_disk_space()
    
    # Generate unique download path
    timestamp = int(datetime.now().timestamp())
    download_path = config.TEMP_DIR / f"dl_{video_id}_{timestamp}.mp4"
    
    if destination_ids is None:
        destination_ids = []
        
    try:
        # Step 1: Download
        if progress_callback:
            await progress_callback(10, "Downloading video...")
        await send_system_notification(f"⬇️ Bắt đầu tải video:\n{video_title}\nURL: {video_url}")
        
        # Run yt-dlp downloader
        ydl_opts = {
            'outtmpl': str(download_path),
            'format': 'mp4/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
        }
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([video_url]))
        
        if not download_path.exists():
            raise Exception("Download failed, output file not created.")
            
        # Step 2: Probing video specs
        duration = await get_video_duration(str(download_path))
        has_audio = await check_audio_stream(str(download_path))
        
        # Load Reup Settings
        reup = database.get_reup_settings()
        speed = float(reup.get('speed', '1.0'))
        flip_horizontal = reup.get('flip_horizontal') == 'true'
        intro_cut = float(reup.get('intro_cut', '0.0'))
        outro_cut = float(reup.get('outro_cut', '0.0'))
        zoom = float(reup.get('zoom', '1.0'))
        bg_music_enabled = reup.get('bg_music_enabled') == 'true'
        music_volume = float(reup.get('music_volume', '0.5'))
        
        # Anti-copyright settings
        copyright_pitch_enabled = reup.get('copyright_pitch_enabled', 'true') == 'true'
        copyright_pitch_factor = float(reup.get('copyright_pitch_factor', '1.02'))
        copyright_color_enabled = reup.get('copyright_color_enabled', 'true') == 'true'
        copyright_noise_enabled = reup.get('copyright_noise_enabled', 'true') == 'true'
        copyright_vignette_enabled = reup.get('copyright_vignette_enabled', 'true') == 'true'
        
        # Step 3: Metadata Extraction & Rewrite (Done once per video)
        if progress_callback:
            await progress_callback(30, "Extracting video metadata...")
        
        extracted_title, extracted_hashtags = await extract_title_and_hashtags(video_url)
        if not extracted_title:
            extracted_title = video_title
            
        if progress_callback:
            await progress_callback(35, "Rewriting metadata using AI...")
            
        meta = await rewrite_metadata(extracted_title, extracted_hashtags)
        final_title = meta.get('title', extracted_title)
        final_hashtags = meta.get('hashtags', extracted_hashtags)
        
        # Format hashtags string: e.g. "#funny #dog #viral"
        hashtags_str = " ".join([f"#{h}" if not h.startswith('#') else h for h in final_hashtags])
        
        # Calculate segments if video > 60s
        effective_duration = duration - intro_cut - outro_cut
        if effective_duration <= 0:
            raise Exception("Intro/Outro cut values exceed total video duration.")
            
        parts_to_process = []
        if effective_duration > 60.0:
            num_parts = math.ceil(effective_duration / 60.0)
            part_duration = effective_duration / num_parts
            for i in range(num_parts):
                start_time = intro_cut + (i * part_duration)
                parts_to_process.append((i + 1, start_time, part_duration))
            await send_system_notification(
                f"✂️ Video dài {effective_duration:.1f}s (>60s). Sẽ chia làm {num_parts} phần đều nhau, mỗi phần {part_duration:.1f}s."
            )
        else:
            parts_to_process.append((1, intro_cut, effective_duration))
            
        total_parts = len(parts_to_process)
        overall_success = True
        
        # Process each segment sequentially
        for part_num, start_time, part_dur in parts_to_process:
            part_timestamp = int(datetime.now().timestamp())
            processed_path = config.TEMP_DIR / f"proc_{video_id}_part{part_num}_{part_timestamp}.mp4"
            
            part_title = f"{final_title} (Phần {part_num})" if total_parts > 1 else final_title
            part_desc = f"{final_title} (Phần {part_num})\n\n{hashtags_str}" if total_parts > 1 else f"{final_title}\n\n{hashtags_str}"
            part_tags = [h.lstrip('#') for h in final_hashtags]
            
            # Compile FFmpeg Filters for this part
            if progress_callback:
                pct = int(40 + (part_num - 1) * (45 / total_parts))
                await progress_callback(pct, f"Applying filters for Part {part_num}...")
            
            await send_system_notification(f"⚙️ Bắt đầu xử lý FFmpeg cho {part_title}")
            
            # Check music file
            music_path = None
            if bg_music_enabled:
                music_files = database.get_music_files()
                if music_files:
                    selected_music = random.choice(music_files)
                    music_file_path = config.MUSIC_DIR / selected_music['filename']
                    if music_file_path.exists():
                        music_path = str(music_file_path)
            
            cmd = ["ffmpeg", "-y"]
            
            # Trimming for this specific segment
            cmd.extend(["-ss", f"{start_time:.3f}", "-t", f"{part_dur:.3f}", "-i", str(download_path)])
            
            if bg_music_enabled and music_path:
                cmd.extend(["-stream_loop", "-1", "-i", music_path])
                
            # Compile video filters
            vf_parts = []
            if speed != 1.0:
                vf_parts.append(f"setpts=1/{speed}*PTS")
            if flip_horizontal:
                vf_parts.append("hflip")
            if zoom != 1.0:
                vf_parts.append(f"crop=in_w/{zoom}:in_h/{zoom}")
            if copyright_color_enabled:
                vf_parts.append("eq=brightness=0.01:contrast=1.02:saturation=1.03")
            if copyright_noise_enabled:
                vf_parts.append("noise=alls=1:allf=t")
            if copyright_vignette_enabled:
                vf_parts.append("vignette=angle=0.05")
                
            # Audio & video mappings
            filter_complex = []
            if vf_parts:
                filter_complex.append(f"[0:v]{','.join(vf_parts)}[v]")
                video_map = "[v]"
            else:
                video_map = "0:v"
                
            audio_filter = get_audio_filter(speed, copyright_pitch_enabled, copyright_pitch_factor)
            
            if has_audio and bg_music_enabled and music_path:
                if audio_filter:
                    filter_complex.append(f"[0:a]{audio_filter}[orig_a]")
                    orig_a_ref = "[orig_a]"
                else:
                    orig_a_ref = "[0:a]"
                filter_complex.append(f"[1:a]volume={music_volume}[bg_a]")
                filter_complex.append(f"{orig_a_ref}[bg_a]amix=inputs=2:duration=first[a]")
                audio_map = "[a]"
            elif has_audio:
                if audio_filter:
                    filter_complex.append(f"[0:a]{audio_filter}[a]")
                    audio_map = "[a]"
                else:
                    audio_map = "0:a"
            elif bg_music_enabled and music_path:
                filter_complex.append(f"[1:a]volume={music_volume}[a]")
                audio_map = "[a]"
            else:
                audio_map = None
                
            if filter_complex:
                cmd.extend(["-filter_complex", ";".join(filter_complex)])
                cmd.extend(["-map", video_map])
                if audio_map:
                    cmd.extend(["-map", audio_map])
            else:
                cmd.extend(["-map", "0:v"])
                if has_audio:
                    cmd.extend(["-map", "0:a"])
                    
            # Add iPhone 15 Pro Max metadata and current creation time
            from datetime import timezone
            creation_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            cmd.extend([
                "-metadata", "make=Apple",
                "-metadata", "model=iPhone 15 Pro Max",
                "-metadata", "brand=Apple",
                "-metadata", "creation_time=" + creation_time_str,
                "-metadata", "encoder=com.apple.avfoundation",
                "-metadata:s:v:0", "handler_name=VideoHandler",
                "-metadata:s:a:0", "handler_name=AudioHandler"
            ])
            
            # Output codecs
            cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(processed_path)])
            
            # Execute FFmpeg Subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                err_log = stderr.decode()
                logger.error(f"FFmpeg render failed for part {part_num} with code {proc.returncode}: {err_log}")
                raise Exception(f"FFmpeg error: {err_log[:150]}")
                
            if not processed_path.exists():
                raise Exception(f"Processed file for part {part_num} not generated by FFmpeg.")
                
            # Step 5: Archive to Telegram Storage removed
            if progress_callback:
                pct = int(85 + (part_num - 1) * (5 / total_parts))
                await progress_callback(pct, f"Finished rendering part {part_num}...")
            
            # Step 5.5: Backup to Backup Bot removed
            
            # Step 6: Platform Uploads
            destinations = database.get_destination_channels()
            target_dests = [d for d in destinations if d['id'] in destination_ids]
            
            for dest in target_dests:
                platform = dest['platform'].lower()
                if progress_callback:
                    await progress_callback(90, f"Uploading Part {part_num} to {dest['channel_name']} ({platform.upper()})...")
                try:
                    upload_ref = ""
                    dest_creds = dest.get('credentials')
                    
                    if platform == 'youtube':
                        upload_ref = await upload_to_youtube(str(processed_path), part_title, part_desc, part_tags, credentials=dest_creds)
                    elif platform == 'facebook':
                        upload_ref = await upload_to_facebook(str(processed_path), part_title, part_desc, credentials=dest_creds)
                    elif platform == 'tiktok':
                        upload_ref = await upload_to_tiktok(str(processed_path), part_title, tags=part_tags, credentials=dest_creds)
                        
                    if platform == 'tiktok':
                        channel_id = dest.get('channel_id')
                        upload_ref_url = f"https://www.tiktok.com/@{channel_id}" if channel_id and channel_id != 'tiktok_user' else "https://www.tiktok.com/"
                    else:
                        upload_ref_url = upload_ref
                        
                    database.add_upload_history(
                        video_queue_id=video_id,
                        destination_channel_id=dest['id'],
                        status='success',
                        video_url_or_id=upload_ref_url
                    )
                except Exception as upload_err:
                    logger.error(f"Upload to {dest['channel_name']} failed: {upload_err}")
                    database.add_upload_history(
                        video_queue_id=video_id,
                        destination_channel_id=dest['id'],
                        status='failed',
                        error_msg=str(upload_err)
                    )
                    overall_success = False
            
            # Clean processed temp file for this segment
            try:
                if processed_path.exists():
                    processed_path.unlink()
            except Exception as clean_err:
                logger.error(f"Part temp file cleanup failed: {clean_err}")
                
        return overall_success
    except Exception as e:
        logger.error(f"Error in video processing pipeline: {e}")
        return False
    finally:
        # Clean downloaded file
        try:
            if download_path.exists():
                download_path.unlink()
        except Exception as clean_err:
            logger.error(f"Download temp file cleanup failed: {clean_err}")
