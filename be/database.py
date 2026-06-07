import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
import config

logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 2. settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    # 3. api_tokens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_tokens (
        platform TEXT PRIMARY KEY,
        token_data TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 4. monitored_channels
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monitored_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        url TEXT UNIQUE,
        channel_name TEXT,
        channel_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 5. destination_channels
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS destination_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        channel_name TEXT,
        channel_id TEXT,
        credentials TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 6. channel_mapping
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_mapping (
        monitored_channel_id INTEGER,
        destination_channel_id INTEGER,
        PRIMARY KEY (monitored_channel_id, destination_channel_id)
    )""")
    
    # 7. reup_settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reup_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    # 8. music_library
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS music_library (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        file_id TEXT,
        file_size INTEGER
    )""")
    
    # 9. video_queue
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        monitored_channel_id INTEGER,
        video_id TEXT UNIQUE,
        title TEXT,
        url TEXT,
        status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0,
        error_msg TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 10. upload_history
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS upload_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_queue_id INTEGER,
        destination_channel_id INTEGER,
        status TEXT,
        video_url_or_id TEXT,
        error_msg TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # 11. logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Insert default settings if they don't exist
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('scan_interval', '01:00:00')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_mode_enabled', 'false')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_bot_token', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_chat_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ping_alive_enabled', 'false')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ping_chat_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('keep_awake_url', '')")
    
    # Default reup settings
    default_reup = [
        ('speed', '1.0'),
        ('flip_horizontal', 'false'),
        ('intro_cut', '0.0'),
        ('outro_cut', '0.0'),
        ('zoom', '1.0'),
        ('bg_music_enabled', 'false'),
        ('music_volume', '0.5'),
        ('metadata_rewrite_enabled', 'false'),
        ('metadata_rewrite_platform', 'google_ai_studio'),
        ('copyright_pitch_enabled', 'true'),
        ('copyright_pitch_factor', '1.02'),
        ('copyright_color_enabled', 'true'),
        ('copyright_noise_enabled', 'true'),
        ('copyright_vignette_enabled', 'true')
    ]
    for key, value in default_reup:
        cursor.execute("INSERT OR IGNORE INTO reup_settings (key, value) VALUES (?, ?)", (key, value))
        
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

# Users & Languages removed (previously used for Telegram bot)

# Settings Helpers
def get_setting(key, default=None):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# API Tokens
def parse_multiple_api_tokens(token_input: str) -> list:
    if not token_input:
        return []
    token_input = token_input.strip()
    
    # Try parsing the entire input as a JSON array or object
    try:
        parsed = json.loads(token_input)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass

    # Extract balanced JSON objects or arrays (for multi-line concatenated JSONs)
    extracted = []
    i = 0
    n = len(token_input)
    while i < n:
        char = token_input[i]
        if char in ('{', '['):
            start = i
            bracket_stack = [char]
            i += 1
            in_string = False
            escape = False
            while i < n and bracket_stack:
                c = token_input[i]
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = not in_string
                elif not in_string:
                    if c in ('{', '['):
                        bracket_stack.append(c)
                    elif c == '}':
                        if bracket_stack and bracket_stack[-1] == '{':
                            bracket_stack.pop()
                        else:
                            break
                    elif c == ']':
                        if bracket_stack and bracket_stack[-1] == '[':
                            bracket_stack.pop()
                        else:
                            break
                i += 1
            if not bracket_stack:
                candidate = token_input[start:i]
                try:
                    parsed_candidate = json.loads(candidate)
                    if isinstance(parsed_candidate, list):
                        extracted.extend(parsed_candidate)
                    else:
                        extracted.append(parsed_candidate)
                except Exception:
                    pass
            else:
                i = start + 1
        else:
            i += 1
            
    if extracted:
        return extracted
        
    # Fallback: split line-by-line
    lines = [line.strip() for line in token_input.split('\n') if line.strip()]
    parsed_items = []
    for line in lines:
        try:
            parsed_items.append(json.loads(line))
        except Exception:
            parsed_items.append(line)
    return parsed_items

def get_api_token(platform):
    conn = get_db_connection()
    row = conn.execute("SELECT token_data FROM api_tokens WHERE platform = ?", (platform,)).fetchone()
    conn.close()
    if row and row['token_data']:
        try:
            return json.loads(row['token_data'])
        except json.JSONDecodeError:
            return row['token_data']
    return None

def get_api_tokens_list(platform) -> list:
    tokens = get_api_token(platform)
    if not tokens:
        return []
    if isinstance(tokens, list):
        return tokens
    if isinstance(tokens, str):
        tokens_str = tokens.strip()
        if tokens_str.startswith('[') and tokens_str.endswith(']'):
            try:
                return json.loads(tokens_str)
            except:
                pass
        if tokens_str.startswith('{') and tokens_str.endswith('}'):
            try:
                return [json.loads(tokens_str)]
            except:
                pass
        return [t.strip() for t in tokens_str.split('\n') if t.strip()]
    if isinstance(tokens, dict):
        return [tokens]
    return [tokens]

