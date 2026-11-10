"""
Diego AI — SQLite Storage & Database Foundation (WAL Mode + FTS5).
Concurrent-safe, ACID-compliant, atomic writes.
"""

import os
import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("diego_storage")
logger.setLevel(logging.INFO)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "diego_memory.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """SQLite ulanishini yaratish va WAL rejimini faollashtirish."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DB_PATH):
    """Barcha kerakli jadvallar va indekslarni yaratish."""
    conn = get_connection(db_path)
    try:
        with conn:
            # 1. Suhbatlar tarixi (L1 va L2 xotira uchun)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT,
                    sender_id INTEGER NOT NULL,
                    sender_name TEXT,
                    sender_username TEXT,
                    is_from_me BOOLEAN NOT NULL DEFAULT 0,
                    message_text TEXT NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    reply_to_msg_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id, timestamp);")

            # 2. Uzoq muddatli faktlar (L3 Memory)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'manual',
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_cat ON memory_facts(category, subject);")

            # FTS5 (To'liq matn qidiruvi — semantik qidiruv asosi)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts USING fts5(
                    subject,
                    fact,
                    content='memory_facts',
                    content_rowid='id'
                );
            """)

            # FTS5 triggerlari
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_facts_ai AFTER INSERT ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(rowid, subject, fact) VALUES (new.id, new.subject, new.fact);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_facts_ad AFTER DELETE ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, subject, fact) VALUES('delete', old.id, old.subject, old.fact);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_facts_au AFTER UPDATE ON memory_facts BEGIN
                    INSERT INTO memory_facts_fts(memory_facts_fts, rowid, subject, fact) VALUES('delete', old.id, old.subject, old.fact);
                    INSERT INTO memory_facts_fts(rowid, subject, fact) VALUES (new.id, new.subject, new.fact);
                END;
            """)

            # 3. Kontaktlar profili (Hadichaxon, do'stlar, oila)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    preferred_name TEXT,
                    relationship TEXT,
                    notes TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_tg ON contacts(telegram_id);")

            # 4. Tizim sozlamalari (Key-Value)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 5. Vazifalar (Tasks)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    details TEXT,
                    due_date DATETIME,
                    is_completed BOOLEAN DEFAULT 0,
                    priority INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME
                );
            """)
    finally:
        conn.close()
    logger.info("Database initialized successfully at %s", db_path)


class StorageManager:
    """Barcha ma'lumotlar bazasi operatsiyalari uchun xavfsiz wrapper."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def _execute(self, func):
        """Context-managed connection wrapper that guarantees close."""
        conn = get_connection(self.db_path)
        try:
            with conn:
                return func(conn)
        finally:
            conn.close()

    # --- SOZLAMALAR (Settings) ---
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        def _op(conn):
            row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
        return self._execute(_op)

    def set_setting(self, key: str, value: str):
        def _op(conn):
            conn.execute("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
            """, (key, value))
        return self._execute(_op)

    # --- SUHBATLAR (Conversations) ---
    def add_message(self, chat_id: int, sender_id: int, sender_name: str, 
                    message_text: str, is_from_me: bool = False,
                    chat_title: str = "", sender_username: str = "",
                    message_type: str = "text", reply_to_msg_id: Optional[int] = None) -> int:
        def _op(conn):
            cursor = conn.execute("""
                INSERT INTO conversations 
                (chat_id, chat_title, sender_id, sender_name, sender_username, is_from_me, message_text, message_type, reply_to_msg_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (chat_id, chat_title, sender_id, sender_name, sender_username, is_from_me, message_text, message_type, reply_to_msg_id))
            return cursor.lastrowid
        return self._execute(_op)

    def get_recent_messages(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        def _op(conn):
            rows = conn.execute("""
                SELECT * FROM (
                    SELECT * FROM conversations 
                    WHERE chat_id = ? 
                    ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC;
            """, (chat_id, limit)).fetchall()
            return [dict(r) for r in rows]
        return self._execute(_op)

    # --- FAKTLAR VA XOTIRA (Facts & Long-term memory) ---
    def add_fact(self, category: str, subject: str, fact: str, confidence: float = 1.0, source: str = "manual") -> int:
        def _op(conn):
            cursor = conn.execute("""
                INSERT INTO memory_facts (category, subject, fact, confidence, source)
                VALUES (?, ?, ?, ?, ?)
            """, (category, subject.strip(), fact.strip(), confidence, source))
            return cursor.lastrowid
        return self._execute(_op)

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        def _op(conn):
            try:
                rows = conn.execute("""
                    SELECT m.* FROM memory_facts m
                    JOIN memory_facts_fts f ON m.id = f.rowid
                    WHERE memory_facts_fts MATCH ? AND m.is_active = 1
                    ORDER BY rank LIMIT ?;
                """, (query, limit)).fetchall()
                return [dict(r) for r in rows]
            except Exception:
                like_q = f"%{query}%"
                rows = conn.execute("""
                    SELECT * FROM memory_facts 
                    WHERE (subject LIKE ? OR fact LIKE ?) AND is_active = 1
                    LIMIT ?;
                """, (like_q, like_q, limit)).fetchall()
                return [dict(r) for r in rows]
        return self._execute(_op)

    def get_all_active_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        def _op(conn):
            if category:
                rows = conn.execute("SELECT * FROM memory_facts WHERE category = ? AND is_active = 1", (category,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM memory_facts WHERE is_active = 1").fetchall()
            return [dict(r) for r in rows]
        return self._execute(_op)

    # --- KONTAKTLAR (Contacts) ---
    def get_or_create_contact(self, telegram_id: int, display_name: str, username: str = "") -> Dict[str, Any]:
        def _op(conn):
            row = conn.execute("SELECT * FROM contacts WHERE telegram_id = ?", (telegram_id,)).fetchone()
            if row:
                if username and row["username"] != username:
                    conn.execute("UPDATE contacts SET username = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?", (username, telegram_id))
                return dict(row)
            cursor = conn.execute("""
                INSERT INTO contacts (telegram_id, username, display_name)
                VALUES (?, ?, ?)
            """, (telegram_id, username, display_name))
            return {
                "id": cursor.lastrowid,
                "telegram_id": telegram_id,
                "username": username,
                "display_name": display_name,
                "preferred_name": None,
                "relationship": None,
                "notes": None
            }
        return self._execute(_op)

    def set_contact_details(self, telegram_id: int, preferred_name: Optional[str] = None, 
                            relationship: Optional[str] = None, notes: Optional[str] = None):
        def _op(conn):
            updates = []
            params = []
            if preferred_name is not None:
                updates.append("preferred_name = ?")
                params.append(preferred_name)
            if relationship is not None:
                updates.append("relationship = ?")
                params.append(relationship)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(telegram_id)
                query = f"UPDATE contacts SET {', '.join(updates)} WHERE telegram_id = ?"
                conn.execute(query, tuple(params))
        return self._execute(_op)
