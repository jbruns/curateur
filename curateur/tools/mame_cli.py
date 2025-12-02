"""Command-line interface for MAME ROM organizer."""

import sys
import logging
import argparse
import yaml
from pathlib import Path
from typing import Optional

from curateur.mame.mame_gamelist_generator import MAMEGamelistGenerator, MAMEConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser for MAME command."""
    parser = argparse.ArgumentParser(
        prog='curateur-mame',
        description='MAME ROM Organizer for ES-DE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration from mame_config.yaml in current directory
  curateur-mame

  # Use custom config file
  curateur-mame --config /path/to/mame_config.yaml

  # Override config values from command line
  curateur-mame --source-roms /roms/mame --target-roms /ES-DE/roms/mame

  # Dry run to validate without copying
  curateur-mame --dry-run

  # Filter by rating and set favorites
  curateur-mame --min-rating 0.7 --favorite-threshold 0.9

For configuration file format, see mame_config.yaml.example
        """
    )

    parser.add_argument(
        '--config',
        type=Path,
        default=Path('mame_config.yaml'),
        metavar='PATH',
        help='Path to MAME config file (default: ./mame_config.yaml)'
    )

    # Source paths
    parser.add_argument(
        '--source-roms',
        type=Path,
        metavar='PATH',
        help='Path to source MAME ROM directory (overrides config)'
    )

    parser.add_argument(
        '--source-chds',
        type=Path,
        metavar='PATH',
        help='Path to source MAME CHD directory (overrides config)'
    )

    parser.add_argument(
        '--mame-xml',
        type=Path,
        metavar='PATH',
        help='Path to MAME XML file (overrides config)'
    )

    parser.add_argument(
        '--multimedia',
        type=Path,
        metavar='PATH',
        help='Path to MAME Multimedia directory (overrides config)'
    )

    parser.add_argument(
        '--extras',
        type=Path,
        metavar='PATH',
        help='Path to MAME Extras directory (overrides config)'
    )

    # Output paths
    parser.add_argument(
        '--target-roms',
        type=Path,
        metavar='PATH',
        help='Path to target ROM directory (overrides config)'
    )

    parser.add_argument(
        '--output-gamelist',
        type=Path,
        metavar='PATH',
        help='Path to output gamelist.xml (overrides config)'
    )

    parser.add_argument(
        '--output-media',
        type=Path,
        metavar='PATH',
        help='Path to output media directory (overrides config)'
    )

    # Filtering options
    parser.add_argument(
        '--inclusion-list',
        type=Path,
        metavar='PATH',
        help='Path to inclusion list file (overrides config)'
    )

    parser.add_argument(
        '--min-rating',
        type=float,
        metavar='RATING',
        help='Minimum rating threshold 0.0-1.0 (overrides config)'
    )

    parser.add_argument(
        '--game-or-no-game',
        action='store_true',
        help='Use Game or No Game.ini filter (overrides config)'
    )

    parser.add_argument(
        '--favorite-threshold',
        type=float,
        metavar='RATING',
        help='Favorite threshold 0.0-1.0 (overrides config)'
    )

    # Processing options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate and log without copying files (overrides config)'
    )

    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip gamelist validation after generation'
    )

    return parser


def load_config_file(config_path: Path) -> dict:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is malformed
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if not config:
        raise ValueError(f"Config file is empty: {config_path}")
    
    return config


def apply_cli_overrides(config: dict, args: argparse.Namespace) -> dict:
    """Apply command-line argument overrides to config.
    
    Args:
        config: Configuration dictionary
        args: Parsed arguments
        
    Returns:
        Updated configuration dictionary
    """
    # Source paths
    if args.source_roms:
        config['source_rom_path'] = str(args.source_roms)
    if args.source_chds:
        config['source_chd_path'] = str(args.source_chds)
    if args.mame_xml:
        config['mame_xml_path'] = str(args.mame_xml)
    if args.multimedia:
        config['multimedia_path'] = str(args.multimedia)
    if args.extras:
        config['extras_path'] = str(args.extras)
    
    # Output paths
    if args.target_roms:
        config['target_rom_path'] = str(args.target_roms)
    if args.output_gamelist:
        config['gamelist_output_path'] = str(args.output_gamelist)
    if args.output_media:
        config['media_output_path'] = str(args.output_media)
    
    # Filtering
    if args.inclusion_list:
        config['inclusion_list_path'] = str(args.inclusion_list)
    if args.min_rating is not None:
        config['minimum_rating'] = args.min_rating
    if args.game_or_no_game:
        config['use_game_or_no_game'] = True
    if args.favorite_threshold is not None:
        config['favorite_threshold'] = args.favorite_threshold
    
    # Processing
    if args.dry_run:
        config['dry_run'] = True
    if args.no_validate:
        config['validate_output'] = False
    
    return config


