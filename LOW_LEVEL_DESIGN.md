# Claude SDK - Low-Level Design

Every class, every method, every field — the implementation blueprint.

---

## File 1: `exceptions.py`

```
exceptions.py
│
├── class ClaudeSDKError(Exception)
│       Base exception. All SDK errors inherit from this.
│       Fields: message (str)
│
├── class ClaudeCLINotFound(ClaudeSDKError)
│       Raised when `claude` binary is not in PATH.
│       Triggered by: shutil.which("claude") returns None
│
├── class ClaudeCLIError(ClaudeSDKError)
│       Raised when the CLI process exits with non-zero or returns an error JSON.
│       Fields: message (str), exit_code (int), stderr (str), raw_output (str | None)
│
├── class ClaudeSessionNotFound(ClaudeSDKError)
│       Raised when --resume or --continue references a session that doesn't exist.
│       Fields: message (str), session_id (str)
│
└── class ClaudeSafetyError(ClaudeSDKError)
        Raised when unsafe config is used without confirm_unsafe=True.
        Fields: message (str), unsafe_setting (str)
```

### Inheritance tree:

```
Exception
  └── ClaudeSDKError
        ├── ClaudeCLINotFound
        ├── ClaudeCLIError
        │     └── ClaudeSessionNotFound
        └── ClaudeSafetyError
```

`ClaudeSessionNotFound` inherits from `ClaudeCLIError` because it's a specific
type of CLI error (the CLI returned an error about the session).

---

## File 2: `models.py`

```
models.py
│
└── @dataclass
    class ClaudeResponse
    │
    ├── Fields:
    │   ├── result: str                    # Main text output
    │   ├── is_error: bool                 # True if CLI reported error
    │   ├── cost_usd: float                # Total cost (including subagents)
    │   ├── duration_ms: int               # Wall clock time
    │   ├── duration_api_ms: int           # API-only time
    │   ├── num_turns: int                 # Total turns (including subagent turns)
    │   ├── session_id: str                # Session UUID for resuming
    │   ├── stop_reason: str               # "end_turn", "max_turns", etc.
    │   ├── usage: dict                    # Raw token usage from CLI
    │   ├── model_usage: dict              # Per-model breakdown
    │   ├── permission_denials: list[str]  # Tools that were denied
    │   ├── parsed: dict | None            # Structured output (if json_schema used)
    │   └── raw: dict                      # Full raw JSON from CLI
    │
    └── @classmethod
        from_json(cls, data: dict) -> ClaudeResponse
        │
        ├── Maps CLI JSON keys to dataclass fields:
        │
        │   CLI JSON key           →  Dataclass field
        │   ─────────────             ───────────────
        │   "result"               →  result
        │   "is_error"             →  is_error
        │   "total_cost_usd"       →  cost_usd
        │   "duration_ms"          →  duration_ms
        │   "duration_api_ms"      →  duration_api_ms
        │   "num_turns"            →  num_turns
        │   "session_id"           →  session_id
        │   "stop_reason"          →  stop_reason
        │   "usage"                →  usage
        │   "modelUsage"           →  model_usage
        │   "permission_denials"   →  permission_denials
        │   (parsed from result)   →  parsed
        │   (entire dict)          →  raw
        │
        ├── Structured output handling:
        │   if json_schema was used:
        │     try: parsed = json.loads(result)
        │     except: parsed = None
        │
        └── Safe defaults:
            missing keys get sensible defaults (0, "", [], None)
```

