import json

from ihear import config
from ihear.models import Config


def test_load_default_config_when_missing(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    cfg = config.load_config()
    assert isinstance(cfg, Config)
    assert cfg.backend == "auto"


def test_save_and_load_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    cfg = Config(backend="whisper", whisper_model="small")
    config.save_config(cfg)

    loaded = config.load_config()
    assert loaded.backend == "whisper"
    assert loaded.whisper_model == "small"


def test_update_config_validates_keys(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    config.update_config(backend="openai")
    loaded = config.load_config()
    assert loaded.backend == "openai"

    try:
        config.update_config(unknown="value")
    except config.ConfigError:
        pass
    else:
        raise AssertionError("Expected ConfigError for invalid key")
