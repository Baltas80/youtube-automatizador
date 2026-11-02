from youtube_automatizador.config import AppConfig


def test_new_config_defaults_to_private():
    assert AppConfig().default_privacy == "private"


def test_legacy_config_is_migrated_to_private(tmp_path):
    config = AppConfig.from_dict({
        "default_privacy": "public",
        "watch_folder": "C:/Videos",
    })
    assert config.default_privacy == "private"
    assert config.config_version == 2
