"""Multi-turn conversation helper with automatic session tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import ClaudeResponse

if TYPE_CHECKING:
    from .client import Claude


class Conversation:
    """Stateful multi-turn conversation wrapper.

    Every ``.say()`` call automatically continues the same session.
    Tracks cumulative cost, turn count, and full history.

    Usage::

        from claude_sdk import Claude, Conversation

        client = Claude(model="sonnet", safety="careful")
        conv = Conversation(client, system_prompt="You are a tutor")

        r1 = conv.say("What is recursion?")
        r2 = conv.say("Show me an example")   # auto-continues
        r3 = conv.say("Explain the base case") # still same session

        print(conv.total_cost_usd)  # cumulative
        print(conv.turn_count)      # 3

        # Branch the conversation
        conv2 = conv.fork()
        r4 = conv2.say("Try a tree analogy instead")
        # conv2 is a new session; conv is untouched
    """

    def __init__(
        self,
        client: Claude,
        system_prompt: str | None = None,
    ) -> None:
        self._client = client
        self._system_prompt = system_prompt
        self._session_id: str | None = None
        self._total_cost_usd: float = 0.0
        self._turn_count: int = 0
        self._history: list[tuple[str, ClaudeResponse]] = []
        self._fork_on_next: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def say(self, prompt: str, **overrides: Any) -> ClaudeResponse:
        """Send a message in this conversation.

        On the first call a new session is created. All subsequent calls
        automatically resume the same session via ``--resume``.

        Args:
            prompt: The user message.
            **overrides: Per-call overrides forwarded to ``client.ask()``.

        Returns:
            The parsed ``ClaudeResponse``.
        """
        kwargs: dict[str, Any] = {**overrides}

        # System prompt only on the first turn (session remembers it after).
        if self._system_prompt and self._turn_count == 0:
            kwargs.setdefault("system_prompt", self._system_prompt)

        # Resume the existing session after the first turn.
        if self._session_id is not None:
            kwargs["resume"] = self._session_id

        # If this conversation was created by .fork(), add --fork-session once.
        if self._fork_on_next:
            kwargs["fork"] = True
            self._fork_on_next = False

        response = self._client.ask(prompt, **kwargs)

        # Update internal state.
        self._session_id = response.session_id
        self._total_cost_usd += response.cost_usd
        self._turn_count += 1
        self._history.append((prompt, response))

        return response

    def fork(self) -> Conversation:
        """Create a branched copy of this conversation.

        The first ``.say()`` on the returned ``Conversation`` will use
        ``--fork-session`` so that a new session ID is created while
        carrying the full history of the original. The original
        conversation is not modified.
        """
        new_conv = Conversation(self._client, self._system_prompt)
        new_conv._session_id = self._session_id
        new_conv._fork_on_next = True
        new_conv._total_cost_usd = self._total_cost_usd
        new_conv._turn_count = self._turn_count
        new_conv._history = list(self._history)  # shallow copy
        return new_conv

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str | None:
        """The current session UUID, or ``None`` if no call has been made."""
        return self._session_id

    @property
    def total_cost_usd(self) -> float:
        """Cumulative cost across all turns in this conversation."""
        return self._total_cost_usd

    @property
    def turn_count(self) -> int:
        """Number of ``.say()`` calls made so far."""
        return self._turn_count

    @property
    def history(self) -> list[tuple[str, ClaudeResponse]]:
        """List of ``(prompt, response)`` tuples for every turn."""
        return list(self._history)  # defensive copy
