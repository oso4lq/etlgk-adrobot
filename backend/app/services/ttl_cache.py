import threading
import time
from collections.abc import Callable


class TtlCache[T]:
    """A list loaded by a callable and kept for a while."""

    def __init__(
        self,
        load: Callable[[], list[T]],
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        # FastAPI runs sync endpoints in a thread pool, so the cache is shared between threads.
        self._lock = threading.Lock()
        self._items: list[T] = []
        self._loaded_at: float | None = None

    def get(self) -> tuple[list[T], bool]:
        """Returns the cached items and whether they were just loaded."""
        with self._lock:
            is_fresh = (
                self._loaded_at is not None and self._clock() - self._loaded_at < self._ttl_seconds
            )
            if is_fresh:
                return self._items, False
            return self._reload_locked(), True

    def reload(self) -> list[T]:
        with self._lock:
            return self._reload_locked()

    def _reload_locked(self) -> list[T]:
        # If loading fails, the exception leaves the old cache and timestamp untouched.
        self._items = self._load()
        self._loaded_at = self._clock()
        return self._items
