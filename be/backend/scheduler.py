import logging
import asyncio
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database
import config
from backend.processor import process_video_pipeline, send_system_notification, fetch_channel_videos

logger = logging.getLogger(__name__)

# Initialize APScheduler
scheduler = AsyncIOScheduler()
queue_lock = asyncio.Lock()

# Queue worker that processes pending videos sequentially
async def process_pending_queue_worker():
    """
    Checks for pending video_queue items and runs them one by one.
    Uses a Lock to prevent multiple concurrent worker processes.
    """
    if queue_lock.locked():
        logger.info("Queue worker is already running. Skipping execution.")
        return
        
    async with queue_lock:
        pending_videos = database.get_pending_videos()
        if not pending_videos:
            return
            
        logger.info(f"Found {len(pending_videos)} pending videos in queue. Processing...")
        
        for video in pending_videos:
            # Check if auto mode is still enabled
            if database.get_setting("auto_mode_enabled") != "true":
                logger.info("Auto Mode was disabled. Stopping queue worker.")
                break
                
            monitored_id = video['monitored_channel_id']
            # Get mapped destinations
            dest_ids = database.get_channel_mappings(monitored_id)
            
            if not dest_ids:
                logger.info(f"No destination channels mapped for video {video['title']}. Skipping.")
                database.update_video_queue_status(video['id'], 'completed', "No destinations mapped.")
                continue
                
            database.update_video_queue_status(video['id'], 'processing')
            
            # Execute pipeline
            success = await process_video_pipeline(
                video_url=video['url'],
                video_title=video['title'],
                video_id=video['video_id'],
                monitored_channel_id=monitored_id,
                destination_ids=dest_ids
            )
            
            if success:
                database.update_video_queue_status(video['id'], 'completed')
                logger.info(f"Successfully processed queued video: {video['title']}")
            else:
                database.update_video_queue_status(video['id'], 'failed', "Pipeline execution failed.")
                logger.error(f"Failed to process queued video: {video['title']}")
                
            # Post-reup DB backup to Telegram removed
            pass
                
            # Delay between videos to cooldown system resources (Hugging Face limits)
            await asyncio.sleep(10)

# Main scan job
async def scan_monitored_channels_job():
    """
    Scans all monitored channels for new videos.
    If new videos are found, they are added to the video queue.
    """
    logger.info("Scanning monitored channels for new videos...")
    monitored_channels = database.get_monitored_channels()
    
    if not monitored_channels:
        logger.info("No channels configured to monitor.")
        return
        
    loop = asyncio.get_running_loop()
    
    for channel in monitored_channels:
        logger.info(f"Scanning channel: {channel['channel_name']} ({channel['platform']})")
        # Fetch latest 5 videos using flat extraction (fast)
        videos = await fetch_channel_videos(channel['url'], 5)
        
        new_vids_count = 0
        for vid in videos:
            # Try to add to queue. Standardizes on video_id uniqueness constraint.
            added = database.add_video_to_queue(
                monitored_id=channel['id'],
                video_id=vid['id'],
                title=vid['title'],
                url=vid['url']
            )
            if added:
                new_vids_count += 1
                logger.info(f"New video detected: {vid['title']}")
                await send_system_notification(
                    _t=None or f"✅ Phát hiện video mới từ kênh {channel['channel_name']}:\n{vid['title']}\nURL: {vid['url']}"
                )
                
        if new_vids_count > 0:
            logger.info(f"Added {new_vids_count} new videos to queue for {channel['channel_name']}.")
            
    # Trigger queue processing worker
    asyncio.create_task(process_pending_queue_worker())

# Keep-awake job
async def keep_awake_job():
    """
    Simulates user activity by launching Playwright to visit the dashboard URL
    and clicking on the page, preventing Hugging Face Spaces hibernation.
    """
    url = database.get_setting("keep_awake_url")
    if not url:
        space_id = os.getenv("HF_SPACE_ID") # e.g. "username/space-name"
        if space_id and '/' in space_id:
            user, space = space_id.split('/')
            space_clean = space.replace('_', '-').replace('.', '-')
            url = f"https://{user}-{space_clean}.hf.space"
            
    if not url:
        logger.info("Keep-awake URL not configured and HF_SPACE_ID not found. Skipping auto-click keep-awake.")
        return
        
    logger.info(f"Starting auto-click keep-awake for URL: {url}")
    from playwright.async_api import async_playwright
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            # Click the body to simulate interaction
            await page.click("body")
            await asyncio.sleep(1)
            logger.info("Auto-click keep-awake visit completed successfully.")
    except Exception as e:
        logger.error(f"Auto-click keep-awake failed: {e}")
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

# Scheduler controls
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")
        
    # Read scan interval
    interval_str = database.get_setting("scan_interval", "01:00:00")
    hours, minutes, seconds = map(int, interval_str.split(":"))
    
    # Remove existing jobs if any
    if scheduler.get_job("scan_job"):
        scheduler.remove_job("scan_job")
    if scheduler.get_job("keep_awake_job"):
        scheduler.remove_job("keep_awake_job")
        
    scheduler.add_job(
        scan_monitored_channels_job,
        "interval",
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        id="scan_job",
        next_run_time=datetime.now() # trigger immediately on start
    )
    logger.info(f"Scheduled scan job with interval: {interval_str}")
    
    # Schedule keep-awake job to run every 15 minutes
    scheduler.add_job(
        keep_awake_job,
        "interval",
        minutes=15,
        id="keep_awake_job",
        next_run_time=datetime.now()
    )
    logger.info("Scheduled keep-awake job with interval: 15 minutes")

def stop_scheduler():
    if scheduler.get_job("scan_job"):
        scheduler.remove_job("scan_job")
        logger.info("Scan job unscheduled.")
    if scheduler.get_job("keep_awake_job"):
        scheduler.remove_job("keep_awake_job")
        logger.info("Keep-awake job unscheduled.")

async def restart_scheduler():
    logger.info("Restarting scheduler due to configuration change.")
    stop_scheduler()
    start_scheduler()
