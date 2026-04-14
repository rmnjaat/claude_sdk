"""Claude SDK — Python wrapper for the Claude CLI.

Usage::

    from claude_sdk import Claude, Conversation

    client = Claude(model="sonnet")
    response = client.ask("Explain Python decorators")
    print(response.result)
"""

__version__ = "0.1.0"

from .client import Claude
from .conversation import Conversation
from .exceptions import (
    ClaudeCLIError,
    ClaudeCLINotFound,
    ClaudeSafetyError,
    ClaudeSDKError,
    ClaudeSessionNotFound,
)
from .models import ClaudeResponse

__all__ = [
    "Claude",
    "Conversation",
    "ClaudeResponse",
    "ClaudeSDKError",
    "ClaudeCLINotFound",
    "ClaudeCLIError",
    "ClaudeSessionNotFound",
    "ClaudeSafetyError",
]
