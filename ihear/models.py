"""Dataclasses describing persistent objects for ihear."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(slots=True)
class TranscriptRecord:
    """Represents a stored transcript entry."""

    id: int
    title: str
    audio_path: Optional[str]
    transcript: str
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Config:
    """User configuration stored on disk."""

    backend: str = "auto"
    whisper_model: str = "base"
    openai_model: str = "gpt-4o-mini-transcribe"
    openai_api_key: Optional[str] = None
    insert_destination: str = "paste"
