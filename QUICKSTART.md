# Quick Start Guide

## For Developers

### Initial Setup

1. **Clone and enter the project:**
```bash
cd /Users/jbruns/src/curateur
```

2. **Dependencies are already installed in the virtual environment:**
```bash
# The virtual environment is at .venv/
# Activate it if needed:
source .venv/bin/activate.fish  # for fish shell
# or
source .venv/bin/activate  # for bash/zsh
```

3. **Verify installation:**
```bash
python -m curateur.cli --version
# Should output: curateur 1.0.0
```

4. **Run integration tests:**
```bash
python tests/test_phase1_integration.py
# Should show: 6/6 tests passed
```

### Testing Components

#### Test Configuration System
```bash
python -c "
from curateur.config.loader import load_config
from pathlib import Path
config = load_config(Path('tests/fixtures/test_config.yaml'))
print(f'User: {config[\"screenscraper\"][\"user_id\"]}')
print(f'Systems: {config[\"scraping\"][\"systems\"]}')
"
```

#### Test ES Systems Parser
```bash
python -c "
from curateur.config.es_systems import parse_es_systems
from pathlib import Path
systems = parse_es_systems(Path('tests/fixtures/es_systems.xml'))
for s in systems:
    print(f'{s.name} -> {s.platform}')
"
```

#### Test Platform Mapping
```bash
python -c "
from curateur.api.system_map import get_systemeid
for p in ['nes', 'snes', 'psx']:
    print(f'{p} -> {get_systemeid(p)}')
"
```

#### Test Credential Obfuscation
```bash
python -c "
from curateur.api.obfuscator import obfuscate, deobfuscate
test = 'my_secret'
obf = obfuscate(test)
print(f'Obfuscated: {obf}')
print(f'Deobfuscated: {deobfuscate(obf)}')
"
```

### Creating a Config File

1. **Copy the example:**
```bash
cp config.yaml.example config.yaml
```

2. **Edit config.yaml and set:**
   - `screenscraper.user_id`: Your ScreenScraper username
   - `screenscraper.user_password`: Your ScreenScraper password
   - `paths.roms`: Path to your ROM directory
   - `paths.es_systems`: Path to your es_systems.xml

3. **Test the config:**
```bash
python -m curateur.cli --config config.yaml --dry-run
```

### Next Phase: ROM Scanner

The next implementation phase will add ROM scanning functionality. See `TODO.md` Phase 2 for tasks.

Key files to implement:
- `curateur/scanner/rom_scanner.py`: Main scanning logic
- `curateur/scanner/m3u_parser.py`: M3U playlist handling
- `curateur/scanner/disc_handler.py`: Disc subdirectory support
- `curateur/scanner/hash_calculator.py`: CRC32 computation

### Development Tools

#### Generate System Map (when updating)
```bash
# First, fetch systemesListe.xml from ScreenScraper API
python -m curateur.tools.generate_system_map \
    --es-systems es_systems.xml \
    --systemes-liste systemesListe.xml
```

#### Setup Developer Credentials (maintainer only)
```bash
python -m curateur.tools.setup_dev_credentials
# Follow prompts, then copy output to credentials.py
```

#### Verify Existing Credentials
```bash
python -m curateur.tools.setup_dev_credentials --verify
```

### Project Status

✅ **Phase 1 Complete** - Core infrastructure ready
- Configuration system
- Credential management
- ES-DE systems parsing
- Platform mapping
- CLI framework

🚧 **Phase 2 In Progress** - ROM scanner
📋 **Phases 3-6 Planned** - API client, media downloader, gamelist generator, runtime

See `IMPLEMENTATION_PLAN.md` for full architecture details.
