import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from curateur.media.media_downloader import MediaDownloader, DownloadResult


class DummyDownloader:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    async def download(self, url, output_path, validate=True):
        self.calls.append((url, output_path, validate))
        if self.success:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("data")
            return True, None
        return False, "fail"

    def get_image_dimensions(self, path):
        return (1, 1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_success_and_summary(tmp_path):
    # Stub url selector to return deterministic media list
    dummy_selector = SimpleNamespace(
        enabled_media_types=["box-2D", "ss"],
        select_media_urls=lambda media_list, rom_filename: {
            "box-2D": {"url": "http://example/cover", "format": "jpg"},
            "ss": {"url": "http://example/shot", "format": "png"},
        },
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        preferred_regions=["us"],
        enabled_media_types=["box-2D", "ss"],
    )
    # Inject dummy selector/downloader
    downloader.url_selector = dummy_selector
    dummy = DummyDownloader(success=True)
    downloader.downloader = dummy

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes")
    assert count == 2
    assert all(isinstance(r, DownloadResult) for r in results)
    assert all(r.success for r in results)
    # Dimensions filled for images
    assert results[0].dimensions == (1, 1)

    summary = downloader.get_media_summary(results)
    assert summary["total"] == 2
    assert summary["successful"] == 2
    assert summary["failed"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_handles_missing_url(tmp_path):
    dummy_selector = SimpleNamespace(
        enabled_media_types=["box-2D"],
        select_media_urls=lambda media_list, rom_filename: {"box-2D": {"format": "jpg"}},
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        enabled_media_types=["box-2D"],
    )
    downloader.url_selector = dummy_selector
    downloader.downloader = DummyDownloader(success=False)

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes")
    assert count == 1
    assert results[0].success is False
    assert "No URL" in results[0].error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_respects_shutdown(tmp_path):
    dummy_selector = SimpleNamespace(
        enabled_media_types=["box-2D"],
        select_media_urls=lambda media_list, rom_filename: {"box-2D": {"url": "http://example/cover", "format": "jpg"}},
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        enabled_media_types=["box-2D"],
    )
    downloader.url_selector = dummy_selector
    downloader.downloader = DummyDownloader(success=True)

    event = asyncio.Event()
    event.set()

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes", shutdown_event=event)
    assert count == 1
    assert results[0].success is False
    assert "Cancelled" in results[0].error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_skips_validation_for_non_images(tmp_path):
    dummy_selector = SimpleNamespace(
        enabled_media_types=["manuel", "video"],
        select_media_urls=lambda media_list, rom_filename: {
            "manuel": {"url": "http://example/manual", "format": "pdf"},
            "video": {"url": "http://example/video", "format": "mp4"},
        },
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        enabled_media_types=["manuel", "video"],
    )
    dummy = DummyDownloader(success=True)
    downloader.downloader = dummy
    downloader.url_selector = dummy_selector

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes")
    assert count == 2
    # Dimensions should remain None because validation skipped
    assert all(r.dimensions is None for r in results)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_uses_semaphore_and_progress_callback(tmp_path):
    dummy_selector = SimpleNamespace(
        enabled_media_types=["box-2D"],
        select_media_urls=lambda media_list, rom_filename: {"box-2D": {"url": "http://example/cover", "format": "jpg"}},
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        enabled_media_types=["box-2D"],
    )
    dummy = DummyDownloader(success=True)
    downloader.downloader = dummy
    downloader.url_selector = dummy_selector

    semaphore = asyncio.Semaphore(1)
    downloader.download_semaphore = semaphore
    callbacks = []

    def progress(media_type, idx, total):
        callbacks.append((media_type, idx, total))

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes", progress_callback=progress)
    assert count == 1
    assert callbacks == [("box-2D", 1, 1)]
    assert semaphore._value in (0, 1)  # consumed then released


@pytest.mark.unit
@pytest.mark.asyncio
async def test_media_downloader_strict_hash(monkeypatch, tmp_path):
    dummy_selector = SimpleNamespace(
        enabled_media_types=["box-2D"],
        select_media_urls=lambda media_list, rom_filename: {"box-2D": {"url": "http://example/cover", "format": "jpg"}},
    )
    downloader = MediaDownloader(
        media_root=tmp_path / "media",
        client=None,
        enabled_media_types=["box-2D"],
        validation_mode="strict",
        hash_algorithm="crc32",
    )
    downloader.url_selector = dummy_selector
    dummy = DummyDownloader(success=True)
    downloader.downloader = dummy

    # Capture hash calculation
    monkeypatch.setattr(
        "curateur.media.media_downloader.asyncio.to_thread",
        lambda func, *args, **kwargs: asyncio.sleep(0, result="HASH"),
    )

    results, count = await downloader.download_media_for_game([], "Game.nes", "nes")
    assert results[0].hash_value == "HASH"


@pytest.mark.unit
def test_check_existing_media(tmp_path):
    media_root = tmp_path / "media"
    path = media_root / "nes" / "covers" / "Game.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("img")

    downloader = MediaDownloader(
        media_root=media_root,
        client=None,
        enabled_media_types=["box-2D", "ss"],
    )
    existing = downloader.check_existing_media("nes", "Game")
    assert existing["box-2D"] is True
    assert existing["ss"] is False
