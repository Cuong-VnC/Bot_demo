import os
from pathlib import Path

# Base Directory
BASE_DIR = Path(__file__).resolve().parent

# Environment settings
PORT = int(os.getenv("PORT", "7860"))

# API authentication key for Frontend communication
API_KEY = os.getenv("BACKEND_API_KEY", "reup-automation-secret-key")

# Check if running in Docker / Hugging Face Spaces (which typically sets HOME or runs in specific paths)
IS_DOCKER = os.path.exists("/app") or os.getenv("HF_SPACE_ID") is not None

# Directories
DATA_DIR = Path("/app/data") if IS_DOCKER else BASE_DIR / "data"
MUSIC_DIR = Path("/app/music_library") if IS_DOCKER else BASE_DIR / "music_library"
TEMP_DIR = Path("/app/temp") if IS_DOCKER else BASE_DIR / "temp"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "database.db"

# Public Access Check (for debugging)
SPACE_ID = os.getenv("SPACE_ID")
SPACE_HOST = f"{SPACE_ID}.hf.space" if SPACE_ID else None
