# MAME ROM Organizer for ES-DE

A comprehensive tool for organizing MAME ROM sets, parsing local metadata sources, and generating ES-DE compatible gamelist.xml files.

## Features

- **Metadata Parsing**: Extracts metadata from MAME XML, history.xml, and INI files
- **Smart Filtering**: Filter games by quality ratings, genres, player counts, or custom lists
- **Clone Inheritance**: Automatically inherits metadata from parent ROMs for clones
- **Media Organization**: Extracts images from MAME Extras zip archives and organizes videos
- **ROM Management**: Copies ROMs and CHDs to ES-DE directory with validation
- **Disk Space Validation**: Checks available space before copying to prevent failures
- **Incremental Updates**: Skips files that haven't changed (size+timestamp matching)
- **ES-DE Compatible**: Generates properly formatted gamelist.xml files

## Requirements

### Source Files

1. **MAME ROM Set** (non-merged): Directory containing `.zip` files
2. **MAME CHD Set** (optional): Directory with subdirectories containing `.chd` files
3. **MAME XML**: Full machine list (e.g., `mame0283.xml`)
4. **MAME Extras**: Directory containing:
   - `/folders/bestgames.ini` - Quality ratings
   - `/folders/genre.ini` - Genre categories
   - `/folders/multiplayer.ini` - Player counts
   - `/folders/Game or No Game.ini` (optional) - Game filter
   - `/history/history.xml` - Game descriptions
   - `titles.zip`, `snap.zip`, `marquees.zip`, `flyers.zip`, `cabinets.zip`, `cpanel.zip`, `manuals.zip`
5. **MAME Multimedia** (optional): Directory with `/videosnaps/*.mp4` files

## Installation

The MAME organizer is included with curateur. Install curateur and its dependencies:

```bash
pip install -e .
```

## Configuration

1. Copy the example configuration:
   ```bash
   cp mame_config.yaml.example mame_config.yaml
   ```

2. Edit `mame_config.yaml` and set your paths:
   ```yaml
   source_rom_path: "/path/to/mame/roms"
   source_chd_path: "/path/to/mame/chds"
   mame_xml_path: "/path/to/mame0283.xml"
   multimedia_path: "/path/to/mame/multimedia"
   extras_path: "/path/to/mame/extras"
   
   target_rom_path: "/path/to/ES-DE/ROMs/mame"
   gamelist_output_path: "/path/to/ES-DE/gamelists/mame/gamelist.xml"
   media_output_path: "/path/to/ES-DE/media/mame"
   ```

3. Configure filtering options:
   ```yaml
   # Process only high-quality games
   minimum_rating: 0.7
   favorite_threshold: 0.9
   
   # Or use a custom game list
   inclusion_list_path: "/path/to/my_games.txt"
   ```

## Usage

### Basic Usage

Run with default configuration:
```bash
curateur-mame
```

### Custom Configuration

Use a different config file:
```bash
curateur-mame --config /path/to/my_config.yaml
```

### Command-Line Overrides

Override config values:
```bash
curateur-mame \
  --source-roms /mame/roms \
  --target-roms /ES-DE/roms/mame \
  --min-rating 0.8 \
  --favorite-threshold 0.9
```

### Dry Run

Test without copying files:
```bash
curateur-mame --dry-run
```

## Filtering Options

### By Quality Rating

Use `bestgames.ini` ratings (0.0 to 1.0):
```yaml
minimum_rating: 0.7  # Only games rated 70% or higher
favorite_threshold: 0.9  # Mark 90%+ games as favorites
```

### By Inclusion List

Provide a plain text file with one ROM shortname per line:
```yaml
inclusion_list_path: "/path/to/games.txt"
```

Example `games.txt`:
```
pacman
mspacman
galaga
donkeykong
```

### By Game Filter

Use "Game or No Game.ini" to filter out utilities and BIOS:
```yaml
use_game_or_no_game: true
```

### Combined Filtering

Filters are applied in order:
1. Inclusion list (if provided)
2. Minimum rating (if provided)
3. Game or No Game filter (if enabled)

## Media Types

The tool maps MAME Extras to ES-DE media types:

| MAME Extras     | ES-DE Type      | Description        |
|-----------------|-----------------|-------------------|
| titles.zip      | titlescreens/   | Title screens     |
| snap.zip        | screenshots/    | Screenshots       |
| marquees.zip    | marquees/       | Marquee artwork   |
| flyers.zip      | covers/         | Flyer artwork     |
| cabinets.zip    | 3dboxes/        | Cabinet photos    |
| cpanel.zip      | backcovers/     | Control panels    |
| manuals.zip     | manuals/        | Game manuals      |
| videosnaps/*.mp4| videos/         | Video previews    |

## Metadata Sources

The tool generates gamelist entries with:

- **name**: From MAME XML `<description>`
- **desc**: From history.xml entries
- **releasedate**: From MAME XML `<year>` (formatted as YYYYMMDD)
- **developer**: From MAME XML `<manufacturer>`
- **genre**: From genre.ini categories
- **players**: From multiplayer.ini categories
- **rating**: From bestgames.ini quality tiers (0.0-1.0)
- **favorite**: Auto-set based on rating threshold

## Clone Handling

When a ROM is identified as a clone (via `cloneof` attribute in MAME XML):
- If the parent ROM is in scope, missing metadata is inherited
- Favorites status is inherited from parent
- If parent is not in scope, a warning is logged and no inheritance occurs

## Disk Space Management

Before copying files, the tool:
1. Calculates total space required for ROMs and CHDs
2. Checks available space on target drive
3. Fails early with clear error if insufficient space
4. Logs size of each CHD directory before copying

## Incremental Updates

When re-running the tool:
- Files matching size and timestamp are skipped
- New/updated source files overwrite existing files
- Missing source files preserve existing files
- Media files already present are not re-extracted

## Example Workflows

### High-Quality Arcade Collection

```yaml
minimum_rating: 0.7
use_game_or_no_game: true
favorite_threshold: 0.9
```

This creates a curated collection of well-rated arcade games with the best marked as favorites.

### Custom Game List

```yaml
inclusion_list_path: "my_favorites.txt"
favorite_threshold: null
```

Process only games from your custom list.

### Complete MAME Set

```yaml
inclusion_list_path: null
minimum_rating: null
use_game_or_no_game: true
favorite_threshold: null
```

Process all playable games (excluding utilities and BIOS).

## Troubleshooting

### "MAME XML file not found"

Ensure the MAME XML path is correct:
```bash
curateur-mame --mame-xml /correct/path/to/mame0283.xml
```

### "Insufficient disk space"

The tool calculates required space before copying. Free up space on the target drive or adjust filtering to reduce the ROM count.

### "CHD directory missing discs"

The tool will copy partial CHD directories with a warning. Check the MAME XML to see which discs are required.

### "ROM not found"

Some ROMs in MAME XML may not be in your set. These are logged but don't stop execution. Ensure you're using a complete non-merged ROM set.

### Memory Issues

The tool loads MAME XML and history.xml into memory (50MB+ each). If you experience memory issues, ensure your system has at least 1GB of available RAM.

## Performance Notes

- **Parsing**: MAME XML and history.xml parsing takes 30-60 seconds each
- **ROM Copying**: Depends on file count and disk speed
- **CHD Copying**: CHDs can be several GB each, allow adequate time
- **Media Extraction**: Processed sequentially, ~500 games takes several minutes
- **Overall**: Expect 10-30 minutes for a full run with 500-1000 games

## License

Same as curateur (see LICENSE file in repository root).
