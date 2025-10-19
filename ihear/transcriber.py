"""Audio transcription backends."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Optional, Protocol, Tuple

from .config import load_config


class TranscriptionBackend(Protocol):
    """Common interface for transcription backends."""

    def transcribe(self, audio_path: Path) -> Tuple[str, dict]:
        """Return a tuple of transcript text and metadata."""


class WhisperBackend:
    """Local transcription using the `openai-whisper` package."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            import whisper  # type: ignore
            import torch
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The `openai-whisper` package is required for local transcription."
            ) from exc
        self._whisper = whisper
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = whisper.load_model(model_name, device=device)

    def transcribe(self, audio_path: Path) -> Tuple[str, dict]:
        result = self._model.transcribe(
            str(audio_path),
            task="transcribe",
            temperature=0.0,
            initial_prompt="Hello, how are you? I'm doing well, thank you. Please transcribe with proper punctuation.",
        )
        return result.get("text", "").strip(), {k: v for k, v in result.items() if k != "text"}


class OpenAIBackend:
    """Cloud transcription using the OpenAI API."""

    def __init__(self, model: str, api_key: Optional[str]) -> None:
        if api_key is None:
            raise RuntimeError("An OpenAI API key is required for this backend.")
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("The `openai` package is required for this backend.") from exc
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def transcribe(self, audio_path: Path) -> Tuple[str, dict]:  # pragma: no cover - network call
        with audio_path.open("rb") as fh:
            response = self._client.audio.transcriptions.create(model=self._model, file=fh)
        return response.text.strip(), {"response": response.model_dump()}


class DummyBackend:
    """Fallback backend used when no transcription engine is available."""

    def __init__(self) -> None:
        self._notice = (
            "No transcription backend available. Install `openai-whisper` for offline "
            "usage or configure an OpenAI API key to use the hosted service."
        )

    def transcribe(self, audio_path: Path) -> Tuple[str, dict]:
        raise RuntimeError(self._notice)


def get_backend(preferred: Optional[str] = None) -> TranscriptionBackend:
    """Return the best available transcription backend."""

    config = load_config()
    backend_name = preferred or config.backend

    if backend_name in {"whisper", "auto"}:
        try:
            return WhisperBackend(config.whisper_model)
        except Exception as exc:
            if backend_name == "whisper":
                raise RuntimeError(
                    f"Failed to initialise Whisper backend: {exc}. Ensure `openai-whisper` is installed."
                ) from exc

    if backend_name in {"openai", "auto"}:
        try:
            return OpenAIBackend(config.openai_model, config.openai_api_key)
        except Exception as exc:
            if backend_name == "openai":
                raise RuntimeError(
                    f"Failed to initialise OpenAI backend: {exc}. Check your API key and internet connection."
                ) from exc

    return DummyBackend()


def transcribe_audio(audio_path: Path, backend: Optional[str] = None) -> Tuple[str, dict]:
    """High level convenience wrapper."""

    engine = get_backend(backend)
    return engine.transcribe(audio_path)
