from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import APP_DIR, DATABASE_PATH, load_config, save_config
from .metadata import VIDEO_EXTENSIONS, metadata_for_file
from .store import JobStore
from .watcher import FolderWatcher
from .worker import UploadWorker
from .youtube_api import YouTubeApi

STATUS_LABELS = {
    "queued": "En cola",
    "uploading": "Subiendo",
    "retry_wait": "Reintento pendiente",
    "interrupted": "Interrumpido — comprobar",
    "failed": "Error",
    "published": "Publicado",
    "scheduled": "Programado",
    "uploaded_private": "Subido como privado",
    "uploaded_unlisted": "Subido como oculto",
}


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.parent = parent
        self.title("Configuración")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        config = parent.config
        self.secret_var = tk.StringVar(value=config.client_secrets_path)
        self.folder_var = tk.StringVar(value=config.watch_folder)
        self.privacy_var = tk.StringVar(value=config.default_privacy)
        self.auto_var = tk.BooleanVar(value=config.auto_start_watching)
        self.startup_var = tk.BooleanVar(value=config.start_with_windows)

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Archivo OAuth de Google (cliente de escritorio)").grid(
            row=0, column=0, sticky="w"
        )
        row = ttk.Frame(frame)
        row.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        ttk.Entry(row, textvariable=self.secret_var, width=58).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Examinar…", command=self._choose_secret).pack(side="left", padx=(6, 0))

        ttk.Label(frame, text="Carpeta vigilada").grid(row=2, column=0, sticky="w")
        row = ttk.Frame(frame)
        row.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        ttk.Entry(row, textvariable=self.folder_var, width=58).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Examinar…", command=self._choose_folder).pack(side="left", padx=(6, 0))

        ttk.Label(frame, text="Privacidad por defecto para archivos sin JSON lateral").grid(
            row=4, column=0, sticky="w"
        )
        ttk.Combobox(
            frame, textvariable=self.privacy_var, values=("public", "unlisted", "private"),
            state="readonly", width=18
        ).grid(row=5, column=0, sticky="w", pady=(4, 12))

        ttk.Checkbutton(
            frame, text="Iniciar la vigilancia automáticamente al abrir la aplicación",
            variable=self.auto_var
        ).grid(row=6, column=0, sticky="w", pady=(0, 5))
        ttk.Checkbutton(
            frame, text="Iniciar YouTube Automatizador al arrancar Windows",
            variable=self.startup_var
        ).grid(row=7, column=0, sticky="w", pady=(0, 12))

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, sticky="e")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Guardar", command=self._save).pack(side="right", padx=(0, 8))

    def _choose_secret(self):
        path = filedialog.askopenfilename(
            parent=self, title="Seleccionar credenciales OAuth",
            filetypes=[("Archivo JSON", "*.json"), ("Todos los archivos", "*.*")]
        )
        if path:
            self.secret_var.set(path)

    def _choose_folder(self):
        path = filedialog.askdirectory(parent=self, title="Seleccionar carpeta de vídeos")
        if path:
            self.folder_var.set(path)

    def _save(self):
        if self.privacy_var.get() not in {"public", "unlisted", "private"}:
            messagebox.showerror("Configuración", "Selecciona una privacidad válida.", parent=self)
            return
        self.parent.config.client_secrets_path = self.secret_var.get().strip()
        self.parent.config.watch_folder = self.folder_var.get().strip()
        self.parent.config.default_privacy = self.privacy_var.get()
        self.parent.config.auto_start_watching = self.auto_var.get()
        self.parent.config.start_with_windows = self.startup_var.get()
        try:
            from .windows_startup import set_startup

            set_startup(self.startup_var.get())
        except Exception as exc:
            messagebox.showerror(
                "Inicio de Windows",
                f"No se pudo actualizar el inicio automático: {exc}",
                parent=self,
            )
            return
        save_config(self.parent.config)
        self.parent._set_status("Configuración guardada.")
        self.destroy()


