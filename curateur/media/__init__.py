"""
Media downloader package for curateur.

Handles downloading, validating, and organizing game media from ScreenScraper.
"""

from .downloader import DownloadError, ImageDownloader, ValidationError
from .media_downloader import DownloadResult, MediaDownloader
from .media_types import MEDIA_TYPE_MAP, MediaType, get_directory_for_media_type
from .organizer import MediaOrganizer
from .region_selector import (
    detect_region_from_filename,
    get_media_for_region,
    select_best_region,
    should_use_region_filtering,
)
from .url_selector import MediaURLSelector

__all__ = [
    "MediaType",
    "MEDIA_TYPE_MAP",
    "get_directory_for_media_type",
    "detect_region_from_filename",
    "select_best_region",
    "get_media_for_region",
    "should_use_region_filtering",
    "MediaURLSelector",
    "ImageDownloader",
    "DownloadError",
    "ValidationError",
    "MediaOrganizer",
    "MediaDownloader",
    "DownloadResult",
]
