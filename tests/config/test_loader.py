import pytest

from curateur.config.loader import load_config, ConfigError


@pytest.mark.unit
def test_load_config_merges_dev_credentials(tmp_path, data_dir, es_systems_file, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
screenscraper:
  user_id: user
  user_password: pass
paths:
  roms: /roms
  media: /media
  gamelists: /gamelists
  es_systems: {es_systems_file}
"""
    )

    monkeypatch.setattr(
        "curateur.api.credentials.get_dev_credentials",
        lambda: {"devid": "dev", "devpassword": "devpass", "softname": "curateur"},
    )

    cfg = load_config(str(config_path))

    assert cfg["screenscraper"]["user_id"] == "user"
    assert cfg["screenscraper"]["devid"] == "dev"
    assert cfg["screenscraper"]["devpassword"] == "devpass"
    assert cfg["screenscraper"]["softname"] == "curateur"


@pytest.mark.unit
def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError):
        load_config("/tmp/does-not-exist.yaml")


@pytest.mark.unit
def test_load_config_invalid_yaml(tmp_path, es_systems_file, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("invalid: [unclosed")

    monkeypatch.setattr(
        "curateur.api.credentials.get_dev_credentials",
        lambda: {"devid": "dev", "devpassword": "devpass", "softname": "curateur"},
    )

    with pytest.raises(ConfigError):
        load_config(str(config_path))