### Actual CLI JSON structure (from real output):

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 2345,
  "duration_api_ms": 2321,
  "num_turns": 1,
  "result": "Hello! How can I help you today?",
  "stop_reason": "end_turn",
  "session_id": "5b81a84a-c6d3-4110-bb28-76c9adc4e7a3",
  "total_cost_usd": 0.0354345,
  "usage": {
    "input_tokens": 3,
    "cache_creation_input_tokens": 4646,
    "cache_read_input_tokens": 12164,
    "output_tokens": 12,
    "server_tool_use": { "web_search_requests": 0, "web_fetch_requests": 0 },
    "service_tier": "standard"
  },
  "modelUsage": {
    "claude-opus-4-6[1m]": {
      "inputTokens": 3,
      "outputTokens": 12,
      "cacheReadInputTokens": 12164,
      "cacheCreationInputTokens": 4646,
      "webSearchRequests": 0,
      "costUSD": 0.0354345,
      "contextWindow": 1000000,
      "maxOutputTokens": 64000
    }
  },
  "permission_denials": [],
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "uuid": "dddffe22-f7b5-4ef7-8d12-e254ad0c3e55"
}
```

---

## File 3: `client.py`

The main file. This is the most complex module.

```
client.py
│
├── CONSTANTS
│   ├── SAFE_DEFAULTS = {
│   │     "permission_mode": "plan",
│   │     "tools": ["Read", "Glob", "Grep"],
│   │     "max_turns": 1,
│   │     "max_budget_usd": 1.0,
│   │   }
│   ├── CAREFUL_DEFAULTS = {
│   │     "permission_mode": "acceptEdits",
│   │     "tools": ["Read", "Glob", "Grep", "Edit", "Write"],
│   │     "disallowed_tools": ["Bash"],
│   │     "max_turns": 3,
│   │     "max_budget_usd": 5.0,
│   │   }
│   └── FULL_DEFAULTS = {
│         "permission_mode": "auto",
│         "tools": None,  (None = all tools, CLI default)
│         "max_turns": 10,
│         "max_budget_usd": 20.0,
│       }
│
└── class Claude
    │
    ├── __init__(self, **kwargs)
    │   │
    │   │  1. Store ALL parameters as instance attributes
    │   │  2. Set _last_session_id = None
    │   │  3. Call _apply_safety_preset()
    │   │  4. Call _validate_config()
    │   │  5. Call _find_cli()
    │   │
    │   └── Parameter storage order:
    │       self.model = model
    │       self.system_prompt = system_prompt
    │       self.append_system_prompt = append_system_prompt
    │       self.effort = effort
    │       self.fallback_model = fallback_model
    │       self.allowed_tools = allowed_tools
    │       self.disallowed_tools = disallowed_tools
    │       self.tools = tools
    │       self.permission_mode = permission_mode
    │       self.dangerously_skip_permissions = dangerously_skip_permissions
    │       self.allow_dangerously_skip_permissions = allow_dangerously_skip_permissions
    │       self.disable_slash_commands = disable_slash_commands
    │       self.safety = safety
    │       self.confirm_unsafe = confirm_unsafe
    │       self.warn_on_permission_denial = warn_on_permission_denial
    │       self.no_session_persistence = no_session_persistence
    │       self.cwd = cwd
    │       self.add_dirs = add_dirs
    │       self.agent = agent
    │       self.agents = agents
    │       self.max_budget_usd = max_budget_usd
    │       self.max_turns = max_turns
    │       self.output_format = output_format
    │       self.json_schema = json_schema
    │       self.mcp_config = mcp_config
    │       self.strict_mcp_config = strict_mcp_config
    │       self.plugin_dirs = plugin_dirs
    │       self.input_format = input_format
    │       self.replay_user_messages = replay_user_messages
    │       self.settings = settings
    │       self.setting_sources = setting_sources
    │       self.remote_control_prefix = remote_control_prefix
    │       self.bare = bare
    │       self.betas = betas
    │       self.verbose = verbose
    │       self.debug = debug
    │       self.debug_file = debug_file
    │       self.files = files
    │       self.worktree = worktree
    │       self.brief = brief
    │       self.exclude_dynamic_prompt = exclude_dynamic_prompt
    │       self._last_session_id = None
    │       self._cli_path = None  (set by _find_cli)
    │
    ├── _apply_safety_preset(self)
    │   │
    │   │  Only sets values for parameters the user did NOT explicitly provide.
    │   │  Explicit params always win over preset defaults.
    │   │
    │   │  Logic:
    │   │    preset = SAFE_DEFAULTS | CAREFUL_DEFAULTS | FULL_DEFAULTS
    │   │    for key, value in preset.items():
    │   │      if getattr(self, key) is None:  # user didn't set it
    │   │        setattr(self, key, value)
    │   │
    │   │  For "full" preset:
    │   │    print("WARNING: Full tool access enabled...", file=sys.stderr)
    │   │
    │   └── Returns: None (mutates self)
    │
    ├── _validate_config(self)
    │   │
    │   │  Checks for dangerous configurations:
    │   │
    │   │  1. if permission_mode == "bypassPermissions" and not confirm_unsafe:
    │   │       raise ClaudeSafetyError("bypassPermissions requires confirm_unsafe=True")
    │   │
    │   │  2. if dangerously_skip_permissions and not confirm_unsafe:
    │   │       raise ClaudeSafetyError("dangerously_skip_permissions requires confirm_unsafe=True")
    │   │
    │   │  3. if allow_dangerously_skip_permissions and not confirm_unsafe:
    │   │       raise ClaudeSafetyError("allow_dangerously_skip_permissions requires confirm_unsafe=True")
    │   │
    │   │  4. if permission_mode == "auto" and tools is None:
    │   │       print("WARNING: auto mode with all tools...", file=sys.stderr)
    │   │
    │   │  5. if max_turns and max_turns > 20:
    │   │       print("WARNING: max_turns > 20...", file=sys.stderr)
    │   │
    │   └── Returns: None (raises on failure)
    │
    ├── _find_cli(self) -> str
    │   │
    │   │  path = shutil.which("claude")
    │   │  if path is None:
    │   │    raise ClaudeCLINotFound(
    │   │      "claude CLI not found in PATH. Install: npm install -g @anthropic-ai/claude-code"
    │   │    )
    │   │  self._cli_path = path
    │   │
    │   └── Returns: path (str)
    │
    ├── _build_command(self, prompt: str, **overrides) -> list[str]
    │   │
    │   │  Builds the full CLI command as a list of strings.
    │   │
    │   │  Merge order (later wins):
    │   │    1. Safety preset defaults (already applied in __init__)
    │   │    2. Client-level settings (self.*)
    │   │    3. Per-call overrides (**overrides)
    │   │
    │   │  Base command:
    │   │    cmd = [self._cli_path, "-p", prompt, "--output-format", output_format]
    │   │
    │   │  Then append flags conditionally:
    │   │
    │   │    PARAMETER                    → FLAG APPENDED
    │   │    ─────────                       ──────────────
    │   │    model                        → ["--model", model]
    │   │    system_prompt                → ["--system-prompt", system_prompt]
    │   │    append_system_prompt         → ["--append-system-prompt", append_system_prompt]
    │   │    effort                       → ["--effort", effort]
    │   │    fallback_model               → ["--fallback-model", fallback_model]
    │   │    allowed_tools                → ["--allowedTools"] + tools
    │   │    disallowed_tools             → ["--disallowedTools"] + tools
    │   │    tools                        → ["--tools"] + tools (comma-separated)
    │   │    permission_mode              → ["--permission-mode", mode]
    │   │    dangerously_skip_permissions → ["--dangerously-skip-permissions"]
    │   │    allow_dangerously_skip_perms → ["--allow-dangerously-skip-permissions"]
    │   │    disable_slash_commands       → ["--disable-slash-commands"]
    │   │    no_session_persistence       → ["--no-session-persistence"]
    │   │    add_dirs                     → ["--add-dir"] + dirs (one per dir)
    │   │    agent                        → ["--agent", agent]
    │   │    agents                       → ["--agents", json.dumps(agents)]
    │   │    max_budget_usd               → ["--max-budget-usd", str(budget)]
    │   │    json_schema                  → ["--json-schema", json.dumps(schema)]
    │   │    mcp_config                   → ["--mcp-config"] + configs
    │   │    strict_mcp_config            → ["--strict-mcp-config"]
    │   │    plugin_dirs                  → ["--plugin-dir", dir] per dir
    │   │    input_format (if not "text") → ["--input-format", format]
    │   │    replay_user_messages         → ["--replay-user-messages"]
    │   │    settings                     → ["--settings", settings]
    │   │    setting_sources              → ["--setting-sources", ",".join(sources)]
    │   │    remote_control_prefix        → ["--remote-control-session-name-prefix", prefix]
    │   │    bare                         → ["--bare"]
    │   │    betas                        → ["--betas"] + betas
    │   │    verbose                      → ["--verbose"]
    │   │    debug                        → ["--debug"] or ["--debug", filter_str]
    │   │    debug_file                   → ["--debug-file", path]
    │   │    files                        → ["--file"] + file_specs
    │   │    worktree                     → ["--worktree"] or ["--worktree", name]
    │   │    brief                        → ["--brief"]
    │   │    exclude_dynamic_prompt       → ["--exclude-dynamic-system-prompt-sections"]
    │   │
    │   │  Session resolution (from overrides):
    │   │    resume         → ["--resume", session_id]
    │   │    from_pr        → ["--from-pr", pr_ref]
    │   │    continue_session=True
    │   │      + _last_session_id → ["--resume", _last_session_id]
    │   │    session_id     → ["--session-id", uuid]
    │   │    session_name   → ["--name", name]
    │   │    fork=True      → ["--fork-session"]
    │   │
    │   │  Streaming overrides:
    │   │    include_hook_events    → ["--include-hook-events"]
    │   │    include_partial_msgs   → ["--include-partial-messages"]
    │   │
    │   └── Returns: list[str]
    │
    ├── _run(self, command: list[str]) -> str
    │   │
    │   │  proc = subprocess.run(
    │   │    command,
    │   │    capture_output=True,
    │   │    text=True,
    │   │    cwd=self.cwd or None,
    │   │  )
    │   │
    │   │  if proc.returncode != 0:
    │   │    # Check if it's a session-not-found error
    │   │    if "session" in proc.stderr.lower() and "not found" in proc.stderr.lower():
    │   │      raise ClaudeSessionNotFound(...)
    │   │    raise ClaudeCLIError(
    │   │      message=proc.stderr,
    │   │      exit_code=proc.returncode,
    │   │      stderr=proc.stderr,
    │   │      raw_output=proc.stdout
    │   │    )
    │   │
    │   └── Returns: proc.stdout (str)
    │
    ├── ask(self, prompt: str, **overrides) -> ClaudeResponse
    │   │
    │   │  1. command = self._build_command(prompt, **overrides)
    │   │  2. raw_output = self._run(command)
    │   │  3. data = json.loads(raw_output)
    │   │  4. response = ClaudeResponse.from_json(data)
    │   │  5. self._last_session_id = response.session_id
    │   │  6. if self.warn_on_permission_denial and response.permission_denials:
    │   │       for tool in response.permission_denials:
    │   │         print(f"WARNING: Permission denied for tool: {tool}", file=sys.stderr)
    │   │  7. return response
    │   │
    │   └── Per-call override params:
    │       continue_session: bool = False
    │       resume: str | None = None
    │       fork: bool = False
    │       session_id: str | None = None
    │       session_name: str | None = None
    │       from_pr: str | None = None
    │       json_schema: dict | None = None  (override client-level)
    │       agent: str | None = None         (override client-level)
    │       agents: dict | None = None       (override client-level)
    │       files: list[str] | None = None   (override client-level)
    │       + any other client param can be overridden per-call
    │
    ├── stream(self, prompt: str, on_event: Callable, **overrides) -> ClaudeResponse
    │   │
    │   │  1. Force output_format = "stream-json" in overrides
    │   │  2. command = self._build_command(prompt, **overrides)
    │   │  3. proc = subprocess.Popen(
    │   │       command,
    │   │       stdout=subprocess.PIPE,
    │   │       stderr=subprocess.PIPE,
    │   │       text=True,
    │   │       cwd=self.cwd or None,
    │   │     )
    │   │  4. final_event = None
    │   │  5. for line in proc.stdout:
    │   │       line = line.strip()
    │   │       if not line: continue
    │   │       event = json.loads(line)
    │   │       on_event(event)
    │   │       if event.get("type") == "result":
    │   │         final_event = event
    │   │  6. proc.wait()
    │   │  7. if proc.returncode != 0 and final_event is None:
    │   │       raise ClaudeCLIError(...)
    │   │  8. response = ClaudeResponse.from_json(final_event)
    │   │  9. self._last_session_id = response.session_id
    │   │  10. return response
    │   │
    │   └── Additional per-call params:
    │       include_hook_events: bool = False
    │       include_partial_messages: bool = False
    │
    └── stream_iter(self, prompt: str, **overrides) -> Iterator[dict]
        │
        │  Generator version of stream(). No callback needed.
        │
        │  1. Force output_format = "stream-json" in overrides
        │  2. command = self._build_command(prompt, **overrides)
        │  3. proc = subprocess.Popen(...)
        │  4. for line in proc.stdout:
        │       line = line.strip()
        │       if not line: continue
        │       event = json.loads(line)
        │       yield event
        │       if event.get("type") == "result":
        │         response = ClaudeResponse.from_json(event)
        │         self._last_session_id = response.session_id
        │  5. proc.wait()
        │
        └── Returns: Iterator[dict]
            (caller gets raw event dicts, final one is the result)