def save_api_token(platform, token_data):
    conn = get_db_connection()
    data_str = json.dumps(token_data) if isinstance(token_data, (dict, list)) else str(token_data)
    conn.execute("INSERT OR REPLACE INTO api_tokens (platform, token_data, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (platform, data_str))
    conn.commit()
    conn.close()

def delete_api_token(platform):
    conn = get_db_connection()
    # Delete channel mappings for destination channels on this platform
    conn.execute("""
        DELETE FROM channel_mapping 
        WHERE destination_channel_id IN (
            SELECT id FROM destination_channels WHERE platform = ?
        )
    """, (platform,))
    # Delete destination channels
    conn.execute("DELETE FROM destination_channels WHERE platform = ?", (platform,))
    # Delete api token
    conn.execute("DELETE FROM api_tokens WHERE platform = ?", (platform,))
    conn.commit()
    conn.close()

# Monitored Channels
def get_monitored_channels():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM monitored_channels").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_monitored_channel(platform, url, channel_name, channel_id):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO monitored_channels (platform, url, channel_name, channel_id) VALUES (?, ?, ?, ?)",
                     (platform, url, channel_name, channel_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_monitored_channel(channel_id):
    conn = get_db_connection()
    # Delete mappings too
    conn.execute("DELETE FROM channel_mapping WHERE monitored_channel_id = ?", (channel_id,))
    conn.execute("DELETE FROM monitored_channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()

# Destination Channels
def get_destination_channels():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM destination_channels").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_destination_channel(platform, channel_name, channel_id, credentials):
    conn = get_db_connection()
    cred_str = json.dumps(credentials) if isinstance(credentials, (dict, list)) else str(credentials)
    
    # Check if channel already exists for this platform and channel_id
    row = conn.execute("SELECT id FROM destination_channels WHERE platform = ? AND channel_id = ?", (platform, channel_id)).fetchone()
    if row:
        dest_id = row['id']
        conn.execute("UPDATE destination_channels SET channel_name = ?, credentials = ? WHERE id = ?", (channel_name, cred_str, dest_id))
        conn.commit()
        conn.close()
        return dest_id
    else:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO destination_channels (platform, channel_name, channel_id, credentials) VALUES (?, ?, ?, ?)",
                     (platform, channel_name, channel_id, cred_str))
        conn.commit()
        dest_id = cursor.lastrowid
        conn.close()
        return dest_id

def delete_destination_channel(dest_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM channel_mapping WHERE destination_channel_id = ?", (dest_id,))
    conn.execute("DELETE FROM destination_channels WHERE id = ?", (dest_id,))
    conn.commit()
    conn.close()

# Channel Mappings
def get_channel_mappings(monitored_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT destination_channel_id FROM channel_mapping WHERE monitored_channel_id = ?", (monitored_id,)).fetchall()
    conn.close()
    return [r['destination_channel_id'] for r in rows]

def save_channel_mappings(monitored_id, destination_ids):
    conn = get_db_connection()
    conn.execute("DELETE FROM channel_mapping WHERE monitored_channel_id = ?", (monitored_id,))
    for dest_id in destination_ids:
        conn.execute("INSERT INTO channel_mapping (monitored_channel_id, destination_channel_id) VALUES (?, ?)", (monitored_id, dest_id))
    conn.commit()
    conn.close()

# Reup Settings
def get_reup_settings():
    conn = get_db_connection()
    rows = conn.execute("SELECT key, value FROM reup_settings").fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}

def save_reup_settings(settings_dict):
    conn = get_db_connection()
    for key, value in settings_dict.items():
        conn.execute("INSERT OR REPLACE INTO reup_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# Music Library
def get_music_files():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM music_library").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_music_file(filename, file_id, file_size):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO music_library (filename, file_id, file_size) VALUES (?, ?, ?)", (filename, file_id, file_size))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_music_file(music_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM music_library WHERE id = ?", (music_id,))
    conn.commit()
    conn.close()

# Video Queue
def add_video_to_queue(monitored_id, video_id, title, url):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO video_queue (monitored_channel_id, video_id, title, url) VALUES (?, ?, ?, ?)",
                     (monitored_id, video_id, title, url))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def update_video_queue_status(queue_id, status, error_msg=None):
    conn = get_db_connection()
    if status == 'failed':
        conn.execute("UPDATE video_queue SET status = ?, attempts = attempts + 1, error_msg = ? WHERE id = ?", (status, error_msg, queue_id))
    else:
        conn.execute("UPDATE video_queue SET status = ?, error_msg = ? WHERE id = ?", (status, error_msg, queue_id))
    conn.commit()
    conn.close()

def get_pending_videos():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM video_queue WHERE status = 'pending' AND attempts < 3 ORDER BY created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Upload History
def add_upload_history(video_queue_id, destination_channel_id, status, video_url_or_id=None, error_msg=None):
    conn = get_db_connection()
    conn.execute("INSERT INTO upload_history (video_queue_id, destination_channel_id, status, video_url_or_id, error_msg) VALUES (?, ?, ?, ?, ?)",
                 (video_queue_id, destination_channel_id, status, video_url_or_id, error_msg))
    conn.commit()
    conn.close()

# Logs
def log_event(level, message):
    conn = get_db_connection()
    conn.execute("INSERT INTO logs (level, message) VALUES (?, ?)", (level, message))
    conn.commit()
    conn.close()
    print(f"[{level}] {message}")

def get_logs(limit=50):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# DB Backup and Restore to/from Telegram removed
