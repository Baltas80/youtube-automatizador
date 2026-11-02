from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .metadata import parse_datetime

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
KEYRING_SERVICE = "youtube-automatizador"
KEYRING_ACCOUNT = "default"


class ApiUploadError(RuntimeError):
    def __init__(
        self, message: str, retryable: bool = False, retry_after_seconds: int | None = None
    ):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class YouTubeApi:
    def __init__(self):
        self._lock = threading.RLock()
        self._cached_service = None
        self._cached_credentials = None

    def has_credentials(self) -> bool:
        import keyring

        try:
            return bool(keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT))
        except Exception:
            return False

    def authenticate(self, client_secrets_path: str) -> dict[str, str]:
        secrets = Path(client_secrets_path)
        if not secrets.is_file():
            raise FileNotFoundError(f"No existe el archivo de credenciales OAuth: {secrets}")

        try:
            import keyring
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError("Faltan dependencias de Google OAuth. Reinstala la aplicación.") from exc

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            access_type="offline",
            prompt="consent",
            open_browser=True,
        )
        keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, credentials.to_json())
        with self._lock:
            self._cached_service = None
        return self.channel_info()

    def _credentials(self):
        import keyring
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        if not raw:
            raise ApiUploadError("No hay una cuenta conectada. Pulsa «Conectar con YouTube».")
        info = json.loads(raw)
        credentials = Credentials.from_authorized_user_info(info, SCOPES)
        if not credentials.has_scopes(SCOPES):
            raise ApiUploadError(
                "La autorización guardada no incluye los permisos necesarios. Vuelve a conectar."
            )
        if credentials.expired:
            if not credentials.refresh_token:
                raise ApiUploadError("La autorización ha caducado. Vuelve a conectar con YouTube.")
            try:
                credentials.refresh(Request())
            except Exception as exc:
                raise ApiUploadError(
                    f"No se pudo renovar la autorización ({exc}). Vuelve a conectar con YouTube."
                ) from exc
            keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, credentials.to_json())
        return credentials

    def _service(self):
        from googleapiclient.discovery import build

        with self._lock:
            if self._cached_service is None:
                self._cached_credentials = self._credentials()
                self._cached_service = build(
                    "youtube", "v3", credentials=self._cached_credentials, cache_discovery=False
                )
            return self._cached_service

    def _persist_credentials(self) -> None:
        if self._cached_credentials is None:
            return
        import keyring

        keyring.set_password(
            KEYRING_SERVICE, KEYRING_ACCOUNT, self._cached_credentials.to_json()
        )

    def channel_info(self) -> dict[str, str]:
        try:
            response = self._service().channels().list(part="snippet", mine=True).execute()
            self._persist_credentials()
        except Exception as exc:
            self._persist_credentials()
            raise ApiUploadError(f"No se pudo consultar el canal de YouTube: {exc}") from exc
        items = response.get("items") or []
        if not items:
            raise ApiUploadError("La cuenta autorizada no tiene un canal de YouTube accesible.")
        snippet = items[0].get("snippet") or {}
        return {
            "channel_id": items[0].get("id", ""),
            "channel_title": snippet.get("title", "Canal de YouTube"),
        }

    def upload(
        self, job: dict, progress: Callable[[float], None] | None = None
    ) -> dict[str, str | None]:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        video_path = Path(job["file_path"])
        if not video_path.is_file():
            raise ApiUploadError(f"El archivo ya no existe: {video_path}")
        if not job.get("title", "").strip():
            raise ApiUploadError("El título del vídeo está vacío.")

        scheduled_at = None
        status: dict[str, str] = {"privacyStatus": job.get("privacy_status") or "public"}
        if job.get("scheduled_at"):
            scheduled_at = parse_datetime(job["scheduled_at"])
            minimum = datetime.now(timezone.utc) + timedelta(minutes=15)
            if scheduled_at <= minimum:
                raise ApiUploadError(
                    "La fecha programada debe estar al menos 15 minutos en el futuro. "
                    "No se ha subido el vídeo para evitar publicarlo inmediatamente por error."
                )
            status = {
                "privacyStatus": "private",
                "publishAt": scheduled_at.isoformat().replace("+00:00", "Z"),
            }

        snippet = {
            "title": job["title"],
            "description": job.get("description") or "",
            "tags": job.get("tags") or [],
            "categoryId": job.get("category_id") or "22",
        }
        if job.get("language"):
            snippet["defaultLanguage"] = job["language"]

        body = {"snippet": snippet, "status": status}
        media = MediaFileUpload(
            str(video_path), mimetype="video/*", chunksize=8 * 1024 * 1024, resumable=True
        )

        try:
            service = self._service()
            request = service.videos().insert(
                part="snippet,status", body=body, media_body=media
            )
            response = None
            while response is None:
                upload_status, response = request.next_chunk(num_retries=3)
                if upload_status is not None and progress is not None:
                    progress(round(upload_status.progress() * 100, 1))
            video_id = response.get("id")
            if not video_id:
                raise ApiUploadError("YouTube no devolvió un identificador de vídeo.")

            warning = None
            thumbnail_path = job.get("thumbnail_path")
            if thumbnail_path and Path(thumbnail_path).is_file():
                try:
                    thumbnail = MediaFileUpload(str(thumbnail_path), resumable=False)
                    service.thumbnails().set(videoId=video_id, media_body=thumbnail).execute()
                except Exception as exc:
                    warning = f"El vídeo se subió, pero no se pudo asignar la miniatura: {exc}"

            actual_privacy = None
            try:
                check = service.videos().list(part="status", id=video_id).execute()
                items = check.get("items") or []
                if items:
                    actual_privacy = (items[0].get("status") or {}).get("privacyStatus")
            except Exception as exc:
                warning = (warning + " | " if warning else "") + (
                    f"No se pudo verificar el estado final del vídeo: {exc}"
                )

            requested_privacy = status["privacyStatus"]
            if not scheduled_at and requested_privacy == "public" and actual_privacy == "private":
                warning = (warning + " | " if warning else "") + (
                    "YouTube ha guardado el vídeo como privado aunque se solicitó público. "
                    "Comprueba la auditoría/restricciones del proyecto de API y publícalo "
                    "manualmente cuando esté permitido."
                )

            if scheduled_at:
                final_status = "scheduled"
            else:
                final_status = {
                    "public": "published",
                    "unlisted": "uploaded_unlisted",
                    "private": "uploaded_private",
                }.get(actual_privacy or requested_privacy, "published")
            if not scheduled_at and actual_privacy and actual_privacy != requested_privacy:
                warning = (warning + " | " if warning else "") + (
                    f"YouTube devolvió privacidad '{actual_privacy}' aunque se solicitó "
                    f"'{requested_privacy}'. Revisa el estado del vídeo en YouTube Studio."
                )

            self._persist_credentials()
            return {
                "video_id": video_id,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "actual_privacy": actual_privacy,
                "warning": warning,
                "final_status": final_status,
            }
        except ApiUploadError:
            raise
        except HttpError as exc:
            reason = ""
            message = str(exc)
            try:
                payload = json.loads(exc.content.decode("utf-8"))
                api_error = payload.get("error", {})
                message = api_error.get("message") or message
                errors = api_error.get("errors") or []
                reason = errors[0].get("reason", "") if errors else ""
            except Exception:
                pass

            quota_reasons = {
                "quotaExceeded", "dailyLimitExceeded", "userRateLimitExceeded",
                "rateLimitExceeded", "dailyLimitExceededUnreg",
            }
            retryable = exc.resp.status in {408, 429, 500, 502, 503, 504} or reason in quota_reasons
            retry_after = 24 * 60 * 60 if reason in quota_reasons else None
            raise ApiUploadError(
                f"YouTube API ({exc.resp.status}, {reason or 'sin código'}): {message}",
                retryable=retryable,
                retry_after_seconds=retry_after,
            ) from exc
        except (OSError, TimeoutError, ConnectionError) as exc:
            raise ApiUploadError(f"Error de red o archivo durante la subida: {exc}", True) from exc
