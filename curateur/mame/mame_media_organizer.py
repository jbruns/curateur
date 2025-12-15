"""Organize MAME media files from Extras and Multimedia sources.

Coordinates extraction from zip archives and copying of video files to ES-DE structure.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, Optional, Set
from dataclasses import dataclass

from .media_extractor import MediaExtractor

logger = logging.getLogger(__name__)


@dataclass
class MediaStats:
    """Statistics for media organization."""

    videos_copied: int = 0
    videos_skipped: int = 0
    images_by_type: Dict[str, int] = None

    def __post_init__(self):
        if self.images_by_type is None:
            self.images_by_type = {}


class MAMEMediaOrganizer:
    """Organizes MAME media files to ES-DE directory structure."""

    def __init__(
        self,
        extras_path: Path,
        multimedia_path: Optional[Path],
        media_output_path: Path,
    ):
        """Initialize media organizer.

        Args:
            extras_path: Path to MAME Extras directory (contains zip files)
            multimedia_path: Optional path to MAME Multimedia directory
            media_output_path: Base output path for media (e.g., .../media/mame/)
        """
        self.extras_path = extras_path
        self.multimedia_path = multimedia_path
        self.media_output_path = media_output_path
        self.extractor = MediaExtractor(extras_path)

    def organize_media(self, shortnames: Set[str], dry_run: bool = False) -> MediaStats:
        """Organize media files for specified games.

        Args:
            shortnames: Set of MAME shortnames to organize media for
            dry_run: If True, only log without copying

        Returns:
            MediaStats with operation results
        """
        stats = MediaStats()

        if dry_run:
            logger.info("Dry run mode: skipping media extraction")
            return stats

        # Create base media directory
        self.media_output_path.mkdir(parents=True, exist_ok=True)

        # Extract images from MAME Extras zip files
        logger.info(f"Extracting media from MAME Extras: {self.extras_path}")
        extracted_media = self.extractor.extract_media_for_games(
            shortnames=shortnames, output_base_path=self.media_output_path
        )

        # Count extracted images by type
        for shortname, media_dict in extracted_media.items():
            for media_type in media_dict.keys():
                stats.images_by_type[media_type] = (
                    stats.images_by_type.get(media_type, 0) + 1
                )

        # Copy videos from MAME Multimedia
        if self.multimedia_path:
            logger.info(f"Copying videos from MAME Multimedia: {self.multimedia_path}")
            self._copy_videos(shortnames, stats)
        else:
            logger.info("MAME Multimedia path not provided, skipping videos")

        # Log summary
        logger.info("Media organization complete:")
        for media_type, count in sorted(stats.images_by_type.items()):
            logger.info(f"  {media_type}: {count} files")
        if self.multimedia_path:
            logger.info(
                f"  videos: {stats.videos_copied} copied, {stats.videos_skipped} skipped"
            )

        return stats

    def _copy_videos(self, shortnames: Set[str], stats: MediaStats):
        """Copy video files from MAME Multimedia.

        Args:
            shortnames: Set of MAME shortnames
            stats: MediaStats to update
        """
        if not self.multimedia_path.exists():
            logger.warning(
                f"MAME Multimedia path does not exist: {self.multimedia_path}"
            )
            return

        # Videos are in /videosnaps/ subdirectory
        videosnaps_path = self.multimedia_path / "videosnaps"
        if not videosnaps_path.exists():
            logger.warning(f"videosnaps directory not found: {videosnaps_path}")
            return

        # Create videos output directory
        videos_output_dir = self.media_output_path / "videos"
        videos_output_dir.mkdir(parents=True, exist_ok=True)

        for shortname in sorted(shortnames):
            source_video = videosnaps_path / f"{shortname}.mp4"
            target_video = videos_output_dir / f"{shortname}.mp4"

            if not source_video.exists():
                logger.debug(f"Video not found: {shortname}.mp4")
                continue

            # Skip if already exists with matching size/timestamp
            if target_video.exists():
                source_stat = source_video.stat()
                target_stat = target_video.stat()
                if (
                    source_stat.st_size == target_stat.st_size
                    and abs(source_stat.st_mtime - target_stat.st_mtime) < 2
                ):
                    logger.debug(f"Skipping {shortname}.mp4 (already exists)")
                    stats.videos_skipped += 1
                    continue
                else:
                    # File exists but differs - remove it before copying
                    logger.debug(f"Removing outdated {shortname}.mp4 before copying")
                    try:
                        target_video.unlink()
                    except Exception as e:
                        logger.error(f"Error removing video {shortname}.mp4: {e}")
                        continue

            # Copy video
            try:
                shutil.copy2(source_video, target_video)
                stats.videos_copied += 1
                logger.debug(f"Copied {shortname}.mp4")
            except Exception as e:
                logger.error(f"Error copying video {shortname}.mp4: {e}")
