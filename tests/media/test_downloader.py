from pathlib import Path

import pytest

from curateur.media.downloader import ImageDownloader


class DummyClient:
    def __init__(self, content: bytes, content_type: str = "image/png"):
        self._content = content
        self._content_type = content_type
        self.calls = 0

    async def get(self, url, timeout=None, headers=None):
        self.calls += 1

        class Response:
            def __init__(self, content, content_type):
                self.content = content
                self.headers = {"Content-Type": content_type}

            def raise_for_status(self):
                return None

        return Response(self._content, self._content_type)


def _make_png_bytes(width=2, height=2):
    from PIL import Image
    from io import BytesIO

    img = Image.new("RGB", (width, height), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_image_downloader_downloads_and_validates(tmp_path):
    png_bytes = _make_png_bytes()
    client = DummyClient(png_bytes)
    downloader = ImageDownloader(client=client, validation_mode="normal", min_width=1, min_height=1)

    out = tmp_path / "image.png"
    ok, err = await downloader.download("http://example/image.png", out)

    assert ok is True
    assert err is None
    assert out.exists()
    assert client.calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_image_downloader_rejects_small_images(tmp_path):
    png_bytes = _make_png_bytes(width=1, height=1)
    client = DummyClient(png_bytes)
    downloader = ImageDownloader(client=client, validation_mode="normal", min_width=5, min_height=5, max_retries=1)

    out = tmp_path / "small.png"
    ok, err = await downloader.download("http://example/small.png", out)

    assert ok is False
    assert "Image too small" in err
