"""
core/rate_limit_utils.py

Helper dùng CHUNG cho mọi nơi gọi Gemini API trong project.
Tích hợp pacer toàn tiến trình + retry exponential backoff + simple_generate.
"""
from __future__ import annotations

import asyncio
import os
import random
import time


class GeminiCallPacer:
    """Pacer toàn tiến trình: ép khoảng cách tối thiểu giữa các lần gọi Gemini."""

    def __init__(self, min_interval_seconds: float = 7.0):
        self.min_interval_seconds = min_interval_seconds
        self._lock: asyncio.Lock | None = None
        self._last_call_at: float = 0.0

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def wait_turn(self) -> None:
        async with self._get_lock():
            now = time.monotonic()
            elapsed = now - self._last_call_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_call_at = time.monotonic()


gemini_pacer = GeminiCallPacer(min_interval_seconds=7.0)


def _is_quota_error(e: Exception) -> bool:
    err_str = str(e)
    if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
        return True
    for cls in type(e).__mro__:
        name = cls.__name__
        if "ResourceExhausted" in name or "RateLimitError" in name:
            return True
    return False


async def call_with_retry(
    coro_fn,
    *args,
    max_attempts: int = 5,
    base_delay: float = 15.0,
    max_delay: float = 90.0,
    **kwargs,
):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        await gemini_pacer.wait_turn()
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            if _is_quota_error(e):
                last_exc = e
                if attempt < max_attempts - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    delay += random.uniform(0, 4.0)
                    print(
                        f"Rate limit hit (429). Retrying in {delay:.0f}s "
                        f"(attempt {attempt + 1}/{max_attempts})..."
                    )
                    await asyncio.sleep(delay)
                continue
            raise
    assert last_exc is not None
    raise last_exc


async def simple_generate(prompt: str, model: str | None = None) -> str:
    """Gọi Gemini API trực tiếp (không qua ADK runner), với pacer + retry."""
    from google import genai as _genai

    if model is None:
        from core.config import GEMINI_MODEL
        model = GEMINI_MODEL

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    client = _genai.Client(api_key=api_key)

    last_exc: Exception | None = None
    for attempt in range(5):
        await gemini_pacer.wait_turn()
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model, contents=prompt
                ),
            )
            return response.text or ""
        except Exception as e:
            if _is_quota_error(e):
                last_exc = e
                if attempt < 4:
                    delay = min(15.0 * (2 ** attempt), 90.0) + random.uniform(0, 4.0)
                    print(f"Rate limit hit (429). Retrying in {delay:.0f}s (attempt {attempt + 1}/5)...")
                    await asyncio.sleep(delay)
                continue
            raise
    assert last_exc is not None
    raise last_exc