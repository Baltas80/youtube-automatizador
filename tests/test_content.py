import json

from youtube_automatizador.content import build_video_content, generate_hashtags
from youtube_automatizador.metadata import metadata_for_file


def test_generates_description_and_relevant_hashtags_without_network():
    description, hashtags, tags = build_video_content(
        "Falsa Ilusión",
        channel_name="Proyecto NeoLatino",
    )
    assert "Falsa Ilusión" in description
    assert "Proyecto NeoLatino" in description
    assert "#Bachata" in description
    assert "#Falsa" in description
    assert "#Ilusion" in description
    assert hashtags
    assert tags


def test_custom_description_is_preserved_and_hashtags_appended():
    description, _, _ = build_video_content(
        "Para Olvidarte",
        "Una nueva bachata romántica.",
    )
    assert description.startswith("Una nueva bachata romántica.")
    assert "#Bachata" in description
    assert "#Olvidarte" in description


def test_custom_template_replaces_supported_variables():
    description, _, _ = build_video_content(
        "Mi canción",
        description_template="Nuevo lanzamiento: {title} en {channel}. {hashtags}",
        channel_name="Mi Canal",
        default_hashtags=["pop latino"],
    )
    assert description.startswith("Nuevo lanzamiento: Mi canción en Mi Canal.")
    assert "#PopLatino" in description


def test_hashtags_are_deduplicated_and_bounded():
    tags = generate_hashtags(
        "Bachata Romántica",
        ["bachata", "bachata romantica", "musica latina"],
        limit=5,
    )
    assert len(tags) <= 5
    assert len({tag.casefold() for tag in tags}) == len(tags)


def test_sidecar_can_override_generated_description_and_privacy(tmp_path):
    video = tmp_path / "tema.mp4"
    video.write_bytes(b"video")
    video.with_suffix(".json").write_text(
        json.dumps({
            "title": "Tema especial",
            "description": "Descripción escrita por el usuario.",
            "privacy_status": "unlisted",
            "tags": ["mi etiqueta"],
        }),
        encoding="utf-8",
    )
    metadata = metadata_for_file(video)
    assert metadata["privacy_status"] == "unlisted"
    assert metadata["description"].startswith("Descripción escrita por el usuario.")
    assert "#Bachata" in metadata["description"]
    assert "mi etiqueta" in metadata["tags"]
