import sys
from pathlib import Path

import pytest

from curateur.tools import code_quality_check
from curateur.tools import generate_system_map
from curateur.tools import setup_dev_credentials


def test_code_quality_check_missing_path(monkeypatch, capsys, tmp_path):
    # Point to missing path should return 1
    monkeypatch.setenv("PYTHONWARNINGS", "ignore")
    monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path / "missing")])
    rc = code_quality_check.main()
    assert rc == 1


def test_code_quality_check_detects_syntax_error(monkeypatch, tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n    pass\n")
    monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path)])
    rc = code_quality_check.main()
    # In strict/ci default false; syntax error should still trigger non-zero
    assert rc == 1


def test_generate_system_map_writes_mapping(tmp_path, monkeypatch, capsys):
    es_xml = tmp_path / "es_systems.xml"
    es_xml.write_text(
        """<systemList><system><platform>nes</platform><fullname>Nintendo</fullname></system></systemList>"""
    )
    ss_xml = tmp_path / "systemesListe.xml"
    ss_xml.write_text(
        """<Data><systeme><id>3</id><noms_commun>Nintendo</noms_commun></systeme></Data>"""
    )
    out_file = tmp_path / "map.py"
    monkeypatch.setattr(sys, "argv", ["prog", "--es-systems", str(es_xml), "--systemes-liste", str(ss_xml), "--output", str(out_file)])
    generate_system_map.main()
    content = out_file.read_text()
    assert "nes" in content and "3" in content


def test_generate_system_map_missing_files(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["prog", "--es-systems", str(tmp_path / "missing1"), "--systemes-liste", str(tmp_path / "missing2")])
    with pytest.raises(SystemExit):
        generate_system_map.main()


def test_setup_dev_credentials_formatting():
    data = bytearray([1, 2, 3, 4, 5, 6, 7])
    formatted = setup_dev_credentials.format_bytearray(data, indent=2)
    # Ensure indent and commas are present
    assert "  1, 2, 3" in formatted
