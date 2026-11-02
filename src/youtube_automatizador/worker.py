from __future__ import annotations

import threading
from typing import Callable

from .store import JobStore
from .youtube_api import ApiUploadError, YouTubeApi


class UploadWorker(threading.Thread):
    def __init__(
        self,
        store: JobStore,
        api: YouTubeApi,
        emit: Callable[..., None],
    ):
        super().__init__(name="YouTubeUploadWorker", daemon=True)
        self.store = store
        self.api = api
        self.emit = emit
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            if not self.api.has_credentials():
                self._stop_event.wait(3)
                continue

            job = self.store.next_job()
            if job is None:
                self._stop_event.wait(2)
                continue

            job_id = job["id"]
            try:
                self.store.mark_uploading(job_id)
                self.emit("job_changed", job_id)
                self.emit("log", f"Subiendo: {job['title']}")

                def report(percent: float) -> None:
                    self.emit("progress", job_id, percent)

                result = self.api.upload(job, progress=report)
                self.store.mark_completed(
                    job_id,
                    str(result["video_id"]),
                    str(result["video_url"]),
                    actual_privacy=result.get("actual_privacy"),
                    warning=result.get("warning"),
                    final_status=str(result.get("final_status") or "published"),
                )
                self.emit("job_changed", job_id)
                if result.get("warning"):
                    self.emit("warning", str(result["warning"]))
                self.emit("log", f"Subida completada: {result['video_url']}")
            except ApiUploadError as exc:
                self.store.mark_failed(
                    job_id,
                    str(exc),
                    retryable=exc.retryable,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                self.emit("job_changed", job_id)
                self.emit("error", str(exc))
            except Exception as exc:
                self.store.mark_failed(job_id, str(exc), retryable=True)
                self.emit("job_changed", job_id)
                self.emit("error", f"Error inesperado durante la subida: {exc}")
