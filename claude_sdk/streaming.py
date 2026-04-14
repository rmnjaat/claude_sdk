"""Stream-json output parsing for Claude CLI."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

from .models import ClaudeResponse


def parse_stream_line(line: str) -> dict[str, Any] | None:
    """Parse a single line from stream-json output.

    Returns the parsed dict, or None if the line is empty or malformed.
    """
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


class StreamHandler:
    """Handles reading and dispatching stream-json events from a subprocess."""

    def __init__(
        self,
        process: subprocess.Popen,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._process = process
        self._on_event = on_event
        self._final_event: dict[str, Any] | None = None

    def process_stream(self) -> dict[str, Any] | None:
        """Read all events, dispatch via callback, return the final result event."""
        if self._process.stdout is None:
            return None

        for line in self._process.stdout:
            event = parse_stream_line(line)
            if event is None:
                continue
            if self._on_event:
                self._on_event(event)
            if event.get("type") == "result":
                self._final_event = event

        self._process.wait()
        return self._final_event

    def iter_events(self) -> Iterator[dict[str, Any]]:
        """Yield events one by one from the stream."""
        if self._process.stdout is None:
            return

        for line in self._process.stdout:
            event = parse_stream_line(line)
            if event is None:
                continue
            yield event
            if event.get("type") == "result":
                self._final_event = event

        self._process.wait()

    @property
    def final_event(self) -> dict[str, Any] | None:
        return self._final_event
