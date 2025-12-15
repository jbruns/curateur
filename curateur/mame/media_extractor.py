"""Media file extraction from MAME Extras zip archives.

Handles extracting images from various zip files and mapping them to ES-DE media types.
"""

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Mapping from MAME Extras zip files to ES-DE media types
MAME_MEDIA_MAPPING = {
    "titles.zip": "titlescreens",
    "snap.zip": "screenshots",
    "marquees.zip": "marquees",
    "flyers.zip": "covers",
    "cabinets.zip": "3dboxes",
    "cpanel.zip": "backcovers",
    "manuals.zip": "manuals",
}

# Valid image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# Valid extensions by media type
MEDIA_TYPE_EXTENSIONS = {
    "manuals": {".pdf", ".png", ".jpg", ".jpeg"},
    # All other media types use IMAGE_EXTENSIONS
}


class MediaExtractor:
    """Extracts media files from MAME Extras zip archives."""

    def __init__(self, extras_path: Path):
        """Initialize extractor with path to MAME Extras directory.

        Args:
            extras_path: Path to MAME Extras directory containing zip files
        """
        self.extras_path = extras_path
        self.available_archives: Dict[str, Path] = {}
        self._scan_archives()

    def _scan_archives(self):
        """Scan for available media archive files."""
        if not self.extras_path.exists():
            logger.warning(f"MAME Extras path does not exist: {self.extras_path}")
            return

        for archive_name in MAME_MEDIA_MAPPING.keys():
            archive_path = self.extras_path / archive_name
            if archive_path.exists():
                self.available_archives[archive_name] = archive_path
                logger.debug(f"Found media archive: {archive_name}")
            else:
                logger.debug(f"Media archive not found: {archive_name}")

        logger.info(
            f"Found {len(self.available_archives)} of {len(MAME_MEDIA_MAPPING)} media archives"
        )

    def extract_media_for_games(
        self, shortnames: Set[str], output_base_path: Path
    ) -> Dict[str, Dict[str, Path]]:
        """Extract media files for specified games.

        Args:
            shortnames: Set of MAME shortnames to extract media for
            output_base_path: Base path for media output (e.g., .../media/mame/)

        Returns:
            Dictionary mapping shortname to dict of media_type -> file_path
        """
        extracted_media: Dict[str, Dict[str, Path]] = {}

        for shortname in shortnames:
            extracted_media[shortname] = {}

        # Process each archive
        for archive_name, archive_path in self.available_archives.items():
            media_type = MAME_MEDIA_MAPPING[archive_name]
            logger.info(f"Processing {archive_name} -> {media_type}/")

            media_output_dir = output_base_path / media_type
            media_output_dir.mkdir(parents=True, exist_ok=True)

            extracted_count = self._extract_from_archive(
                archive_path=archive_path,
                shortnames=shortnames,
                output_dir=media_output_dir,
                media_type=media_type,
                extracted_media=extracted_media,
            )

            logger.info(f"  Extracted {extracted_count}/{len(shortnames)} files")

        return extracted_media

    def _extract_from_archive(
        self,
        archive_path: Path,
        shortnames: Set[str],
        output_dir: Path,
        media_type: str,
        extracted_media: Dict[str, Dict[str, Path]],
    ) -> int:
        """Extract matching files from a single archive.

        Args:
            archive_path: Path to zip archive
            shortnames: Set of shortnames to match
            output_dir: Output directory for this media type
            media_type: Media type name
            extracted_media: Dictionary to update with extracted files

        Returns:
            Number of files extracted
        """
        extracted_count = 0

        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            try:
                # Extract entire archive to temp directory
                logger.debug(
                    f"Extracting {archive_path.name} to temporary directory..."
                )
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(temp_path)

                # Find and move matching files
                for shortname in shortnames:
                    extracted = self._find_and_move_media(
                        temp_path=temp_path,
                        shortname=shortname,
                        output_dir=output_dir,
                        media_type=media_type,
                    )

                    if extracted:
                        extracted_media[shortname][media_type] = extracted
                        extracted_count += 1

            except zipfile.BadZipFile:
                logger.error(f"Invalid zip file: {archive_path}")
            except Exception as e:
                logger.error(f"Error extracting from {archive_path}: {e}")

        return extracted_count

    def _find_and_move_media(
        self, temp_path: Path, shortname: str, output_dir: Path, media_type: str
    ) -> Optional[Path]:
        """Find and move a media file for a specific game.

        Searches temp directory for files matching the shortname.
        Prefers .png over .jpg when both exist.

        Args:
            temp_path: Temporary extraction directory
            shortname: Game shortname to match
            output_dir: Output directory for this media type
            media_type: Media type name

        Returns:
            Path to moved file, or None if not found
        """
        # Get valid extensions for this media type
        valid_extensions = MEDIA_TYPE_EXTENSIONS.get(media_type, IMAGE_EXTENSIONS)

        # Look for files matching shortname with various extensions
        candidates = []

        # Search recursively in temp directory
        for file_path in temp_path.rglob(f"{shortname}.*"):
            # Check if it's a file (not directory)
            if not file_path.is_file():
                continue

            # Check extension
            ext = file_path.suffix.lower()
            if ext not in valid_extensions:
                logger.warning(
                    f"File {file_path.name} does not have a valid extension for {media_type} "
                    f"({', '.join(sorted(valid_extensions))}), skipping"
                )
                continue

            candidates.append((file_path, ext))

        if not candidates:
            return None

        # Prefer .png over other formats, but .pdf is valid for manuals
        if media_type == "manuals":
            # For manuals, prefer .pdf over images
            candidates.sort(key=lambda x: (x[1] != ".pdf", x[1] != ".png", x[1]))
        else:
            # For images, prefer .png
            candidates.sort(key=lambda x: (x[1] != ".png", x[1]))

        if len(candidates) > 1:
            logger.debug(
                f"Multiple files found for {shortname}, using {candidates[0][0].name}"
            )

        source_file = candidates[0][0]
        dest_file = output_dir / source_file.name

        # Skip if already exists with matching size and timestamp
        if dest_file.exists():
            source_stat = source_file.stat()
            dest_stat = dest_file.stat()
            if (
                source_stat.st_size == dest_stat.st_size
                and abs(source_stat.st_mtime - dest_stat.st_mtime) < 2
            ):
                logger.debug(f"Skipping {dest_file.name} (already exists)")
                return dest_file
            else:
                # File exists but differs - remove it before copying
                logger.debug(f"Removing outdated {dest_file.name} before copying")
                try:
                    dest_file.unlink()
                except Exception as e:
                    logger.error(f"Error removing {dest_file.name}: {e}")
                    return None

        # Copy file
        try:
            shutil.copy2(source_file, dest_file)
            logger.debug(f"Copied {source_file.name} -> {media_type}/")
            return dest_file
        except Exception as e:
            logger.error(f"Error copying {source_file} to {dest_file}: {e}")
            return None

    def get_available_media_types(self) -> List[str]:
        """Get list of available media types based on found archives.

        Returns:
            List of ES-DE media type names
        """
        return [
            MAME_MEDIA_MAPPING[archive_name]
            for archive_name in self.available_archives.keys()
        ]
