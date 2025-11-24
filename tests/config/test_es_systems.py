import pytest

from curateur.config.es_systems import (
    parse_es_systems,
    get_systems_by_name,
    ESSystemsError,
)


@pytest.mark.unit
def test_parse_es_systems_returns_definitions(tmp_path, data_dir):
    source = data_dir / "config" / "es_systems_valid.xml"
    es_path = tmp_path / "es_systems.xml"
    es_path.write_text(source.read_text())

    systems = parse_es_systems(es_path)

    assert len(systems) == 1
    system = systems[0]
    assert system.name == "nes"
    assert system.supports_m3u() is False
    resolved = system.resolve_rom_path(tmp_path / "roms")
    assert str(resolved).endswith("roms/nes")


@pytest.mark.unit
def test_parse_es_systems_rejects_invalid_root(tmp_path, data_dir):
    source = data_dir / "config" / "es_systems_invalid_root.xml"
    es_path = tmp_path / "bad.xml"
    es_path.write_text(source.read_text())

    with pytest.raises(ESSystemsError):
        parse_es_systems(es_path)


@pytest.mark.unit
def test_get_systems_by_name_reports_missing(tmp_path, data_dir):
    source = data_dir / "config" / "es_systems_valid.xml"
    es_path = tmp_path / "es_systems.xml"
    es_path.write_text(source.read_text())

    systems = parse_es_systems(es_path)

    with pytest.raises(ValueError):
        get_systems_by_name(systems, names=["unknown"])
