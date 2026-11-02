from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .metadata import VIDEO_EXTENSIONS, metadata_for_file
from .store import JobStore


class FolderWatcher:
    def __init__(
        self,
        folder: str | Path,
        store: JobStore,
        default_privacy: str,
        on_job: Callable[[str, bool, str], None],
        on_error: Callable[[str], None],
        interval_seconds: int = 10,
        stable_scans: int = 3,
    ):
        self.folder = Path(folder)
        self.store = store
        self.default_privacy = default_privacy
        self.on_job = on_job
        self.on_error = on_error
        self.interval_seconds = max(5, interval_seconds)
        self.stable_scans = max(2, stable_scans)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observed: dict[str, tuple[int, float, int]] = {}

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if not self.folder.is_dir():
            raise NotADirectoryError(self.folder)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="YouTubeFolderWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                self.on_error(f"Error al revisar la carpeta: {exc}")
            self._stop.wait(self.interval_seconds)

    def scan_once(self) -> None:
        try:
            candidates = list(self.folder.iterdir())
        except OSError as exc:
            self.on_error(f"No se puede leer la carpeta {self.folder}: {exc}")
            return

        active: set[str] = set()
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            key = str(path.resolve())
            active.add(key)
            try:
                stat = path.stat()
                previous = self._observed.get(key)
                if previous and previous[0] == stat.st_size and previous[1] == stat.st_mtime:
                    stable_count = previous[2] + 1
                else:
                    stable_count = 1
                self._observed[key] = (stat.st_size, stat.st_mtime, stable_count)
                if stat.st_size <= 0 or stable_count < self.stable_scans:
                    continue

                sidecar = path.with_suffix(".json")
                try:
                    sidecar_mtime = sidecar.stat().st_mtime if sidecar.exists() else 0.0
                except OSError:
                    sidecar_mtime = -1.0

                if self.store.has_watch_version(key, stat.st_size, stat.st_mtime, sidecar_mtime):
                    continue

                try:
                    metadata = metadata_for_file(path, self.default_privacy)
                    job_id, created = self.store.add_job(metadata)
                    self.store.mark_watch_version(key, stat.st_size, stat.st_mtime, sidecar_mtime)
                    self.on_job(job_id, created, path.name)
                except Exception as exc:
                    self.store.mark_watch_version(key, stat.st_size, stat.st_mtime, sidecar_mtime)
                    self.on_error(f"{path.name}: {exc}")
            except OSError as exc:
                self.on_error(f"No se puede inspeccionar {path.name}: {exc}")

        for stale in set(self._observed) - active:
            self._observed.pop(stale, None)
