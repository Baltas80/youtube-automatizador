# YouTube Automatizador

Aplicación de escritorio ligera para Windows que vigila una carpeta, mantiene una cola persistente y publica vídeos en un canal propio de YouTube mediante la YouTube Data API v3 oficial.

## Funciones de la primera versión

- OAuth 2.0 para aplicación de escritorio.
- Token de acceso en el almacén de credenciales de Windows.
- Identificación del canal autenticado.
- Vigilancia periódica de una carpeta y detección de archivos terminados.
- Cola SQLite persistente, huella SHA-256 y prevención de duplicados.
- Subida reanudable de 8 MB por bloque, progreso y reintentos.
- Conservación de tareas interrumpidas; exige comprobar YouTube Studio antes de reintentar para evitar duplicados.
- Publicación inmediata o programación mediante `status.publishAt`.
- Generación local y automática de descripciones, hashtags y etiquetas de YouTube a partir del título.
- Plantillas, nombre del canal y hashtags predeterminados configurables.
- Metadatos por vídeo mediante formulario o archivo JSON lateral; los valores indicados expresamente tienen prioridad.
- Compilación automática de un ejecutable Windows x64 en GitHub Actions.

## Requisitos de Google / YouTube

La aplicación utiliza exclusivamente la API oficial, no cookies ni endpoints privados.

- La cuota predeterminada documentada para `videos.insert` es de 100 subidas al día.
- El historial de revisión de YouTube indica que algunos proyectos API no auditados pueden tener restricciones para publicar vídeos públicamente. La aplicación comprueba el estado devuelto por YouTube y muestra una advertencia si el vídeo termina privado.
- Los tokens OAuth de un proyecto externo cuyo consentimiento siga en estado **Testing** caducan a los 7 días para scopes distintos de identidad básica. Para uso continuado hay que configurar correctamente el estado de publicación de la pantalla de consentimiento y completar cualquier verificación exigible.

Fuentes oficiales: [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert), [cuotas](https://developers.google.com/youtube/data/determine_quota_cost), [historial de cambios](https://developers.google.com/youtube/v3/revision_history), [OAuth 2.0](https://developers.google.com/identity/protocols/oauth2).

## Primer uso

1. En Google Cloud Console, crea un proyecto y habilita **YouTube Data API v3**.
2. Configura la pantalla de consentimiento OAuth.
3. Crea un cliente OAuth de tipo **Desktop app** y descarga el JSON.
4. Abre la aplicación, pulsa **Conectar con YouTube** y selecciona el JSON.
5. Selecciona una carpeta y activa **Iniciar vigilancia**. En Configuración puedes activar el inicio con Windows y la vigilancia automática al abrir la aplicación.

No subas el JSON OAuth ni tokens al repositorio. Los tokens se guardan en Windows Credential Manager.

## Descripción y hashtags automáticos (sin IA ni costes externos)

La aplicación genera metadatos localmente, sin llamadas de red adicionales. Usa el título del archivo, las palabras configuradas y una plantilla editable desde **Configuración**. La plantilla admite:

- `{title}`: título del vídeo.
- `{channel}`: nombre del canal.
- `{hashtags}`: hashtags generados y sin duplicados.

La configuración inicial incluye términos de bachata y música latina para Proyecto NeoLatino. Se pueden cambiar en cualquier momento. Las etiquetas de YouTube también se generan automáticamente y se pueden ampliar mediante metadatos laterales.

Si se escribe una descripción en el JSON, se conserva y se completan los hashtags que falten. La generación es determinista y basada en reglas: no analiza el audio ni el contenido visual, por lo que conviene revisar los resultados antes de activar subidas públicas desatendidas.

## Metadatos para la carpeta vigilada

Para `video.mp4`, se puede crear un archivo `video.json` en la misma carpeta:

```json
{
  "title": "Título del vídeo",
  "description": "Descripción",
  "description": "Descripción opcional. Si se omite, se genera automáticamente.",
  "tags": ["etiqueta adicional"],
  "hashtags": ["bachata", "música latina"],
  "category_id": "10",
  "language": "es",
  "privacy_status": "private",
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

Los vídeos programados se suben como privados y se asigna `status.publishAt`. La aplicación rechaza fechas pasadas, sin zona horaria o con menos de 15 minutos de margen. Ese margen de 15 minutos es una validación conservadora de la aplicación, no una garantía ni un mínimo publicado por YouTube. Una programación inválida nunca se convierte en una publicación inmediata.

También se puede añadir un vídeo manualmente desde el formulario, seleccionando publicación inmediata o fecha programada.

## Desarrollo y pruebas

Python 3.12 recomendado:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest -q
python -m youtube_automatizador
```

El ejecutable portable para Windows x64 se genera como artefacto de GitHub Actions en cada push a la rama de desarrollo. No requiere tener Python instalado para ejecutarlo. Para subir automáticamente tras reiniciar Windows, activa tanto «Iniciar YouTube Automatizador al arrancar Windows» como «Iniciar la vigilancia automáticamente».

## Seguridad y comportamiento

- No se guardan credenciales en Git.
- El token OAuth se almacena en Windows Credential Manager.
- Los vídeos originales no se borran ni se mueven automáticamente.
- Las descripciones, hashtags y etiquetas se generan localmente; no se envían títulos ni vídeos a servicios externos de IA.
- La cola y el estado de los trabajos persisten en SQLite. Si el proceso se interrumpe durante una subida, el trabajo queda en estado «Interrumpido» y exige comprobación manual antes de reintentar.
- Se detectan duplicados mediante SHA-256.
- Las subidas interrumpidas se recuperan como trabajos pendientes de reintento.
- Los fallos de cuota se esperan 24 horas antes del siguiente intento automático.
- Una programación inválida se bloquea; nunca se publica inmediatamente como alternativa.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