def validate_config(config: dict) -> list:
    """Validate configuration and return list of errors.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    # Required source paths
    required_sources = [
        ('source_rom_path', 'Source ROM path'),
        ('mame_xml_path', 'MAME XML path'),
        ('extras_path', 'MAME Extras path'),
    ]
    
    for key, name in required_sources:
        if key not in config or not config[key]:
            errors.append(f"{name} is required")
    
    # Required output paths
    required_outputs = [
        ('target_rom_path', 'Target ROM path'),
        ('gamelist_output_path', 'Gamelist output path'),
        ('media_output_path', 'Media output path'),
    ]
    
    for key, name in required_outputs:
        if key not in config or not config[key]:
            errors.append(f"{name} is required")
    
    # Validate rating thresholds
    if 'minimum_rating' in config and config['minimum_rating'] is not None:
        rating = config['minimum_rating']
        if not isinstance(rating, (int, float)) or rating < 0.0 or rating > 1.0:
            errors.append(f"minimum_rating must be between 0.0 and 1.0, got: {rating}")
    
    if 'favorite_threshold' in config and config['favorite_threshold'] is not None:
        rating = config['favorite_threshold']
        if not isinstance(rating, (int, float)) or rating < 0.0 or rating > 1.0:
            errors.append(f"favorite_threshold must be between 0.0 and 1.0, got: {rating}")
    
    return errors


def config_to_mame_config(config: dict) -> MAMEConfig:
    """Convert config dictionary to MAMEConfig object.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        MAMEConfig object
    """
    return MAMEConfig(
        source_rom_path=Path(config['source_rom_path']).expanduser(),
        source_chd_path=Path(config['source_chd_path']).expanduser() if config.get('source_chd_path') else None,
        mame_xml_path=Path(config['mame_xml_path']).expanduser(),
        multimedia_path=Path(config['multimedia_path']).expanduser() if config.get('multimedia_path') else None,
        extras_path=Path(config['extras_path']).expanduser(),
        target_rom_path=Path(config['target_rom_path']).expanduser(),
        gamelist_output_path=Path(config['gamelist_output_path']).expanduser(),
        media_output_path=Path(config['media_output_path']).expanduser(),
        inclusion_list_path=Path(config['inclusion_list_path']).expanduser() if config.get('inclusion_list_path') else None,
        minimum_rating=config.get('minimum_rating'),
        use_game_or_no_game=config.get('use_game_or_no_game', False),
        favorite_threshold=config.get('favorite_threshold'),
        auto_sortname_enabled=config.get('auto_sortname_enabled', False),
        dry_run=config.get('dry_run', False),
        merge_strategy=config.get('merge_strategy', 'refresh_metadata'),
        validate_output=config.get('validate_output', True)
    )


def main(argv: Optional[list] = None) -> int:
    """Main entry point for MAME CLI.
    
    Args:
        argv: Command-line arguments (default: sys.argv)
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # Load configuration
    try:
        config = load_config_file(args.config)
        logger.info(f"Loaded configuration from: {args.config}")
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        logger.error(f"Create {args.config} from mame_config.yaml.example")
        return 1
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return 1
    
    # Apply CLI overrides
    config = apply_cli_overrides(config, args)
    
    # Validate configuration
    errors = validate_config(config)
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return 1
    
    # Convert to MAMEConfig
    try:
        mame_config = config_to_mame_config(config)
    except Exception as e:
        logger.error(f"Error creating MAME configuration: {e}")
        return 1
    
    # Run generator
    logger.info("\n" + "=" * 60)
    logger.info("MAME ROM Organizer for ES-DE")
    logger.info("=" * 60)
    
    if mame_config.dry_run:
        logger.info("DRY RUN MODE - No files will be copied")
    
    generator = MAMEGamelistGenerator(mame_config)
    
    try:
        success = generator.generate()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.error("\n\nOperation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nFatal error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
