from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

from .content import DEFAULT_DESCRIPTION_TEMPLATE, DEFAULT_HASHTAGS, DEFAULT_TAGS

APP_DIR = Path(user_data_dir("YouTubeAutomatizador", "Baltas80"))
CONFIG_PATH = APP_DIR / "config.json"
DATABASE_PATH = APP_DIR / "queue.sqlite3"
CURRENT_CONFIG_VERSION = 2


@dataclass
class AppConfig:
    config_version: int = CURRENT_CONFIG_VERSION
    client_secrets_path: str = ""
    watch_folder: str = ""
    scan_interval_seconds: int = 10
    stable_scans: int = 3
    default_privacy: str = "private"
    auto_start_watching: bool = False
    start_with_windows: bool = False
    channel_name: str = "Proyecto NeoLatino"
    description_template: str = DEFAULT_DESCRIPTION_TEMPLATE
    default_hashtags: list[str] = field(default_factory=lambda: list(DEFAULT_HASHTAGS))
    default_tags: list[str] = field(default_factory=lambda: list(DEFAULT_TAGS))

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        allowed = {name for name in cls.__dataclass_fields__}
        values = {key: value for key, value in raw.items() if key in allowed}
        previous_version = int(values.get("config_version", 1))
        config = cls(**values)

        # Version 2 changes the first-run and migrated privacy default to private.
        if previous_version < 2:
            config.default_privacy = "private"
        config.config_version = CURRENT_CONFIG_VERSION

        if config.default_privacy not in {"public", "unlisted", "private"}:
            config.default_privacy = "private"
        config.scan_interval_seconds = max(5, min(300, int(config.scan_interval_seconds)))
        config.stable_scans = max(2, min(10, int(config.stable_scans)))
        if not isinstance(config.default_hashtags, list):
            config.default_hashtags = list(DEFAULT_HASHTAGS)
        if not isinstance(config.default_tags, list):
            config.default_tags = list(DEFAULT_TAGS)
        if not config.description_template:
            config.description_template = DEFAULT_DESCRIPTION_TEMPLATE
        if not config.channel_name.strip():
            config.channel_name = "tu canal"
        return config


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("El archivo de configuración no contiene un objeto JSON.")
        return AppConfig.from_dict(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        backup = path.with_suffix(".invalid.json")
        try:
            os.replace(path, backup)
        except OSError:
            pass
        raise RuntimeError(
            f"No se pudo leer la configuración. Se ha intentado conservar una copia en {backup}: {exc}"
        ) from exc


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    config.config_version = CURRENT_CONFIG_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
