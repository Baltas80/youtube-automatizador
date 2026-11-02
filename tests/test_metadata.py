from datetime import datetime, timedelta, timezone
import json

import pytest

from youtube_automatizador.metadata import metadata_for_file, parse_datetime


def test_metadata_defaults_to_filename_and_private_with_generated_description(tmp_path):
    video = tmp_path / "mi video.mp4"
    video.write_bytes(b"video")
    data = metadata_for_file(video)
    assert data["title"] == "mi video"
    assert data["privacy_status"] == "private"
    assert data["scheduled_at"] is None
    assert "mi video" in data["description"]
    assert "#" in data["description"]
    assert data["tags"]


def test_sidecar_scheduling_forces_private(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    video.with_suffix(".json").write_text(
        json.dumps({"title": "Programado", "scheduled_at": future, "privacy_status": "public"}),
        encoding="utf-8",
    )
    data = metadata_for_file(video)
    assert data["title"] == "Programado"
    assert data["privacy_status"] == "private"
    assert data["scheduled_at"].endswith("+00:00")


def test_scheduled_datetime_requires_timezone():
    with pytest.raises(ValueError, match="zona horaria"):
        parse_datetime("2026-11-05T18:00:00")


def test_invalid_sidecar_is_rejected(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    video.with_suffix(".json").write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="No se puede leer"):
        metadata_for_file(video)


def test_unsupported_extension_is_rejected(tmp_path):
    video = tmp_path / "video.txt"
    video.write_text("not a video")
    with pytest.raises(ValueError, match="Formato"):
        metadata_for_file(video)