```

---

## File 4: `conversation.py`

```
conversation.py
│
└── class Conversation
    │
    ├── __init__(self, client: Claude, system_prompt: str | None = None)
    │   │
    │   │  self._client = client
    │   │  self._system_prompt = system_prompt
    │   │  self._session_id: str | None = None
    │   │  self._total_cost_usd: float = 0.0
    │   │  self._turn_count: int = 0
    │   │  self._history: list[tuple[str, ClaudeResponse]] = []
    │   │
    │   └── Does NOT make any API calls. Just stores config.
    │
    ├── say(self, prompt: str, **overrides) -> ClaudeResponse
    │   │
    │   │  Build call kwargs:
    │   │    kwargs = {**overrides}
    │   │    if self._system_prompt and self._turn_count == 0:
    │   │      kwargs["system_prompt"] = self._system_prompt
    │   │    if self._session_id is not None:
    │   │      kwargs["resume"] = self._session_id
    │   │
    │   │  response = self._client.ask(prompt, **kwargs)
    │   │
    │   │  Update state:
    │   │    self._session_id = response.session_id
    │   │    self._total_cost_usd += response.cost_usd
    │   │    self._turn_count += 1
    │   │    self._history.append((prompt, response))
    │   │
    │   │  return response
    │   │
    │   └── Note: system_prompt only sent on first turn.
    │       After that, the session already has it in context.
    │
    ├── fork(self) -> Conversation
    │   │
    │   │  Creates a new Conversation that will branch from the current session.
    │   │
    │   │  new_conv = Conversation(self._client, self._system_prompt)
    │   │  new_conv._session_id = self._session_id  (same session to resume from)
    │   │  new_conv._fork_on_next = True  (internal flag)
    │   │  new_conv._total_cost_usd = self._total_cost_usd  (copy running total)
    │   │  new_conv._turn_count = self._turn_count  (copy turn count)
    │   │  new_conv._history = list(self._history)  (copy history)
    │   │
    │   │  The FIRST .say() on the forked conv will include fork=True.
    │   │  After that, fork=True is removed (it only applies once).
    │   │
    │   └── Returns: new Conversation instance
    │
    ├── @property session_id(self) -> str | None
    │     return self._session_id
    │
    ├── @property total_cost_usd(self) -> float
    │     return self._total_cost_usd
    │
    ├── @property turn_count(self) -> int
    │     return self._turn_count
    │
    └── @property history(self) -> list[tuple[str, ClaudeResponse]]
          return list(self._history)  (defensive copy)
