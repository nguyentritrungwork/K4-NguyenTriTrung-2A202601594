"""
Assignment 11 — Rate Limiter Plugin (TODO 8).

Enforces per-user rate limits before requests reach the LLM.
Uses a sliding-window counter tracked in memory.
"""
from __future__ import annotations

import time
from collections import defaultdict

from google.genai import types
from google.adk.plugins import base_plugin
from google.adk.agents.invocation_context import InvocationContext


class RateLimitPlugin(base_plugin.BasePlugin):
    """Sliding-window rate limiter plugin.

    Enforces ``max_requests`` per ``window_seconds`` per user_id.
    Uses the invocation_context.user_id when available; falls back to 'anonymous'.

    Attributes:
        max_requests: Maximum allowed requests in the rolling window.
        window_seconds: Length of the rolling window in seconds.
        user_windows: Dict mapping user_id -> list[timestamp] of recent calls.
        blocked_count: Total number of requests blocked by this plugin.
        total_count: Total requests seen by this plugin.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        super().__init__(name="rate_limiter")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # user_id -> list of call timestamps within the current window
        self.user_windows: dict[str, list[float]] = defaultdict(list)
        self.blocked_count: int = 0
        self.total_count: int = 0

    def _get_user_id(self, invocation_context: InvocationContext | None) -> str:
        """Extract user_id from context, defaulting to 'anonymous'."""
        try:
            if invocation_context is not None:
                uid = getattr(invocation_context, "user_id", None)
                if uid:
                    return str(uid)
        except Exception:
            pass
        return "anonymous"

    def _is_allowed(self, user_id: str) -> bool:
        """Check + update the sliding window. Returns True if request is allowed."""
        now = time.time()
        window = self.user_windows[user_id]
        # Evict timestamps older than the window
        cutoff = now - self.window_seconds
        self.user_windows[user_id] = [t for t in window if t > cutoff]

        if len(self.user_windows[user_id]) >= self.max_requests:
            return False

        # Stamp the new request
        self.user_windows[user_id].append(now)
        return True

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Block request if user has exceeded their rate limit.

        Returns:
            None if allowed (pass through to next plugin/LLM).
            types.Content block message if rate limit exceeded.
        """
        self.total_count += 1
        user_id = self._get_user_id(invocation_context)

        if not self._is_allowed(user_id):
            self.blocked_count += 1
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=(
                            f"Rate limit exceeded. You have made {self.max_requests} requests "
                            f"in the last {self.window_seconds} seconds. "
                            "Please try again shortly."
                        )
                    )
                ],
            )
        return None
