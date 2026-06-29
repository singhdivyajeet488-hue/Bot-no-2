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
        type TEXT,
        PRIMARY KEY (channel_id, user_id)
    )""")

    # ── Leveling: per-guild per-user stats ──────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS levels (
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        xp              INTEGER NOT NULL DEFAULT 0,
        total_xp        INTEGER NOT NULL DEFAULT 0,
        level           INTEGER NOT NULL DEFAULT 0,
        last_msg_xp     REAL    NOT NULL DEFAULT 0,
        msg_xp          INTEGER NOT NULL DEFAULT 0,
        voice_xp        INTEGER NOT NULL DEFAULT 0,
        msg_count       INTEGER NOT NULL DEFAULT 0,
        voice_minutes   REAL    NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )""")

    # Add new columns if upgrading from older schema
    for col, typedef in [
        ("msg_xp",        "INTEGER NOT NULL DEFAULT 0"),
        ("voice_xp",      "INTEGER NOT NULL DEFAULT 0"),
        ("msg_count",     "INTEGER NOT NULL DEFAULT 0"),
        ("voice_minutes", "REAL NOT NULL DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE levels ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_levels_guild_xp ON levels (guild_id, xp DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_levels_guild_msg ON levels (guild_id, msg_xp DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_levels_guild_voice ON levels (guild_id, voice_xp DESC)"
    )

    # ── Per-guild leveling config ────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS level_config (
        guild_id            INTEGER PRIMARY KEY,
        levelup_channel_id  INTEGER,
        leaderboard_channel_id INTEGER,
        leaderboard_message_id INTEGER
    )""")

    # ── Dynamic role rewards ─────────────────────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS level_roles (
        guild_id INTEGER NOT NULL,
        level    INTEGER NOT NULL,
        role_id  INTEGER NOT NULL,
        PRIMARY KEY (guild_id, level)
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
