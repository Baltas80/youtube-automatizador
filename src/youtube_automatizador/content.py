from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

DEFAULT_DESCRIPTION_TEMPLATE = (
    "🎵 {title}\n\n"
    "Disfruta de esta canción y de más música latina en {channel}.\n\n"
    "Suscríbete y activa las notificaciones para descubrir los próximos lanzamientos.\n\n"
    "{hashtags}"
)
DEFAULT_HASHTAGS = ["bachata", "bachata romantica", "musica latina", "Proyecto NeoLatino"]
DEFAULT_TAGS = [
    "bachata",
    "bachata romantica",
    "musica latina",
    "musica romantica",
    "Proyecto NeoLatino",
]

STOPWORDS = {
    "para", "por", "con", "sin", "del", "las", "los", "una", "uno", "unos",
    "unas", "que", "como", "desde", "hasta", "sobre", "entre", "pero", "sus",
    "mas", "muy", "este", "esta", "estos", "estas", "video", "vídeo", "oficial",
    "official", "audio", "letra", "lyrics", "hd", "4k",
}


def _items(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw = re.split(r"[,;\n]+", values)
    else:
        raw = list(values)
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        item = str(value).strip().lstrip("#").strip()
        key = item.casefold()
        if item and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _ascii_words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.findall(r"[A-Za-z0-9]+", plain)


def _hashtag(value: str) -> str | None:
    words = _ascii_words(value)
    if not words:
        return None
    slug = "".join(word[:1].upper() + word[1:] for word in words)
    if not slug or slug.isdigit():
        return None
    return f"#{slug}"


def extract_title_keywords(title: str, limit: int = 5) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for word in _ascii_words(title):
        key = word.casefold()
        if len(word) < 3 or key.isdigit() or key in STOPWORDS or key in seen:
            continue
        result.append(word)
        seen.add(key)
        if len(result) >= limit:
            break
    return result


def generate_hashtags(
    title: str,
    default_hashtags: Iterable[str] | str | None = None,
    description: str = "",
    limit: int = 8,
) -> list[str]:
    candidates = _items(default_hashtags if default_hashtags is not None else DEFAULT_HASHTAGS)
    candidates.extend(extract_title_keywords(title))
    # Include a small number of meaningful terms from the supplied description.
    candidates.extend(extract_title_keywords(description, limit=3))

    hashtags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        tag = _hashtag(candidate)
        if tag and tag.casefold() not in seen:
            hashtags.append(tag)
            seen.add(tag.casefold())
        if len(hashtags) >= max(1, limit):
            break
    return hashtags


def generate_youtube_tags(
    title: str,
    supplied_tags: Iterable[str] | str | None = None,
    default_tags: Iterable[str] | str | None = None,
) -> list[str]:
    candidates = _items(supplied_tags)
    candidates.extend(_items(default_tags if default_tags is not None else DEFAULT_TAGS))
    candidates.extend(extract_title_keywords(title, limit=6))

    result: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for candidate in candidates:
        item = re.sub(r"\s+", " ", candidate).strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        cost = len(item) + (1 if result else 0)
        if len(result) >= 20 or total_chars + cost > 450:
            continue
        result.append(item)
        seen.add(key)
        total_chars += cost
    return result


def build_video_content(
    title: str,
    description: str = "",
    supplied_tags: Iterable[str] | str | None = None,
    *,
    description_template: str = DEFAULT_DESCRIPTION_TEMPLATE,
    channel_name: str = "Proyecto NeoLatino",
    default_hashtags: Iterable[str] | str | None = None,
    default_tags: Iterable[str] | str | None = None,
) -> tuple[str, list[str], list[str]]:
    """Create a deterministic description, hashtags and YouTube tags without network calls."""
    hashtags = generate_hashtags(title, default_hashtags, description)
    hashtag_line = " ".join(hashtags)

    if description.strip():
        final_description = description.strip()
        existing = {tag.casefold() for tag in re.findall(r"#[A-Za-z0-9_]+", final_description)}
        missing = [tag for tag in hashtags if tag.casefold() not in existing]
        if missing:
            final_description = f"{final_description}\n\n{' '.join(missing)}"
    else:
        template = description_template.strip() or DEFAULT_DESCRIPTION_TEMPLATE
        final_description = (
            template.replace("{title}", title.strip())
            .replace("{channel}", channel_name.strip() or "tu canal")
            .replace("{hashtags}", hashtag_line)
        )
        if "{hashtags}" not in template:
            final_description = f"{final_description.rstrip()}\n\n{hashtag_line}"

    final_description = final_description.strip()
    if len(final_description) > 5000:
        raise ValueError(
            "La descripción generada supera los 5000 caracteres permitidos por YouTube. "
            "Reduce la plantilla o el texto configurado."
        )

    tags = generate_youtube_tags(title, supplied_tags, default_tags)
    return final_description, hashtags, tags
