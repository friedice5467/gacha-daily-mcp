from __future__ import annotations

import asyncio
from collections import deque

_buffer: deque[str] = deque(maxlen=500)
_subscribers: list[asyncio.Queue[str]] = []


def append(line: str) -> None:
    _buffer.append(line)
    for q in _subscribers:
        q.put_nowait(line)


def recent() -> list[str]:
    return list(_buffer)


def subscribe() -> asyncio.Queue[str]:
    q: asyncio.Queue[str] = asyncio.Queue()
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue[str]) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
