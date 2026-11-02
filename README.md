# YouTube Automatizador

Aplicación de escritorio para Windows que vigila una carpeta, mantiene una cola persistente y publica vídeos en un canal propio de YouTube mediante la YouTube Data API v3 oficial.

## Alcance de la primera versión

- OAuth 2.0 de aplicación de escritorio.
- Token de acceso guardado en el almacén de credenciales de Windows.
- Identificación del canal autenticado.
- Vigilancia de carpeta y detección de archivos terminados.
- Cola SQLite persistente, huella SHA-256 y prevención de duplicados.
- Subida reanudable, progreso, reintentos y recuperación tras cierre inesperado.
- Publicación inmediata o programación mediante `status.publishAt`.
- Metadatos por vídeo mediante archivo JSON lateral.
- Paquete Windows generado por GitHub Actions.

## Requisitos de publicación

La aplicación utiliza exclusivamente la API oficial. Google aplica cuotas y políticas propias al proyecto de API. La cuota predeterminada documentada para `videos.insert` es de 100 subidas al día. Los proyectos que no hayan completado la auditoría de cumplimiento pueden estar sujetos a restricciones de publicación; debe verificarse el comportamiento de la credencial real antes de activar la automatización desatendida.

Los tokens OAuth de un proyecto externo que permanezca en estado **Testing** caducan a los 7 días para scopes distintos de identidad básica. Para uso continuado hay que configurar correctamente el estado de publicación de la pantalla de consentimiento y completar cualquier verificación exigible.

## Configuración

1. En Google Cloud Console, crea un proyecto y habilita **YouTube Data API v3**.
2. Configura la pantalla de consentimiento OAuth.
3. Crea un cliente OAuth de tipo **Desktop app** y descarga el JSON.
4. En la aplicación, selecciona ese JSON y pulsa **Conectar con YouTube**.
5. Selecciona una carpeta y activa la vigilancia.

No subas el JSON OAuth ni tokens al repositorio.

## Metadatos opcionales por vídeo

Para `video.mp4`, crea `video.json`:

```json
{
  "title": "Título del vídeo",
  "description": "Descripción",
  "tags": ["etiqueta1", "etiqueta2"],
  "category_id": "22",
  "language": "es",
  "privacy_status": "public",
  "thumbnail_path": "video.jpg"
}
```

Para programar la publicación, añade una fecha ISO 8601 con zona horaria:

```json
{
  "title": "Vídeo programado",
  "scheduled_at": "2026-11-05T18:00:00+01:00"
}
```

Los vídeos programados se suben como privados y se asigna `status.publishAt`. Una fecha pasada, sin zona horaria o demasiado próxima se rechaza antes de subir: nunca se convierte en una publicación inmediata por error.

## Desarrollo

- Python 3.12
- Tkinter
- Google API Python Client
- Watchdog
- SQLite
- Keyring / Windows Credential Manager

Instalación y pruebas:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest -q
python -m youtube_automatizador
```

El ejecutable Windows se compila y publica como artefacto en GitHub Actions.

## Seguridad

- No guardar secretos, tokens ni archivos OAuth en Git.
- Los tokens se almacenan en el almacén de credenciales del usuario de Windows.
- Los vídeos originales no se borran ni se mueven automáticamente.
- La cola persiste en SQLite.
- La aplicación no publica si falla la validación de una programación.

## Licencia

MIT. Consulta `LICENSE`.
