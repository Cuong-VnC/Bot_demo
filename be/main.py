import os
import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
import config
import database
from backend.app import app
from backend.scheduler import start_scheduler, stop_scheduler

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(config.DATA_DIR, "app.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # --- startup logic ---
    logger.info("Initializing application startup...")
    
    # Ensure database file exist and tables are created
    database.init_db()
    
    # Re-discover destination channels for configured platforms on startup
    from backend.app import auto_discover_destinations
    for platform in ['youtube', 'facebook', 'tiktok']:
        token = database.get_api_token(platform)
        if token:
            asyncio.create_task(auto_discover_destinations(platform, token))
    
    # Alert container restart
    database.log_event("INFO", "Application container started.")
            
    # Start APScheduler if enabled
    auto_mode_enabled = database.get_setting("auto_mode_enabled") == "true"
    if auto_mode_enabled:
        logger.info("Auto Mode is active. Launching background scheduler...")
        start_scheduler()
    else:
        logger.info("Auto Mode is inactive. Scheduler paused.")
        
    yield
    
    # --- shutdown logic ---
    logger.info("Shutting down application...")
    
    # Stop scheduler
    stop_scheduler()
    logger.info("Shutdown completed.")

# Apply lifespan context manager to the FastAPI application
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    logger.info(f"Starting server on port {config.PORT}...")
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