```

### Conversation internal state transitions:

```
INIT:
  _session_id = None
  _turn_count = 0
  _total_cost_usd = 0.0
  _history = []

AFTER .say("Hello"):
  _session_id = "abc-123"       ← from response
  _turn_count = 1
  _total_cost_usd = 0.035       ← from response.cost_usd
  _history = [("Hello", <response>)]

AFTER .say("Follow up"):
  _session_id = "abc-123"       ← same (resumed)
  _turn_count = 2
  _total_cost_usd = 0.055       ← accumulated
  _history = [("Hello", <r1>), ("Follow up", <r2>)]

AFTER .fork():
  Returns NEW Conversation:
    _session_id = "abc-123"     ← same as parent (to resume from)
    _fork_on_next = True        ← will add --fork-session on first .say()
    _turn_count = 2             ← copied
    _total_cost_usd = 0.055     ← copied
    _history = [...copied...]

AFTER forked_conv.say("Branch"):
  _session_id = "def-456"       ← NEW id (forked)
  _fork_on_next = False          ← consumed
  _turn_count = 3
  _total_cost_usd = 0.080
  _history = [...parent..., ("Branch", <r3>)]
```

---

## File 5: `streaming.py`

```
streaming.py
│
├── parse_stream_line(line: str) -> dict | None
│   │
│   │  Parses a single line from stream-json output.
│   │
│   │  line = line.strip()
│   │  if not line:
│   │    return None
│   │  try:
│   │    return json.loads(line)
│   │  except json.JSONDecodeError:
│   │    return None  (skip malformed lines)
│   │
│   └── Returns: dict or None
│
└── class StreamHandler
    │
    ├── __init__(self, process: subprocess.Popen, on_event: Callable | None = None)
    │     self._process = process
    │     self._on_event = on_event
    │     self._final_event: dict | None = None
    │
    ├── process_stream(self) -> dict | None
    │   │
    │   │  Reads all lines from process.stdout, calls on_event for each.
    │   │  Stores the last "result" type event as _final_event.
    │   │
    │   │  for line in self._process.stdout:
    │   │    event = parse_stream_line(line)
    │   │    if event is None: continue
    │   │    if self._on_event:
    │   │      self._on_event(event)
    │   │    if event.get("type") == "result":
    │   │      self._final_event = event
    │   │
    │   │  self._process.wait()
    │   │
    │   └── Returns: self._final_event (dict | None)
    │
    ├── iter_events(self) -> Iterator[dict]
    │   │
    │   │  Generator that yields events one by one.
    │   │
    │   │  for line in self._process.stdout:
    │   │    event = parse_stream_line(line)
    │   │    if event is None: continue
    │   │    yield event
    │   │    if event.get("type") == "result":
    │   │      self._final_event = event
    │   │
    │   │  self._process.wait()
    │   │
    │   └── Yields: dict
    │
    └── @property final_event(self) -> dict | None
          return self._final_event
