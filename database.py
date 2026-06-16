import os
import sqlite3
from typing import Optional, List, Tuple
from config import DATABASE_PATH

def init_db() -> None:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # AI Channels config
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_channels (
        guild_id INTEGER,
        channel_id INTEGER PRIMARY KEY,
        model TEXT
    )""")
    
    # Voice Core Configuration
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS voice_config (
        guild_id INTEGER PRIMARY KEY,
        create_channel_id INTEGER,
        category_id INTEGER,
        interface_channel_id INTEGER,
        interface_message_id INTEGER
    )""")
    
    # Active Temp Voice Channels
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_vcs (
        channel_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        owner_id INTEGER,
        creation_time INTEGER
    )""")

    # Persistent user overrides (Bans & Permits)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vc_overrides (
        channel_id INTEGER,
        user_id INTEGER,
        type TEXT, -- 'BAN' or 'PERMIT'
        PRIMARY KEY (channel_id, user_id)
    )""")
    
    conn.commit()
    conn.close()

def execute_query(query: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()

def fetch_one(query: str, params: tuple = ()) -> Optional[Tuple]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row

def fetch_all(query: str, params: tuple = ()) -> List[Tuple]:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
