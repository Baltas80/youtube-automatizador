from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}


def parse_datetime(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("scheduled_at debe ser una fecha ISO 8601 válida.") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("scheduled_at debe incluir zona horaria, por ejemplo +01:00 o Z.")
    return result.astimezone(timezone.utc)


def metadata_for_file(video_path: str | Path, default_privacy: str = "public") -> dict[str, Any]:
    path = Path(video_path)
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Formato de vídeo no admitido: {path.suffix or '(sin extensión)'}")

    sidecar = path.with_suffix(".json")
    raw: dict[str, Any] = {}
    if sidecar.exists():
        try:
            loaded = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"No se puede leer {sidecar.name}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"{sidecar.name} debe contener un objeto JSON.")
        raw = loaded

    title = str(raw.get("title") or path.stem).strip()
    description = str(raw.get("description") or "").strip()
    if not title:
        raise ValueError("El título no puede estar vacío.")
    if len(title) > 100:
        raise ValueError("El título supera el límite de 100 caracteres de YouTube.")
    if len(description) > 5000:
        raise ValueError("La descripción supera los 5000 caracteres permitidos.")

    tags_value = raw.get("tags") or []
    if isinstance(tags_value, str):
        tags = [item.strip() for item in tags_value.split(",") if item.strip()]
    elif isinstance(tags_value, list):
        tags = [str(item).strip() for item in tags_value if str(item).strip()]
    else:
        raise ValueError("tags debe ser una lista de textos o una cadena separada por comas.")

    privacy = str(raw.get("privacy_status") or default_privacy).lower()
    if privacy not in {"public", "unlisted", "private"}:
        raise ValueError("privacy_status debe ser public, unlisted o private.")

    scheduled_value = raw.get("scheduled_at")
    scheduled_at = parse_datetime(str(scheduled_value)) if scheduled_value else None
    if scheduled_at is not None:
        # La programación siempre se carga como privada y YouTube la publica al llegar la fecha.
        privacy = "private"

    thumbnail_value = raw.get("thumbnail_path")
    thumbnail = None
    if thumbnail_value:
        thumbnail_path = Path(str(thumbnail_value))
        if not thumbnail_path.is_absolute():
            thumbnail_path = path.parent / thumbnail_path
        thumbnail = str(thumbnail_path.resolve())

    category_id = str(raw.get("category_id") or "").strip() or None
    language = str(raw.get("language") or "").strip() or None

    return {
        "file_path": str(path.resolve()),
        "title": title,
        "description": description,
        "tags": tags,
        "category_id": category_id,
        "language": language,
        "privacy_status": privacy,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "thumbnail_path": thumbnail,
    }