```

### Stream event types from CLI:

```
Event types seen in stream-json output:

{"type": "system", ...}                    ← system info at start
{"type": "assistant", "message": {...}}    ← Claude's response chunks
{"type": "tool_use", ...}                  ← tool being called
{"type": "tool_result", ...}               ← tool output
{"type": "result", ...}                    ← FINAL result (same format as json mode)
```

---

## File 6: `__init__.py`

```
__init__.py
│
├── from .client import Claude
├── from .conversation import Conversation
├── from .models import ClaudeResponse
├── from .exceptions import (
│     ClaudeSDKError,
│     ClaudeCLINotFound,
│     ClaudeCLIError,
│     ClaudeSessionNotFound,
│     ClaudeSafetyError,
│   )
│
└── __all__ = [
      "Claude",
      "Conversation",
      "ClaudeResponse",
      "ClaudeSDKError",
      "ClaudeCLINotFound",
      "ClaudeCLIError",
      "ClaudeSessionNotFound",
      "ClaudeSafetyError",
    ]
```

---

## _build_command() — Full Flag Mapping Logic

This is the most complex method. Here's the exact logic for every flag:

```python
def _build_command(self, prompt: str, **overrides) -> list[str]:

    # Helper to resolve: per-call override > client setting
    def get(key, default=None):
        return overrides.pop(key, getattr(self, key, default))

    cmd = [self._cli_path, "-p", prompt]

    # --- Output format (always set) ---
    fmt = get("output_format", "json")
    cmd += ["--output-format", fmt]

    # --- Model & Prompt ---
    if v := get("model"):                cmd += ["--model", v]
    if v := get("system_prompt"):        cmd += ["--system-prompt", v]
    if v := get("append_system_prompt"): cmd += ["--append-system-prompt", v]
    if v := get("effort"):               cmd += ["--effort", v]
    if v := get("fallback_model"):       cmd += ["--fallback-model", v]

    # --- Tools & Permissions ---
    if v := get("tools"):
        if isinstance(v, list):
            cmd += ["--tools", ",".join(v)]
        else:
            cmd += ["--tools", v]  # handles "" for no tools
    if v := get("allowed_tools"):        cmd += ["--allowedTools"] + v
    if v := get("disallowed_tools"):     cmd += ["--disallowedTools"] + v
    if v := get("permission_mode"):      cmd += ["--permission-mode", v]
    if get("dangerously_skip_permissions"):      cmd += ["--dangerously-skip-permissions"]
    if get("allow_dangerously_skip_permissions"): cmd += ["--allow-dangerously-skip-permissions"]
    if get("disable_slash_commands"):    cmd += ["--disable-slash-commands"]

    # --- Session ---
    resume_id = get("resume")
    from_pr = get("from_pr")
    continue_session = get("continue_session", False)
    fork = get("fork", False)
    session_id = get("session_id")
    session_name = get("session_name")

    if resume_id:
        cmd += ["--resume", resume_id]
    elif from_pr:
        cmd += ["--from-pr", str(from_pr)]
    elif continue_session and self._last_session_id:
        cmd += ["--resume", self._last_session_id]

    if fork:                             cmd += ["--fork-session"]
    if session_id:                       cmd += ["--session-id", session_id]
    if session_name:                     cmd += ["--name", session_name]
    if get("no_session_persistence"):    cmd += ["--no-session-persistence"]

    # --- Agents ---
    if v := get("agent"):                cmd += ["--agent", v]
    if v := get("agents"):               cmd += ["--agents", json.dumps(v)]

    # --- Budget ---
    if v := get("max_budget_usd"):       cmd += ["--max-budget-usd", str(v)]

    # --- Structured Output ---
    if v := get("json_schema"):          cmd += ["--json-schema", json.dumps(v)]

    # --- MCP & Plugins ---
    if v := get("mcp_config"):
        if isinstance(v, list):          cmd += ["--mcp-config"] + v
        else:                            cmd += ["--mcp-config", v]
    if get("strict_mcp_config"):         cmd += ["--strict-mcp-config"]
    if v := get("plugin_dirs"):
        for d in v:                      cmd += ["--plugin-dir", d]

    # --- Input/Output ---
    if (v := get("input_format", "text")) != "text":
        cmd += ["--input-format", v]
    if get("replay_user_messages"):      cmd += ["--replay-user-messages"]

    # --- Settings ---
    if v := get("settings"):             cmd += ["--settings", v]
    if v := get("setting_sources"):      cmd += ["--setting-sources", ",".join(v)]

    # --- Remote Control ---
    if v := get("remote_control_prefix"):cmd += ["--remote-control-session-name-prefix", v]

    # --- Directories ---
    if v := get("add_dirs"):
        for d in v:                      cmd += ["--add-dir", d]

    # --- Advanced ---
    if get("bare"):                      cmd += ["--bare"]
    if v := get("betas"):                cmd += ["--betas"] + v
    if get("verbose"):                   cmd += ["--verbose"]
    if v := get("debug"):
        if isinstance(v, str):           cmd += ["--debug", v]
        elif v is True:                  cmd += ["--debug"]
    if v := get("debug_file"):           cmd += ["--debug-file", v]
    if v := get("files"):                cmd += ["--file"] + v
    if v := get("worktree"):
        if isinstance(v, str):           cmd += ["--worktree", v]
        elif v is True:                  cmd += ["--worktree"]
    if get("brief"):                     cmd += ["--brief"]
    if get("exclude_dynamic_prompt"):    cmd += ["--exclude-dynamic-system-prompt-sections"]

    # --- Streaming-specific ---
    if get("include_hook_events"):       cmd += ["--include-hook-events"]
    if get("include_partial_messages"):  cmd += ["--include-partial-messages"]

    return cmd
