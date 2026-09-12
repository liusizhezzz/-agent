from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, background_sound TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, ended_at TEXT);
        CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, user_text TEXT NOT NULL, final_asr INTEGER NOT NULL, rag_status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, agent_id TEXT NOT NULL, title TEXT NOT NULL, source_text TEXT NOT NULL, summary TEXT NOT NULL, category TEXT NOT NULL, retention TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        self.db.commit()

    def create_session(self, agent_id: str, background_sound: str) -> str:
        sid = str(uuid.uuid4()); self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,NULL)", (sid, agent_id, background_sound, "active", now())); self.db.commit(); return sid

    def add_turn(self, session_id: str, text: str, *, final_asr: bool, rag_status: str) -> str:
        tid = str(uuid.uuid4()); self.db.execute("INSERT INTO turns VALUES(?,?,?,?,?,?)", (tid, session_id, text, int(final_asr), rag_status, now())); self.db.commit(); return tid

    def session_agent(self, session_id: str) -> str | None:
        row = self.db.execute("SELECT agent_id FROM sessions WHERE id=?", (session_id,)).fetchone()
        return row[0] if row else None

    def transcript(self, session_id: str) -> str:
        rows = self.db.execute("SELECT user_text FROM turns WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
        return "\n".join(row[0] for row in rows if row[0])

    def end_session(self, session_id: str, agent_id: str, title: str, source: str, summary: str, category: str, retention: str) -> dict:
        mid = str(uuid.uuid4()); self.db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?)", (mid, session_id, agent_id, title, source, summary, category, retention, now())); self.db.execute("UPDATE sessions SET status='ended',ended_at=? WHERE id=?", (now(), session_id)); self.db.commit(); return dict(self.db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone())
