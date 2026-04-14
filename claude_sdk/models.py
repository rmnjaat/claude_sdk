"""Claude SDK response model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClaudeResponse:
    """Parsed response from a Claude CLI call.

    Attributes:
        result: The text response from Claude.
        is_error: Whether the CLI reported an error.
        cost_usd: Total cost of the call (including subagents).
        duration_ms: Wall-clock time in milliseconds.
        duration_api_ms: API-only time in milliseconds.
        num_turns: Number of conversation turns.
        session_id: Session UUID for resuming later.
        stop_reason: Why the response ended ("end_turn", "max_turns", etc.).
        usage: Raw token usage dict from the CLI.
        model_usage: Per-model breakdown (tokens, cost, context window).
        permission_denials: Tools that were blocked by permission checks.
        parsed: Structured output dict if json_schema was used, else None.
        raw: The full raw JSON dict from the CLI.
    """

    result: str = ""
    is_error: bool = False
    cost_usd: float = 0.0
    duration_ms: int = 0
    duration_api_ms: int = 0
    num_turns: int = 0
    session_id: str = ""
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    model_usage: dict[str, Any] = field(default_factory=dict)
    permission_denials: list[str] = field(default_factory=list)
    parsed: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any], json_schema_used: bool = False) -> ClaudeResponse:
        """Create a ClaudeResponse from the raw CLI JSON output.

        Args:
            data: The parsed JSON dict from CLI stdout.
            json_schema_used: Whether a json_schema was provided in the request,
                so we should attempt to parse the result as JSON.
        """
        result_text = data.get("result", "")

        # The CLI puts structured output in "structured_output" when
        # --json-schema is used.  Fall back to parsing result as JSON.
        parsed = None
        if json_schema_used:
            parsed = data.get("structured_output")
            if parsed is None and result_text:
                try:
                    parsed = json.loads(result_text)
                except (json.JSONDecodeError, TypeError):
                    parsed = None

        return cls(
            result=result_text,
            is_error=data.get("is_error", False),
            cost_usd=data.get("total_cost_usd", 0.0),
            duration_ms=data.get("duration_ms", 0),
            duration_api_ms=data.get("duration_api_ms", 0),
            num_turns=data.get("num_turns", 0),
            session_id=data.get("session_id", ""),
            stop_reason=data.get("stop_reason", ""),
            usage=data.get("usage", {}),
            model_usage=data.get("modelUsage", {}),
            permission_denials=data.get("permission_denials", []),
            parsed=parsed,
            raw=data,
        )
