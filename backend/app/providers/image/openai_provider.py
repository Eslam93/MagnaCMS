"""OpenAI `gpt-image-1` provider.

Same retry/cost/logging contract as the chat provider. Quality maps
directly to OpenAI's `quality` parameter; size defaults to 1024×1024
(the only size the protocol guarantees).
"""

from __future__ import annotations

import asyncio
import base64
import random
import time
from typing import Any, Final

import openai
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.errors import ProviderConfigError, ProviderError, ProviderRetryExhausted
from app.providers.image.base import ImageQuality, ImageResult

log = get_logger(__name__)

# USD per image at 1024×1024. Hand-maintained — sync when OpenAI ships
# a new price sheet.
_PRICE_PER_IMAGE: Final[dict[tuple[str, ImageQuality], float]] = {
    ("gpt-image-1", ImageQuality.LOW): 0.011,
    ("gpt-image-1", ImageQuality.MEDIUM): 0.042,
    ("gpt-image-1", ImageQuality.HIGH): 0.167,
}


def _compute_cost_usd(model: str, quality: ImageQuality) -> float:
    price = _PRICE_PER_IMAGE.get((model, quality))
    if price is None:
        log.warning("openai_image_unknown_pricing", model=model, quality=quality.value)
        return 0.0
    return price


_RETRYABLE_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAIImageProvider:
    """Production image provider against OpenAI's `gpt-image-1`."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        if client is None:
            if settings.openai_api_key is None:
                raise ProviderConfigError(
                    "OPENAI_API_KEY is required when AI_PROVIDER_MODE=openai."
                )
            client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=timeout_seconds or settings.openai_timeout_seconds,
                max_retries=0,
            )
        self._client = client
        self._model = model or settings.openai_image_model
        self._max_retries = max_retries or settings.openai_max_retries

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        *,
        prompt: str,
        quality: ImageQuality = ImageQuality.MEDIUM,
        size: tuple[int, int] = (1024, 1024),
    ) -> ImageResult:
        width, height = size
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "quality": quality.value,
        }
        return await self._call_with_retry(
            request_kwargs,
            prompt=prompt,
            quality=quality,
            width=width,
            height=height,
        )

    async def _call_with_retry(
        self,
        request_kwargs: dict[str, Any],
        *,
        prompt: str,
        quality: ImageQuality,
        width: int,
        height: int,
    ) -> ImageResult:
        started = time.perf_counter()
        last_exc: BaseException | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.images.generate(**request_kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                log.warning(
                    "openai_image_retryable_error",
                    attempt=attempt,
                    max_attempts=self._max_retries,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_seconds(attempt))
                    continue
                break
            except openai.OpenAIError as exc:
                log.error(
                    "openai_image_non_retryable_error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise ProviderError(f"OpenAI image call failed: {exc}") from exc
            else:
                return self._build_result(
                    response,
                    prompt=prompt,
                    quality=quality,
                    width=width,
                    height=height,
                    started=started,
                )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log.error(
            "openai_image_retry_exhausted",
            attempts=self._max_retries,
            elapsed_ms=elapsed_ms,
            last_error=str(last_exc),
        )
        raise ProviderRetryExhausted(
            f"OpenAI image call exhausted {self._max_retries} retries: {last_exc}"
        ) from last_exc

    def _build_result(
        self,
        response: Any,
        *,
        prompt: str,
        quality: ImageQuality,
        width: int,
        height: int,
        started: float,
    ) -> ImageResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not response.data:
            raise ProviderError("OpenAI image response contained no data.")
        b64 = response.data[0].b64_json
        if not b64:
            raise ProviderError("OpenAI image response missing b64_json payload.")
        image_bytes = base64.b64decode(b64)
        cost_usd = _compute_cost_usd(self._model, quality)

        log.info(
            "openai_image_generation",
            model=self._model,
            quality=quality.value,
            size=f"{width}x{height}",
            bytes=len(image_bytes),
            cost_usd=round(cost_usd, 4),
            latency_ms=elapsed_ms,
        )
        return ImageResult(
            image_bytes=image_bytes,
            width=width,
            height=height,
            model=self._model,
            quality=quality,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            prompt_used=prompt,
        )

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        base = float(2 ** (attempt - 1))
        jitter = random.uniform(0, 0.25 * base)  # noqa: S311 — jitter, not crypto
        return base + jitter
