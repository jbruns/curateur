"""
Shared pytest fixtures and utilities for the curateur test suite.
"""

from pathlib import Path
from typing import Dict, Any, Callable

import pytest
import yaml


@pytest.fixture
def project_root() -> Path:
    """
    Repository root path for locating fixtures and sample data.
    """
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def data_dir(project_root: Path) -> Path:
    """
    Path to shared static test fixtures (tiny ROMs, XML, YAML, media).
    """
    return project_root / "tests" / "data"


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[[Dict[str, Any]], Path]:
    """
    Create a minimal config.yaml in a temp directory.
    
    Usage:
        path = make_config({"runtime": {"dry_run": False}})
    """

    def _builder(overrides: Dict[str, Any] | None = None) -> Path:
        base = {
            "screenscraper": {
                "user_id": "test-user",
                "user_password": "test-password",
            },
            "paths": {
                "roms": str(tmp_path / "roms"),
                "media": str(tmp_path / "media"),
                "gamelists": str(tmp_path / "gamelists"),
                "es_systems": str(tmp_path / "es_systems.xml"),
            },
            "runtime": {"dry_run": True},
        }
        if overrides:
            base = merge_dicts(base, overrides)

        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.safe_dump(base))
        return cfg_path

    return _builder


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Shallow+deep merge helper for fixture config dictionaries.
    """
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
