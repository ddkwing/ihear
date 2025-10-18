"""Persisted configuration management."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Config

CONFIG_PATH = (Path.home() / ".ihear" / "config.json").expanduser()


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or saved."""


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    try:
        payload = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Failed to parse configuration file: {exc}") from exc
    return Config(**payload)


def save_config(config: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in asdict(config).items() if v is not None}
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def update_config(**kwargs: Any) -> Config:
    config = load_config()
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
        else:
            raise ConfigError(f"Unknown configuration key: {key}")
    save_config(config)
    return config