```

---

## Error Detection Logic in `_run()`

```
SUBPROCESS OUTPUT             DETECTION                    EXCEPTION RAISED
─────────────────             ─────────                    ────────────────
exit_code != 0 +              "session" + "not found"      ClaudeSessionNotFound
  stderr has session error      in stderr

exit_code != 0                any other stderr             ClaudeCLIError

exit_code == 0 but            json["is_error"] == True     (returned in response,
  response has is_error                                     not raised — user checks
                                                            response.is_error)

claude not in PATH            shutil.which returns None    ClaudeCLINotFound
  (checked at __init__ time)

unsafe config                 _validate_config checks      ClaudeSafetyError
  (checked at __init__ time)
```

---

## Complete Type Annotations

```python
# exceptions.py
class ClaudeSDKError(Exception): ...
class ClaudeCLINotFound(ClaudeSDKError): ...
class ClaudeCLIError(ClaudeSDKError):
    exit_code: int
    stderr: str
    raw_output: str | None
class ClaudeSessionNotFound(ClaudeCLIError):
    session_id: str
class ClaudeSafetyError(ClaudeSDKError):
    unsafe_setting: str

# models.py
@dataclass
class ClaudeResponse:
    result: str
    is_error: bool
    cost_usd: float
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    session_id: str
    stop_reason: str
    usage: dict[str, Any]
    model_usage: dict[str, Any]
    permission_denials: list[str]
    parsed: dict[str, Any] | None
    raw: dict[str, Any]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ClaudeResponse": ...