class VideoDialog(tk.Toplevel):
    def __init__(self, parent: "MainWindow", video_path: str):
        super().__init__(parent)
        self.video_path = Path(video_path)
        self.result = None
        self.title("Añadir vídeo a la cola")
        self.geometry("650x570")
        self.minsize(560, 500)
        self.transient(parent)
        self.grab_set()

        defaults = metadata_for_file(self.video_path, parent.config.default_privacy)
        self.title_var = tk.StringVar(value=defaults["title"])
        self.tags_var = tk.StringVar(value=", ".join(defaults["tags"]))
        self.privacy_var = tk.StringVar(value=defaults["privacy_status"])
        scheduled_default = defaults.get("scheduled_at")
        schedule_display = ""
        if scheduled_default:
            try:
                schedule_display = datetime.fromisoformat(scheduled_default).astimezone().strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                schedule_display = ""
        self.schedule_var = tk.StringVar(value=schedule_display)
        self.thumbnail_var = tk.StringVar(value=defaults.get("thumbnail_path") or "")

        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)

        ttk.Label(container, text=f"Archivo: {self.video_path.name}").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        ttk.Label(container, text="Título").grid(row=1, column=0, sticky="w")
        ttk.Entry(container, textvariable=self.title_var).grid(
            row=2, column=0, sticky="ew", pady=(3, 10)
        )

        ttk.Label(container, text="Descripción").grid(row=3, column=0, sticky="w")
        self.description = tk.Text(container, height=7, wrap="word")
        self.description.grid(row=4, column=0, sticky="nsew", pady=(3, 10))
        self.description.insert("1.0", defaults["description"])

        ttk.Label(container, text="Etiquetas (separadas por comas)").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Entry(container, textvariable=self.tags_var).grid(
            row=6, column=0, sticky="ew", pady=(3, 10)
        )

        options = ttk.Frame(container)
        options.grid(row=7, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(options, text="Privacidad inmediata").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.privacy_var, values=("public", "unlisted", "private"),
            state="readonly", width=12
        ).pack(side="left", padx=(8, 20))
        ttk.Label(options, text="Programar (opcional, hora local)").pack(side="left")
        ttk.Entry(options, textvariable=self.schedule_var, width=19).pack(side="left", padx=(8, 0))

        ttk.Label(
            container,
            text="Formato: AAAA-MM-DD HH:MM. Si se rellena, YouTube lo sube como privado y lo publica a esa hora."
        ).grid(row=8, column=0, sticky="w", pady=(0, 8))

        thumb = ttk.Frame(container)
        thumb.grid(row=9, column=0, sticky="ew")
        ttk.Label(thumb, text="Miniatura (opcional)").pack(side="left")
        ttk.Entry(thumb, textvariable=self.thumbnail_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(thumb, text="Examinar…", command=self._choose_thumbnail).pack(side="left")

        buttons = ttk.Frame(container)
        buttons.grid(row=10, column=0, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Añadir a cola", command=self._submit).pack(
            side="right", padx=(0, 8)
        )

    def _choose_thumbnail(self):
        path = filedialog.askopenfilename(
            parent=self, title="Seleccionar miniatura",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png"), ("Todos los archivos", "*.*")]
        )
        if path:
            self.thumbnail_var.set(path)

    def _submit(self):
        title = self.title_var.get().strip()
        description = self.description.get("1.0", "end").strip()
        if not title:
            messagebox.showerror("Vídeo", "El título no puede estar vacío.", parent=self)
            return
        if len(title) > 100 or len(description) > 5000:
            messagebox.showerror(
                "Vídeo", "El título debe tener como máximo 100 caracteres y la descripción 5000.",
                parent=self
            )
            return
        privacy = self.privacy_var.get()
        if privacy not in {"public", "unlisted", "private"}:
            messagebox.showerror("Vídeo", "Selecciona una privacidad válida.", parent=self)
            return

        scheduled_at = None
        schedule_text = self.schedule_var.get().strip()
        if schedule_text:
            try:
                local_time = datetime.strptime(schedule_text, "%Y-%m-%d %H:%M").astimezone()
                scheduled_at = local_time.isoformat()
            except ValueError:
                messagebox.showerror(
                    "Programación", "Usa el formato AAAA-MM-DD HH:MM, por ejemplo 2026-11-05 18:00.",
                    parent=self
                )
                return
            privacy = "private"

        thumbnail = self.thumbnail_var.get().strip() or None
        if thumbnail and not Path(thumbnail).is_file():
            messagebox.showerror("Miniatura", "El archivo de miniatura no existe.", parent=self)
            return

        self.result = {
            "file_path": str(self.video_path.resolve()),
            "title": title,
            "description": description,
            "tags": [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()],
            "privacy_status": privacy,
            "scheduled_at": scheduled_at,
            "thumbnail_path": thumbnail,
            "category_id": "22",
            "language": "es",
        }
        self.destroy()


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Automatizador")
        self.geometry("1080x680")
        self.minsize(850, 540)

        self.config = load_config()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.store = JobStore(DATABASE_PATH)
        self.api = YouTubeApi()
        self.events: queue.Queue = queue.Queue()
        self.watcher: FolderWatcher | None = None
        self.worker = UploadWorker(self.store, self.api, self._emit)
        self.worker.start()
        self.progress_by_job: dict[str, float] = {}

        self._build_ui()
        self.refresh_jobs()
        self.after(250, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

        if self.config.auto_start_watching and self.config.watch_folder:
            self.after(500, self.start_watching)

        if self.api.has_credentials():
            self._set_status("Credenciales guardadas. Conecta el canal para comprobar el acceso.")

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill="x")
        ttk.Label(
            header, text="YOUTUBE AUTOMATIZADOR", font=("Segoe UI", 16, "bold")
        ).pack(side="left")
        self.channel_label = ttk.Label(header, text="Canal: no conectado")
        self.channel_label.pack(side="left", padx=22)
        ttk.Button(header, text="Conectar con YouTube", command=self.connect).pack(side="right")
        ttk.Button(header, text="Configuración", command=self.open_settings).pack(
            side="right", padx=(0, 8)
        )

        watch = ttk.LabelFrame(self, text="Vigilancia automática", padding=10)
        watch.pack(fill="x", padx=14, pady=(4, 10))
        self.folder_label = ttk.Label(
            watch, text=self.config.watch_folder or "Selecciona una carpeta de vídeos", width=80
        )
        self.folder_label.pack(side="left", fill="x", expand=True)
        ttk.Button(watch, text="Cambiar carpeta", command=self.choose_watch_folder).pack(
            side="left", padx=(8, 6)
        )
        self.watch_button = ttk.Button(watch, text="Iniciar vigilancia", command=self.toggle_watcher)
        self.watch_button.pack(side="left")

        actions = ttk.Frame(self, padding=(14, 0, 14, 8))
        actions.pack(fill="x")
        ttk.Button(actions, text="Añadir vídeo…", command=self.add_video).pack(side="left")
        ttk.Button(actions, text="Reintentar seleccionado", command=self.retry_selected).pack(
            side="left", padx=8
        )
        ttk.Button(actions, text="Abrir carpeta de datos", command=self.open_data_folder).pack(
            side="right"
        )

        table_frame = ttk.Frame(self, padding=(14, 0, 14, 10))
        table_frame.pack(fill="both", expand=True)
        columns = ("title", "file", "status", "privacy", "date", "progress")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "title": ("Título", 260),
            "file": ("Archivo", 220),
            "status": ("Estado", 145),
            "privacy": ("Privacidad", 100),
            "date": ("Publicación", 160),
            "progress": ("Progreso", 90),
        }
        for column, (label, width) in headings.items():
            self.table.heading(column, text=label)
            self.table.column(column, width=width, minwidth=60, stretch=column in {"title", "file"})
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.bind("<Double-1>", self.open_selected_video)
        self.table.tag_configure("failed", foreground="#b42318")
        self.table.tag_configure("uploaded_private", foreground="#9a6700")

        self.status_var = tk.StringVar(value="Preparado.")
        ttk.Label(
            self, textvariable=self.status_var, relief="sunken", anchor="w", padding=6
        ).pack(fill="x", side="bottom")
        self._set_folder_label()

    def _emit(self, *event):
        self.events.put(event)

    def _set_status(self, message: str):
        self.status_var.set(message)

    def _set_folder_label(self):
        self.folder_label.configure(
            text=self.config.watch_folder or "Selecciona una carpeta de vídeos"
        )

    def open_settings(self):
        SettingsDialog(self)
        self.after(400, self._set_folder_label)

    def choose_watch_folder(self):
        folder = filedialog.askdirectory(
            parent=self, title="Seleccionar carpeta de vídeos",
            initialdir=self.config.watch_folder or str(Path.home())
        )
        if folder:
            self.config.watch_folder = folder
            save_config(self.config)
            self._set_folder_label()
            self._set_status("Carpeta de vigilancia guardada.")

    def toggle_watcher(self):
        if self.watcher and self.watcher.running:
            self.stop_watching()
        else:
            self.start_watching()

    def start_watching(self):
        folder = self.config.watch_folder
        if not folder or not Path(folder).is_dir():
            self.choose_watch_folder()
            folder = self.config.watch_folder
        if not folder or not Path(folder).is_dir():
            return
        try:
            self.watcher = FolderWatcher(
                folder=folder,
                store=self.store,
                default_privacy=self.config.default_privacy,
                on_job=lambda job_id, created, name: self._emit("new_job", job_id, created, name),
                on_error=lambda message: self._emit("warning", message),
                interval_seconds=self.config.scan_interval_seconds,
                stable_scans=self.config.stable_scans,
            )
            self.watcher.start()
            self.watch_button.configure(text="Detener vigilancia")
            self._set_status(f"Vigilando {folder}")
        except Exception as exc:
            messagebox.showerror("Vigilancia", str(exc), parent=self)

    def stop_watching(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self.watch_button.configure(text="Iniciar vigilancia")
        self._set_status("Vigilancia detenida. La cola existente continúa.")

    def connect(self):
        path = self.config.client_secrets_path
        if not path or not Path(path).is_file():
            path = filedialog.askopenfilename(
                parent=self, title="Seleccionar credenciales OAuth de Google",
                filetypes=[("Archivo JSON", "*.json"), ("Todos los archivos", "*.*")]
            )
            if not path:
                return
            self.config.client_secrets_path = path
            save_config(self.config)

        self._set_status("Abriendo autorización de Google…")

        def task():
            try:
                if self.api.has_credentials():
                    try:
                        channel = self.api.channel_info()
                    except Exception:
                        channel = self.api.authenticate(path)
                else:
                    channel = self.api.authenticate(path)
                self._emit("connected", channel)
            except Exception as exc:
                self._emit("connect_error", str(exc))

        threading.Thread(target=task, name="YouTubeOAuth", daemon=True).start()

    def add_video(self):
        path = filedialog.askopenfilename(
            parent=self, title="Seleccionar vídeo",
            filetypes=[
                ("Vídeos", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))),
                ("Todos los archivos", "*.*"),
            ]
        )
        if not path:
            return
        try:
            dialog = VideoDialog(self, path)
            self.wait_window(dialog)
            if not dialog.result:
                return
            self._set_status(f"Calculando huella del archivo: {Path(path).name}")
            metadata = dialog.result

            def task():
                try:
                    job_id, created = self.store.add_job(metadata)
                    self._emit("new_job", job_id, created, Path(path).name)
                except Exception as exc:
                    self._emit("warning", f"No se pudo añadir {Path(path).name}: {exc}")

            threading.Thread(target=task, name="AddYouTubeJob", daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Añadir vídeo", str(exc), parent=self)

    def retry_selected(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Cola", "Selecciona primero un vídeo.", parent=self)
            return
        if self.store.retry_job(selection[0]):
            self._set_status("Vídeo devuelto a la cola.")
            self.refresh_now()
        else:
            messagebox.showinfo(
                "Cola", "Solo se pueden reintentar trabajos fallidos o pendientes de reintento.",
                parent=self
            )

    def open_selected_video(self, _event=None):
        selection = self.table.selection()
        if not selection:
            return
        job = next((item for item in self.store.list_jobs() if item["id"] == selection[0]), None)
        if job and job.get("video_url"):
            webbrowser.open(job["video_url"])
        elif job:
            os.startfile(job["file_path"])

    def open_data_folder(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(APP_DIR))

    def refresh_jobs(self):
        self._refresh_table_once()
        self.after(2000, self.refresh_jobs)

    def _refresh_table_once(self):
        selected = self.table.selection()
        selected_id = selected[0] if selected else None
        self.table.delete(*self.table.get_children())
        for job in reversed(self.store.list_jobs()):
            status = job["status"]
            scheduled = job.get("scheduled_at") or "Inmediata"
            if scheduled != "Inmediata":
                try:
                    scheduled = datetime.fromisoformat(scheduled).astimezone().strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            values = (
                job["title"],
                Path(job["file_path"]).name,
                STATUS_LABELS.get(status, status),
                job.get("actual_privacy") or job["privacy_status"],
                scheduled,
                f"{self.progress_by_job.get(job['id'], 0):.0f}%" if status == "uploading" else "",
            )
            tags = (status,) if status in {"failed", "uploaded_private"} else ()
            self.table.insert("", "end", iid=job["id"], values=values, tags=tags)
        if selected_id and self.table.exists(selected_id):
            self.table.selection_set(selected_id)

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind, *args = event
                if kind == "connected":
                    channel = args[0]
                    self.channel_label.configure(text=f"Canal: {channel['channel_title']}")
                    self._set_status(
                        f"Conectado a {channel['channel_title']} ({channel['channel_id']})."
                    )
                elif kind == "connect_error":
                    self._set_status("No se pudo conectar con YouTube.")
                    messagebox.showerror("Conexión con YouTube", args[0], parent=self)
                elif kind == "new_job":
                    _job_id, created, name = args
                    self._set_status(
                        f"Añadido a la cola: {name}" if created
                        else f"Duplicado detectado, no se vuelve a subir: {name}"
                    )
                    self.refresh_now()
                elif kind == "job_changed":
                    self.refresh_now()
                elif kind == "progress":
                    job_id, percent = args
                    self.progress_by_job[job_id] = percent
                    self.refresh_now()
                elif kind == "log":
                    self._set_status(args[0])
                elif kind == "warning":
                    self._set_status(args[0])
                elif kind == "error":
                    self._set_status(args[0])
        except queue.Empty:
            pass
        self.after(250, self._poll_events)

    def refresh_now(self):
        self._refresh_table_once()

    def _close(self):
        if self.watcher:
            self.watcher.stop()
        self.worker.stop()
        self.destroy()


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
