"""Core Claude SDK client."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

from .exceptions import (
    ClaudeCLIError,
    ClaudeCLINotFound,
    ClaudeSafetyError,
    ClaudeSessionNotFound,
)
from .models import ClaudeResponse
from .streaming import StreamHandler

# ---------------------------------------------------------------------------
# Safety preset defaults
# ---------------------------------------------------------------------------

SAFE_DEFAULTS: dict[str, Any] = {
    "permission_mode": "plan",
    "tools": ["Read", "Glob", "Grep"],
    "max_turns": 1,
    "max_budget_usd": 1.0,
}

CAREFUL_DEFAULTS: dict[str, Any] = {
    "permission_mode": "acceptEdits",
    "tools": ["Read", "Glob", "Grep", "Edit", "Write"],
    "disallowed_tools": ["Bash"],
    "max_turns": 3,
    "max_budget_usd": 5.0,
}

FULL_DEFAULTS: dict[str, Any] = {
    "permission_mode": "auto",
    "tools": None,  # None = all tools (CLI default)
    "max_turns": 10,
    "max_budget_usd": 20.0,
}

PRESETS: dict[str, dict[str, Any]] = {
    "safe": SAFE_DEFAULTS,
    "careful": CAREFUL_DEFAULTS,
    "full": FULL_DEFAULTS,
}

# Parameters that participate in safety presets.
_PRESET_KEYS = {"permission_mode", "tools", "disallowed_tools", "max_turns", "max_budget_usd"}


class Claude:
    """Python wrapper around the ``claude`` CLI.

    All parameters set here become defaults for every ``.ask()`` / ``.stream()``
    call.  Any parameter can also be overridden per-call via keyword arguments.
    """

    def __init__(
        self,
        *,
        # --- Model & Prompt ---
        model: str | None = None,
        system_prompt: str | None = None,
        append_system_prompt: str | None = None,
        effort: str | None = None,
        fallback_model: str | None = None,
        # --- Tools & Permissions ---
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        tools: list[str] | None = None,
        permission_mode: str | None = None,
        dangerously_skip_permissions: bool = False,
        allow_dangerously_skip_permissions: bool = False,
        disable_slash_commands: bool = False,
        # --- Safety ---
        safety: str = "safe",
        confirm_unsafe: bool = False,
        warn_on_permission_denial: bool = True,
        # --- Session ---
        no_session_persistence: bool = False,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        # --- Agents ---
        agent: str | None = None,
        agents: dict[str, Any] | None = None,
        # --- Budget ---
        max_budget_usd: float | None = None,
        max_turns: int | None = None,
        # --- Output ---
        output_format: str = "json",
        json_schema: dict[str, Any] | None = None,
        # --- MCP & Plugins ---
        mcp_config: str | list[str] | None = None,
        strict_mcp_config: bool = False,
        plugin_dirs: list[str] | None = None,
        # --- Input/Output ---
        input_format: str = "text",
        replay_user_messages: bool = False,
        # --- Settings ---
        settings: str | None = None,
        setting_sources: list[str] | None = None,
        # --- Remote Control ---
        remote_control_prefix: str | None = None,
        # --- Advanced ---
        bare: bool = False,
        betas: list[str] | None = None,
        verbose: bool = False,
        debug: bool | str = False,
        debug_file: str | None = None,
        files: list[str] | None = None,
        worktree: bool | str | None = None,
        brief: bool = False,
        exclude_dynamic_prompt: bool = False,
    ) -> None:
        # Store every parameter — order matches constructor signature.
        self.model = model
        self.system_prompt = system_prompt
        self.append_system_prompt = append_system_prompt
        self.effort = effort
        self.fallback_model = fallback_model
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.tools = tools
        self.permission_mode = permission_mode
        self.dangerously_skip_permissions = dangerously_skip_permissions
        self.allow_dangerously_skip_permissions = allow_dangerously_skip_permissions
        self.disable_slash_commands = disable_slash_commands
        self.safety = safety
        self.confirm_unsafe = confirm_unsafe
        self.warn_on_permission_denial = warn_on_permission_denial
        self.no_session_persistence = no_session_persistence
        self.cwd = cwd
        self.add_dirs = add_dirs
        self.agent = agent
        self.agents = agents
        self.max_budget_usd = max_budget_usd
        self.max_turns = max_turns
        self.output_format = output_format
        self.json_schema = json_schema
        self.mcp_config = mcp_config
        self.strict_mcp_config = strict_mcp_config
        self.plugin_dirs = plugin_dirs
        self.input_format = input_format
        self.replay_user_messages = replay_user_messages
        self.settings = settings
        self.setting_sources = setting_sources
        self.remote_control_prefix = remote_control_prefix
        self.bare = bare
        self.betas = betas
        self.verbose = verbose
        self.debug = debug
        self.debug_file = debug_file
        self.files = files
        self.worktree = worktree
        self.brief = brief
        self.exclude_dynamic_prompt = exclude_dynamic_prompt

        # Internal state
        self._last_session_id: str | None = None
        self._cli_path: str | None = None

        # Track which parameters the user explicitly set so presets don't
        # overwrite them.
        self._explicit: set[str] = set()
        _locals = {
            "model", "system_prompt", "append_system_prompt", "effort",
            "fallback_model", "allowed_tools", "disallowed_tools", "tools",
            "permission_mode", "max_budget_usd", "max_turns",
        }
        for key in _locals:
            if locals().get(key) is not None:
                self._explicit.add(key)
        # bools that default to False — only mark explicit if user set True
        if dangerously_skip_permissions:
            self._explicit.add("dangerously_skip_permissions")
        if disallowed_tools is not None:
            self._explicit.add("disallowed_tools")

        # Apply safety, validate, find CLI
        self._apply_safety_preset()
        self._validate_config()
        self._find_cli()

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _apply_safety_preset(self) -> None:
        """Fill in unset parameters from the chosen safety preset."""
        preset = PRESETS.get(self.safety)
        if preset is None:
            raise ValueError(
                f"Unknown safety preset {self.safety!r}. "
                f"Choose from: {', '.join(PRESETS)}"
            )
        for key, value in preset.items():
            if key not in self._explicit:
                setattr(self, key, value)

        if self.safety == "full":
            print(
                "WARNING: Full tool access enabled. Claude can run commands, "
                "modify files, and spawn subagents.",
                file=sys.stderr,
            )

    def _validate_config(self) -> None:
        """Raise on dangerous configurations unless the user opted in."""
        if self.permission_mode == "bypassPermissions" and not self.confirm_unsafe:
            raise ClaudeSafetyError(
                "permission_mode='bypassPermissions' skips ALL safety checks. "
                "Pass confirm_unsafe=True if you understand the risk.",
                unsafe_setting="bypassPermissions",
            )
        if self.dangerously_skip_permissions and not self.confirm_unsafe:
            raise ClaudeSafetyError(
                "dangerously_skip_permissions=True bypasses ALL permission "
                "checks. Pass confirm_unsafe=True if you understand the risk.",
                unsafe_setting="dangerously_skip_permissions",
            )
        if self.allow_dangerously_skip_permissions and not self.confirm_unsafe:
            raise ClaudeSafetyError(
                "allow_dangerously_skip_permissions=True enables the option to "
                "bypass all permission checks. Pass confirm_unsafe=True.",
                unsafe_setting="allow_dangerously_skip_permissions",
            )
        if (
            self.permission_mode == "auto"
            and self.tools is None
            and "tools" not in self._explicit
        ):
            print(
                "WARNING: auto permission mode with all tools enabled. "
                "Claude can run arbitrary commands.",
                file=sys.stderr,
            )
        if self.max_turns is not None and self.max_turns > 20:
            print(
                f"WARNING: max_turns={self.max_turns} — high turn counts "
                "can lead to runaway cost.",
                file=sys.stderr,
            )

    def _find_cli(self) -> str:
        """Locate the ``claude`` binary, raise if missing."""
        path = shutil.which("claude")
        if path is None:
            raise ClaudeCLINotFound()
        self._cli_path = path
        return path

    # ------------------------------------------------------------------
    # Command builder
    # ------------------------------------------------------------------

    def _build_command(self, prompt: str, **overrides: Any) -> list[str]:
        """Assemble the full CLI command list.

        Merge order (later wins):
          1. Safety preset defaults (already applied in __init__)
          2. Client-level settings (self.*)
          3. Per-call overrides (**overrides)
        """

        def get(key: str, default: Any = None) -> Any:
            """Resolve: per-call override > client attribute > default."""
            if key in overrides:
                return overrides.pop(key)
            return getattr(self, key, default)

        cmd: list[str] = [self._cli_path, "-p", prompt]  # type: ignore[list-item]

        # --- Output format (always set) ---
        fmt = get("output_format", "json")
        cmd += ["--output-format", fmt]

        # --- Model & Prompt ---
        if v := get("model"):
            cmd += ["--model", v]
        if v := get("system_prompt"):
            cmd += ["--system-prompt", v]
        if v := get("append_system_prompt"):
            cmd += ["--append-system-prompt", v]
        if v := get("effort"):
            cmd += ["--effort", v]
        if v := get("fallback_model"):
            cmd += ["--fallback-model", v]

        # --- Tools & Permissions ---
        tools_val = get("tools")
        if tools_val is not None:
            if isinstance(tools_val, list):
                cmd += ["--tools", ",".join(tools_val)] if tools_val else ["--tools", ""]
            else:
                cmd += ["--tools", str(tools_val)]
        if v := get("allowed_tools"):
            cmd += ["--allowedTools"] + list(v)
        if v := get("disallowed_tools"):
            cmd += ["--disallowedTools"] + list(v)
        if v := get("permission_mode"):
            cmd += ["--permission-mode", v]
        if get("dangerously_skip_permissions"):
            cmd += ["--dangerously-skip-permissions"]
        if get("allow_dangerously_skip_permissions"):
            cmd += ["--allow-dangerously-skip-permissions"]
        if get("disable_slash_commands"):
            cmd += ["--disable-slash-commands"]

        # --- Session (per-call only) ---
        resume_id = overrides.pop("resume", None)
        from_pr = overrides.pop("from_pr", None)
        continue_session = overrides.pop("continue_session", False)
        fork = overrides.pop("fork", False)
        session_id = overrides.pop("session_id", None)
        session_name = overrides.pop("session_name", None)

        if resume_id:
            cmd += ["--resume", str(resume_id)]
        elif from_pr:
            cmd += ["--from-pr", str(from_pr)]
        elif continue_session and self._last_session_id:
            cmd += ["--resume", self._last_session_id]

        if fork:
            cmd += ["--fork-session"]
        if session_id:
            cmd += ["--session-id", str(session_id)]
        if session_name:
            cmd += ["--name", str(session_name)]
        if get("no_session_persistence"):
            cmd += ["--no-session-persistence"]

        # --- Agents ---
        if v := get("agent"):
            cmd += ["--agent", v]
        if v := get("agents"):
            cmd += ["--agents", json.dumps(v)]

        # --- Budget ---
        if (v := get("max_budget_usd")) is not None:
            cmd += ["--max-budget-usd", str(v)]

        # --- Structured Output ---
        if v := get("json_schema"):
            cmd += ["--json-schema", json.dumps(v)]

        # --- MCP & Plugins ---
        mcp = get("mcp_config")
        if mcp:
            if isinstance(mcp, list):
                cmd += ["--mcp-config"] + mcp
            else:
                cmd += ["--mcp-config", mcp]
        if get("strict_mcp_config"):
            cmd += ["--strict-mcp-config"]
        if v := get("plugin_dirs"):
            for d in v:
                cmd += ["--plugin-dir", d]

        # --- Input/Output ---
        input_fmt = get("input_format", "text")
        if input_fmt != "text":
            cmd += ["--input-format", input_fmt]
        if get("replay_user_messages"):
            cmd += ["--replay-user-messages"]

        # --- Settings ---
        if v := get("settings"):
            cmd += ["--settings", v]
        if v := get("setting_sources"):
            cmd += ["--setting-sources", ",".join(v)]

        # --- Remote Control ---
        if v := get("remote_control_prefix"):
            cmd += ["--remote-control-session-name-prefix", v]

        # --- Directories ---
        if v := get("add_dirs"):
            for d in v:
                cmd += ["--add-dir", d]

        # --- Advanced flags ---
        if get("bare"):
            cmd += ["--bare"]
        if v := get("betas"):
            cmd += ["--betas"] + list(v)
        if get("verbose"):
            cmd += ["--verbose"]
        debug_val = get("debug")
        if debug_val:
            if isinstance(debug_val, str):
                cmd += ["--debug", debug_val]
            else:
                cmd += ["--debug"]
        if v := get("debug_file"):
            cmd += ["--debug-file", v]
        if v := get("files"):
            cmd += ["--file"] + list(v)
        worktree_val = get("worktree")
        if worktree_val:
            if isinstance(worktree_val, str):
                cmd += ["--worktree", worktree_val]
            else:
                cmd += ["--worktree"]
        if get("brief"):
            cmd += ["--brief"]
        if get("exclude_dynamic_prompt"):
            cmd += ["--exclude-dynamic-system-prompt-sections"]

        # --- Streaming-specific (per-call) ---
        if overrides.pop("include_hook_events", False):
            cmd += ["--include-hook-events"]
        if overrides.pop("include_partial_messages", False):
            cmd += ["--include-partial-messages"]

        return cmd

    # ------------------------------------------------------------------
    # Subprocess runner
    # ------------------------------------------------------------------

    def _run(self, command: list[str]) -> str:
        """Run the CLI subprocess and return stdout.

        Raises ClaudeCLIError / ClaudeSessionNotFound on failure.
        """
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=self.cwd or None,
        )

        if proc.returncode != 0:
            stderr_lower = proc.stderr.lower()
            if "session" in stderr_lower and "not found" in stderr_lower:
                raise ClaudeSessionNotFound(
                    message=proc.stderr.strip(),
                    session_id=self._last_session_id or "",
                )
            raise ClaudeCLIError(
                message=proc.stderr.strip() or f"CLI exited with code {proc.returncode}",
                exit_code=proc.returncode,
                stderr=proc.stderr,
                raw_output=proc.stdout,
            )

        return proc.stdout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ask(self, prompt: str, **overrides: Any) -> ClaudeResponse:
        """Send a prompt and return the parsed response.

        Per-call overrides (keyword arguments) take priority over client
        defaults. Session-related overrides:

        - ``continue_session=True`` — resume the last session on this client
        - ``resume="<session-id>"`` — resume a specific session
        - ``fork=True`` — branch the conversation (use with resume or continue)
        - ``session_id="<uuid>"`` — force a specific session UUID
        - ``session_name="..."`` — human-readable session label
        - ``from_pr="123"`` — resume a session linked to a PR

        Any client-level parameter can also be overridden here.
        """
        json_schema = overrides.get("json_schema", self.json_schema)
        command = self._build_command(prompt, **overrides)
        raw_output = self._run(command)

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise ClaudeCLIError(
                message=f"Failed to parse CLI JSON output: {exc}",
                raw_output=raw_output,
            ) from exc

        response = ClaudeResponse.from_json(data, json_schema_used=json_schema is not None)
        self._last_session_id = response.session_id

        if self.warn_on_permission_denial and response.permission_denials:
            for tool in response.permission_denials:
                print(
                    f"WARNING: Permission denied for tool: {tool}",
                    file=sys.stderr,
                )

        return response

    def stream(
        self,
        prompt: str,
        on_event: Callable[[dict[str, Any]], None],
        **overrides: Any,
    ) -> ClaudeResponse:
        """Stream a prompt, calling ``on_event`` for each event.

        Returns the final ``ClaudeResponse`` after the stream completes.
        Accepts the same per-call overrides as ``.ask()``, plus:

        - ``include_hook_events=True`` — include hook lifecycle events
        - ``include_partial_messages=True`` — include partial message chunks
        """
        json_schema = overrides.get("json_schema", self.json_schema)
        overrides["output_format"] = "stream-json"
        # stream-json requires --verbose in -p mode
        overrides.setdefault("verbose", True)
        command = self._build_command(prompt, **overrides)

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd or None,
        )

        handler = StreamHandler(proc, on_event=on_event)
        final_event = handler.process_stream()

        if final_event is None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise ClaudeCLIError(
                message=stderr.strip() or "Stream ended without a result event",
                exit_code=proc.returncode or 1,
                stderr=stderr,
            )

        response = ClaudeResponse.from_json(final_event, json_schema_used=json_schema is not None)
        self._last_session_id = response.session_id
        return response

    def stream_iter(self, prompt: str, **overrides: Any) -> Iterator[dict[str, Any]]:
        """Stream a prompt, yielding each event dict.

        The final event (``type: "result"``) is also yielded. After
        iteration, ``self._last_session_id`` is updated from the result.
        """
        json_schema = overrides.get("json_schema", self.json_schema)
        overrides["output_format"] = "stream-json"
        # stream-json requires --verbose in -p mode
        overrides.setdefault("verbose", True)
        command = self._build_command(prompt, **overrides)

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd or None,
        )

        handler = StreamHandler(proc)
        for event in handler.iter_events():
            yield event

        if handler.final_event is not None:
            response = ClaudeResponse.from_json(
                handler.final_event, json_schema_used=json_schema is not None
            )
            self._last_session_id = response.session_id
