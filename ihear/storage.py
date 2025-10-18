"""SQLite backed persistence for ihear transcripts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .models import TranscriptRecord

APP_DIR = Path.home() / ".ihear"
DB_PATH = APP_DIR / "transcripts.db"
SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    """Raised when something goes wrong while accessing the storage."""


class Storage:
    """Manage persistence of transcripts using SQLite."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_initialised()

    def _ensure_initialised(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    audio_path TEXT,
                    transcript TEXT NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            cur = conn.execute("SELECT value FROM metadata WHERE key = ?", ("schema_version",))
            row = cur.fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO metadata(key, value) VALUES(?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )

    def add_transcript(
        self,
        title: str,
        transcript: str,
        audio_path: Optional[Path] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> TranscriptRecord:
        now = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata or {})
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO transcripts(title, audio_path, transcript, summary, created_at, updated_at, metadata)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    str(audio_path) if audio_path else None,
                    transcript,
                    summary,
                    now,
                    now,
                    metadata_json,
                ),
            )
            transcript_id = cur.lastrowid
        return self.get_transcript(transcript_id)

    def list_transcripts(self) -> Iterator[TranscriptRecord]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT * FROM transcripts ORDER BY created_at DESC"):
                yield _row_to_record(row)

    def get_transcript(self, transcript_id: int) -> TranscriptRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,))
            row = cur.fetchone()
            if row is None:
                raise StorageError(f"Transcript with id {transcript_id} not found")
            return _row_to_record(row)

    def update_summary(self, transcript_id: int, summary: str) -> TranscriptRecord:
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE transcripts SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, now, transcript_id),
            )
        return self.get_transcript(transcript_id)

    def delete_transcript(self, transcript_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))


def _row_to_record(row: sqlite3.Row) -> TranscriptRecord:
    return TranscriptRecord(
        id=row["id"],
        title=row["title"],
        audio_path=Path(row["audio_path"]) if row["audio_path"] else None,
        transcript=row["transcript"],
        summary=row["summary"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        metadata=json.loads(row["metadata"] or "{}"),
    )
