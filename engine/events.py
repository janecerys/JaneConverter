"""Small bounded event queues used at the GUI/backend boundary.

Progress is a state, not a durable log.  Keeping only the newest progress
callback prevents a fast downloader or FFmpeg process from starving Tk's
event loop while terminal callbacks remain durable.
"""

from collections import deque
import threading
import time
from typing import Callable, Deque, List, Optional, Tuple


class CoalescingCallbackQueue:
    """Thread-safe callback queue with latest-value coalescing and backpressure."""

    def __init__(self, max_callbacks: int = 256):
        self.max_callbacks = max(1, int(max_callbacks))
        self._items: Deque[Tuple[str, object]] = deque()
        self._latest = {}
        self._pending_keys = set()
        self._lock = threading.Lock()
        self.dropped = 0

    def put(self, callback: Callable[[], None], key: Optional[str] = None,
            priority: bool = False) -> bool:
        """Queue a callback; keyed callbacks replace older callbacks with that key."""
        with self._lock:
            if key is not None:
                self._latest[key] = callback
                if key in self._pending_keys:
                    return True
                self._pending_keys.add(key)
                item = ("key", key)
            else:
                if len(self._items) >= self.max_callbacks and not priority:
                    self.dropped += 1
                    return False
                item = ("callback", callback)

            if priority:
                self._items.appendleft(item)
            else:
                self._items.append(item)
            return True

    def drain(self, max_items: int = 64, time_budget_ms: float = 12.0) -> List[Callable[[], None]]:
        """Return a bounded batch for execution on the UI thread."""
        deadline = time.monotonic() + max(0.0, time_budget_ms) / 1000.0
        callbacks = []
        while len(callbacks) < max(1, max_items) and time.monotonic() <= deadline:
            with self._lock:
                if not self._items:
                    break
                kind, value = self._items.popleft()
                if kind == "key":
                    self._pending_keys.discard(value)
                    callback = self._latest.pop(value, None)
                else:
                    callback = value
            if callback is not None:
                callbacks.append(callback)
        return callbacks

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)


class BoundedLogQueue:
    """Thread-safe bounded text queue that drops noisy fragments under pressure."""

    def __init__(self, max_items: int = 4000):
        self.max_items = max(1, int(max_items))
        self._items: Deque[str] = deque()
        self._lock = threading.Lock()
        self.dropped = 0

    def put(self, text: str) -> bool:
        if not text:
            return True
        with self._lock:
            if len(self._items) >= self.max_items:
                self.dropped += 1
                return False
            self._items.append(str(text))
            return True

    def get_batch(self, max_items: int = 250) -> List[str]:
        with self._lock:
            batch = []
            while self._items and len(batch) < max(1, max_items):
                batch.append(self._items.popleft())
            return batch

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)
