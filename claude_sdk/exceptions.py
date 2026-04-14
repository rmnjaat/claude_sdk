"""Claude SDK exceptions."""


class ClaudeSDKError(Exception):
    """Base exception for all Claude SDK errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ClaudeCLINotFound(ClaudeSDKError):
    """Raised when the claude CLI binary is not found in PATH."""

    def __init__(
        self,
        message: str = "claude CLI not found in PATH. Install: npm install -g @anthropic-ai/claude-code",
    ) -> None:
        super().__init__(message)


class ClaudeCLIError(ClaudeSDKError):
    """Raised when the CLI process exits with an error."""

    def __init__(
        self,
        message: str,
        exit_code: int = 1,
        stderr: str = "",
        raw_output: str | None = None,
    ) -> None:
        self.exit_code = exit_code
        self.stderr = stderr
        self.raw_output = raw_output
        super().__init__(message)


class ClaudeSessionNotFound(ClaudeCLIError):
    """Raised when a session ID cannot be found for resume/continue."""

    def __init__(self, message: str, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(message)


class ClaudeSafetyError(ClaudeSDKError):
    """Raised when an unsafe configuration is used without confirm_unsafe=True."""

    def __init__(self, message: str, unsafe_setting: str) -> None:
        self.unsafe_setting = unsafe_setting
        super().__init__(message)
