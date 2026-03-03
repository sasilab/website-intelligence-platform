"""
Rate limiter for controlling crawler request frequency
"""

import asyncio
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for async operations"""

    def __init__(self, requests_per_window: int = 10, window_seconds: int = 60):
        """
        Initialize rate limiter

        Args:
            requests_per_window: Maximum number of requests allowed in the time window
            window_seconds: Time window in seconds
        """
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.request_times = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """
        Acquire permission to make a request.
        Will wait if rate limit is exceeded.
        """
        async with self._lock:
            now = time.time()

            # Remove expired request times
            cutoff = now - self.window_seconds
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()

            # Check if we need to wait
            if len(self.request_times) >= self.requests_per_window:
                # Calculate wait time
                oldest_request = self.request_times[0]
                wait_time = (oldest_request + self.window_seconds) - now

                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Recursive call after waiting
                    return await self.acquire()

            # Record this request
            self.request_times.append(now)

    def reset(self):
        """Reset the rate limiter"""
        self.request_times.clear()

    @property
    def available_requests(self) -> int:
        """Get the number of available requests in the current window"""
        now = time.time()
        cutoff = now - self.window_seconds

        # Count non-expired requests
        valid_requests = sum(1 for t in self.request_times if t >= cutoff)
        return max(0, self.requests_per_window - valid_requests)


class AdaptiveRateLimiter(RateLimiter):
    """
    Adaptive rate limiter that adjusts based on server response times
    """

    def __init__(
        self,
        initial_requests: int = 10,
        window_seconds: int = 60,
        min_requests: int = 1,
        max_requests: int = 100
    ):
        super().__init__(initial_requests, window_seconds)
        self.min_requests = min_requests
        self.max_requests = max_requests
        self.response_times = deque(maxlen=10)
        self.error_count = 0

    async def acquire(self, response_time: Optional[float] = None):
        """
        Acquire with optional response time feedback

        Args:
            response_time: Previous request's response time in seconds
        """
        if response_time:
            self.response_times.append(response_time)
            self._adjust_rate()

        await super().acquire()

    def report_error(self):
        """Report an error to reduce rate"""
        self.error_count += 1
        if self.error_count >= 3:
            # Reduce rate on multiple errors
            self.requests_per_window = max(
                self.min_requests,
                self.requests_per_window // 2
            )
            self.error_count = 0

    def _adjust_rate(self):
        """Adjust rate based on response times"""
        if len(self.response_times) < 5:
            return

        avg_response_time = sum(self.response_times) / len(self.response_times)

        # If responses are fast, increase rate
        if avg_response_time < 0.5:
            self.requests_per_window = min(
                self.max_requests,
                int(self.requests_per_window * 1.2)
            )
        # If responses are slow, decrease rate
        elif avg_response_time > 2.0:
            self.requests_per_window = max(
                self.min_requests,
                int(self.requests_per_window * 0.8)
            )


class DomainRateLimiter:
    """
    Rate limiter that manages limits per domain
    """

    def __init__(self, default_requests: int = 10, window_seconds: int = 60):
        self.default_requests = default_requests
        self.window_seconds = window_seconds
        self.limiters = {}

    async def acquire(self, domain: str):
        """Acquire permission for a specific domain"""
        if domain not in self.limiters:
            self.limiters[domain] = RateLimiter(
                self.default_requests,
                self.window_seconds
            )

        await self.limiters[domain].acquire()

    def set_domain_limit(self, domain: str, requests: int):
        """Set a specific limit for a domain"""
        self.limiters[domain] = RateLimiter(requests, self.window_seconds)

    def reset_domain(self, domain: str):
        """Reset limits for a specific domain"""
        if domain in self.limiters:
            self.limiters[domain].reset()

    def reset_all(self):
        """Reset all domain limits"""
        self.limiters.clear()