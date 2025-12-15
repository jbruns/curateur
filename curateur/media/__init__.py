"""
Media downloader package for curateur.

Handles downloading, validating, and organizing game media from ScreenScraper.
"""

from .media_types import MediaType, MEDIA_TYPE_MAP, get_directory_for_media_type
from .region_selector import (
    detect_region_from_filename,
    select_best_region,
    get_media_for_region,
    should_use_region_filtering,
)
from .url_selector import MediaURLSelector
from .downloader import ImageDownloader, DownloadError, ValidationError
from .organizer import MediaOrganizer
from .media_downloader import MediaDownloader, DownloadResult

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
