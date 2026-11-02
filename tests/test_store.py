from youtube_automatizador.store import JobStore


def make_video(tmp_path, name="clip.mp4", content=b"fake-video"):
    path = tmp_path / name
    path.write_bytes(content)
    return {
        "file_path": str(path),
        "title": path.stem,
        "description": "",
        "tags": [],
        "privacy_status": "public",
        "scheduled_at": None,
    }


def test_store_adds_job_and_prevents_duplicate_content(tmp_path):
    store = JobStore(tmp_path / "queue.sqlite3")
    first, created = store.add_job(make_video(tmp_path, "one.mp4"))
    second, duplicate_created = store.add_job(make_video(tmp_path, "two.mp4"))
    assert created is True
    assert duplicate_created is False
    assert first == second
    assert len(store.list_jobs()) == 1


def test_retry_job_requeues_failed_job(tmp_path):
    store = JobStore(tmp_path / "queue.sqlite3")
    job_id, _ = store.add_job(make_video(tmp_path))
    store.mark_uploading(job_id)
    store.mark_failed(job_id, "bad request", retryable=False)
    assert store.retry_job(job_id) is True
    job = store.next_job()
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == "queued"


def test_watch_version_detects_changed_sidecar(tmp_path):
    store = JobStore(tmp_path / "queue.sqlite3")
    path = str(tmp_path / "clip.mp4")
    assert not store.has_watch_version(path, 12, 1.0, 2.0)
    store.mark_watch_version(path, 12, 1.0, 2.0)
    assert store.has_watch_version(path, 12, 1.0, 2.0)
    assert not store.has_watch_version(path, 12, 1.0, 3.0)