# client.py
class Claude:
    def __init__(self, *, model: str | None = None, ...) -> None: ...
    def ask(self, prompt: str, **overrides: Any) -> ClaudeResponse: ...
    def stream(self, prompt: str, on_event: Callable[[dict], None], **overrides: Any) -> ClaudeResponse: ...
    def stream_iter(self, prompt: str, **overrides: Any) -> Iterator[dict[str, Any]]: ...

# conversation.py
class Conversation:
    def __init__(self, client: Claude, system_prompt: str | None = None) -> None: ...
    def say(self, prompt: str, **overrides: Any) -> ClaudeResponse: ...
    def fork(self) -> "Conversation": ...

    @property
    def session_id(self) -> str | None: ...
    @property
    def total_cost_usd(self) -> float: ...
    @property
    def turn_count(self) -> int: ...
    @property
    def history(self) -> list[tuple[str, ClaudeResponse]]: ...

# streaming.py
def parse_stream_line(line: str) -> dict[str, Any] | None: ...
class StreamHandler:
    def __init__(self, process: subprocess.Popen, on_event: Callable[[dict], None] | None = None) -> None: ...
    def process_stream(self) -> dict[str, Any] | None: ...
    def iter_events(self) -> Iterator[dict[str, Any]]: ...

    @property
    def final_event(self) -> dict[str, Any] | None: ...
```

---

## Build Order

```
Step 1:  exceptions.py    (no dependencies)
Step 2:  models.py        (no internal dependencies)
Step 3:  streaming.py     (depends on models.py, exceptions.py)
Step 4:  client.py        (depends on all above)
Step 5:  conversation.py  (depends on client.py, models.py)
Step 6:  __init__.py      (imports from all above)
```

Each step can be tested independently before moving to the next.
