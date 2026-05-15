"""Image storage abstraction.

Two implementations live behind one Protocol:

  - `LocalImageStorage` (default in dev) writes bytes to a local
    directory and returns the URL the FastAPI `/local-images/*` static
    mount will serve them from. This is what runs in the demo loop and
    the test suite.
  - `S3ImageStorage` (placeholder) — wires through to boto3 and a
    presigned URL once the deploy story is ready. Not part of this
    slice's local-first contract.

`build_image_storage()` picks the right one based on
`IMAGES_CDN_BASE_URL`. The image service consumes only the Protocol
so swapping is a config change.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Slice 3 ships local-disk storage only. Filenames are UUIDv4 so two
# tests/demos never collide. The directory is created lazily on first
# write — keeps the test suite from needing fixtures.
LOCAL_IMAGES_DIR: Path = Path(__file__).resolve().parents[2] / "local_images"


class IImageStorage(Protocol):
    """Upload-then-return-URL surface. Implementations decide whether
    that means S3 + presigned URL or local-disk + static mount.
    """

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> tuple[str, str]:
        """Persist `image_bytes` and return `(storage_key, cdn_url)`.

        `storage_key` is the implementation-private identifier (filename
        for local; S3 object key for cloud). `cdn_url` is the public-
        facing URL the frontend renders via `<img src=...>`.
        """
        ...


class LocalImageStorage:
    """Write bytes to `LOCAL_IMAGES_DIR/<uuid>.<ext>` and serve via the
    `/local-images/*` mount declared in `app.main`."""

    def __init__(self, *, base_url: str, directory: Path | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._directory = directory or LOCAL_IMAGES_DIR

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> tuple[str, str]:
        self._directory.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4().hex}.{extension.lstrip('.')}"
        path = self._directory / key
        path.write_bytes(image_bytes)
        url = f"{self._base_url}/{key}"
        log.info(
            "local_image_stored",
            key=key,
            bytes=len(image_bytes),
            url=url,
        )
        return key, url


def build_image_storage() -> IImageStorage:
    """Pick the storage implementation based on settings.

    Today: local-disk for every environment. The hosted S3 path lands
    with the deploy batch in the final hours of the 24h budget.
    """
    settings = get_settings()
    return LocalImageStorage(base_url=settings.images_cdn_base_url)
