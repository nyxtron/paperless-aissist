"""In-memory log broadcast system for SSE streaming and log history.

Provides a circular buffer of recent log lines, pub/sub for SSE clients, and a
logging handler that feeds directly into the broadcast pipeline.
"""

import asyncio
import logging
from collections import deque

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_KNOWN_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "app.services.processor",
    "app.services.llm_handler",
    "app.services.paperless",
    "app.services.vision",
    "app.services.scheduler",
    "app.routers.config",
)


def apply_log_level(level_str: str) -> None:
    """Set the global and per-module log level from a string (DEBUG/INFO/WARNING/ERROR)."""
    level = _LEVEL_MAP.get(level_str.upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    for name in _KNOWN_LOGGERS:
        logging.getLogger(name).setLevel(level)


_buffer: deque[str] = deque(maxlen=500)
_subscribers: list[asyncio.Queue] = []


def get_history() -> list[str]:
    """Return the current circular buffer contents as a list of log lines."""
    return list(_buffer)


async def _broadcast(line: str) -> None:
    _buffer.append(line)
    dead_queues = []
    for i, q in enumerate(_subscribers):
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            dead_queues.append(i)
    for i in reversed(dead_queues):
        try:
            _subscribers.pop(i)
        except IndexError:
            pass


async def subscribe() -> asyncio.Queue:
    """Subscribe to new log lines; returns a queue with a 500-line buffer."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """Remove a subscriber queue from the broadcast list."""
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


class BroadcastHandler(logging.Handler):
    """Logging handler that feeds into the in-memory broadcast system."""

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_broadcast(line))
        except RuntimeError:
            _buffer.append(line)  # no event loop (startup); just buffer
