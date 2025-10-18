"""Top-level package for ihear."""

from . import config, storage, summarizer, transcriber

__all__ = ["config", "storage", "summarizer", "transcriber"]

try:  # pragma: no cover - optional dependency
    from . import menubar as menubar  # type: ignore
except Exception:  # noqa: BLE001 - optional dependency failure is acceptable
    menubar = None  # type: ignore
else:
    __all__.append("menubar")
