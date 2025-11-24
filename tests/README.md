Test scaffold for curateur.

- Layout mirrors packages (`api`, `config`, `scanner`, `media`, `gamelist`, `workflow`, `ui`, `tools`); add tests under the matching folder.
- Shared fixtures live in `tests/conftest.py` (temp config builder, project/data paths).
- Place static fixtures under `tests/data` (small XML/YAML, tiny ROM playlists, sample media).
- Fast CI profile: `pytest -m "not slow and not live" --cov=curateur --cov-report=term-missing`.
- Full local (no live): `pytest -m "not live"`.
