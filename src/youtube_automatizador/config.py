from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_DIR = Path(user_data_dir("YouTubeAutomatizador", "Baltas80"))
CONFIG_PATH = APP_DIR / "config.json"
DATABASE_PATH = APP_DIR / "queue.sqlite3"


@dataclass
class AppConfig:
    client_secrets_path: str = ""
    watch_folder: str = ""
    scan_interval_seconds: int = 10
    stable_scans: int = 3
    default_privacy: str = "public"
    auto_start_watching: bool = False
    start_with_windows: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        allowed = {field for field in cls.__dataclass_fields__}
        values = {key: value for key, value in raw.items() if key in allowed}
        config = cls(**values)
        if config.default_privacy not in {"public", "unlisted", "private"}:
            config.default_privacy = "public"
        config.scan_interval_seconds = max(5, min(300, int(config.scan_interval_seconds)))
        config.stable_scans = max(2, min(10, int(config.stable_scans)))
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
