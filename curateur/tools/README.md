# Development Tools

This directory contains development and CI/CD utility scripts for the curateur project.

## Tools

### generate_system_map.py

Generates the ScreenScraper platform ID mapping from `es_systems.xml`.

### setup_dev_credentials.py

Interactive setup tool for configuring ScreenScraper API credentials during development.

### organize_roms.py

Normalize a system's ROM layout for ES-DE and curateur (disc subdirectories and `.m3u` playlists).

Usage:

```bash
python -m curateur.tools.organize_roms /path/to/source psx /path/to/roms --es-systems /path/to/es_systems.xml
```
