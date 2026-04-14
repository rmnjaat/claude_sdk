# Claude SDK (Python) - Plan

## What is this?

A Python wrapper around the `claude` CLI that lets you call Claude from your code
using your existing Claude subscription (no API key needed).

It works by spawning `claude -p <prompt> --output-format json` as a subprocess
and parsing the response.

---

## Architecture

```
claude_sdk/
├── __init__.py          # Public API: from claude_sdk import Claude, Conversation
├── client.py            # Core client class - builds the CLI command, runs it, parses output
├── models.py            # Response dataclass (result, usage, cost, session_id, etc.)
├── exceptions.py        # Custom exceptions (CLINotFound, CLIError, SafetyError, etc.)
├── conversation.py      # Multi-turn conversation helper with automatic session tracking
├── streaming.py         # Streaming response handler (stream-json parsing + callbacks)
└── PLAN.md              # This file
```

Single package, 6 files. No external dependencies beyond Python stdlib.

---

## Core Class: `Claude`

```python
from claude_sdk import Claude

client = Claude(
    # --- Model & Prompt ---
    model="sonnet",                  # or "opus", "haiku", or full model ID
    system_prompt="You are ...",     # --system-prompt (replaces default)
    append_system_prompt=None,       # --append-system-prompt (adds to default)
    effort=None,                     # "low", "medium", "high", "max"
    fallback_model=None,             # --fallback-model for overload fallback

    # --- Tools & Permissions ---
    allowed_tools=None,              # list like ["Bash(git:*)", "Read"]
    disallowed_tools=None,           # list like ["Edit"]
    tools=None,                      # restrict built-in tool set, or [] for none
    permission_mode=None,            # "default", "plan", "auto", "acceptEdits",
                                     #  "bypassPermissions", "dontAsk"
    dangerously_skip_permissions=False,      # --dangerously-skip-permissions: bypass ALL checks
    allow_dangerously_skip_permissions=False, # --allow-dangerously-skip-permissions: enable the option
    disable_slash_commands=False,     # --disable-slash-commands: disable all skills

    # --- Safety (see Safety section below) ---
    safety="safe",                   # "safe" (default), "careful", "full"
    confirm_unsafe=False,            # must be True for dangerously_skip_permissions
    warn_on_permission_denial=True,  # print warning if tools were blocked

    # --- Session Behavior ---
    no_session_persistence=False,    # --no-session-persistence: ephemeral mode
    cwd=None,                        # working directory for subprocess
    add_dirs=None,                   # additional directories for tool access

    # --- Agents ---
    agent=None,                      # --agent: use a named agent
    agents=None,                     # --agents: dict defining custom agents

    # --- Budget ---
    max_budget_usd=None,             # spending cap per call
    max_turns=None,                  # max agentic turns

    # --- Output ---
    output_format="json",            # "json" or "stream-json"
    json_schema=None,                # JSON schema for structured output

    # --- MCP & Plugins ---
    mcp_config=None,                 # path(s) to MCP config JSON or JSON string
    strict_mcp_config=False,         # --strict-mcp-config: only use explicit MCP
    plugin_dirs=None,                # list of plugin directories

    # --- Input/Output ---
    input_format="text",             # --input-format: "text" (default) or "stream-json"
    replay_user_messages=False,      # --replay-user-messages: re-emit user msgs on stdout

    # --- Settings ---
    settings=None,                   # --settings: path to settings JSON or JSON string
    setting_sources=None,            # --setting-sources: list like ["user","project","local"]

    # --- Remote Control ---
    remote_control_prefix=None,      # --remote-control-session-name-prefix

    # --- Advanced ---
    bare=False,                      # --bare: minimal mode (no hooks, LSP, plugins)
    betas=None,                      # beta headers list
    verbose=False,                   # --verbose flag
    debug=False,                     # --debug: enable debug logging
    debug_file=None,                 # --debug-file: write debug logs to file
    files=None,                      # --file: file resources (file_id:path)
    worktree=None,                   # --worktree: create git worktree
    brief=False,                     # --brief: enable SendUserMessage tool
    exclude_dynamic_prompt=False,    # --exclude-dynamic-system-prompt-sections
)
```

### Methods

```python
# ──────────────────────────────────────────────
# 1. Simple one-shot call (new session each time)
# ──────────────────────────────────────────────
response = client.ask("Explain Python decorators")
print(response.result)       # the text
print(response.cost_usd)     # cost of that call
print(response.usage)        # token counts dict
print(response.duration_ms)  # how long it took
print(response.session_id)   # session ID for resuming later

# ──────────────────────────────────────────────
# 2. Continue the LAST conversation on this client
# ──────────────────────────────────────────────
# The client stores the session_id from the previous call internally.
# continue_session=True tells it to pass --resume <last_session_id>.
response = client.ask("Now show me an example", continue_session=True)

# ──────────────────────────────────────────────
# 3. Resume a SPECIFIC session by ID
# ──────────────────────────────────────────────
response = client.ask("What were we discussing?", resume="5b81a84a-c6d3-...")

# ──────────────────────────────────────────────
# 4. Fork a session (branch the conversation)
# ──────────────────────────────────────────────
# Creates a NEW session that starts with the full history of the original.
# The original session is untouched.
response = client.ask("Try a different approach", resume="abc-123", fork=True)
# response.session_id is now a NEW id, different from "abc-123"

# ──────────────────────────────────────────────
# 5. Custom session ID (for testing/tracking)
# ──────────────────────────────────────────────
import uuid
my_id = str(uuid.uuid4())
response = client.ask("Hello", session_id=my_id)
# response.session_id == my_id

# ──────────────────────────────────────────────
# 6. Named session (human-readable label)
# ──────────────────────────────────────────────
response = client.ask("Start my code review", session_name="code-review-pr-42")

# ──────────────────────────────────────────────
# 7. Structured output (returns parsed dict)
# ──────────────────────────────────────────────
response = client.ask(
    "Extract name and age from: John is 30",
    json_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"]
    }
)
print(response.parsed)  # {"name": "John", "age": 30}

# ──────────────────────────────────────────────
# 8. Streaming with callback
# ──────────────────────────────────────────────
def on_chunk(event):
    if event.get("type") == "assistant":
        print(event["message"]["content"], end="", flush=True)

response = client.stream("Write a poem about code", on_event=on_chunk)

# ──────────────────────────────────────────────
# 9. Custom agents
# ──────────────────────────────────────────────
response = client.ask(
    "Review this PR",
    agents={"reviewer": {"description": "Reviews code", "prompt": "You are a code reviewer"}},
    agent="reviewer"
)

# ──────────────────────────────────────────────
# 10. File resources
# ──────────────────────────────────────────────
response = client.ask("Summarize this document", files=["file_abc:doc.txt"])

# ──────────────────────────────────────────────
# 11. Resume from a PR
# ──────────────────────────────────────────────
response = client.ask("What's the status?", from_pr="123")
response = client.ask("Review this", from_pr="https://github.com/org/repo/pull/123")
```

---

## Subagents: How They Work

### What are subagents?

Claude Code has a built-in `Agent` tool. When Claude is working on a complex task,
it can **spawn subagents** — separate Claude instances that run in parallel to
research, explore code, or handle subtasks. This is NOT something our SDK needs
to implement — the CLI does it automatically.

### What our SDK needs to do

**Nothing special.** Subagents work out of the box when:
- The `Agent` tool is not blocked (it's in the default tool set)
- `max_turns` is high enough for Claude to actually use subagents (> 1)
- The permission mode allows the subagent's tools

### Example: subagents just work

```python
# With "careful" or "full" safety, subagents are available automatically
client = Claude(safety="full")

response = client.ask(
    "Refactor the auth module. Check all files that import from auth/ first."
)
# Claude may internally spawn subagents to:
# - Search for all auth imports (Explore agent)
# - Read and analyze each file (general-purpose agent)
# - Plan the refactoring (Plan agent)
# All of this happens INSIDE the single .ask() call
```

### Custom agents (user-defined)

Beyond built-in subagents, users can define their own agent types:

```python
# Define custom agents inline
client = Claude(
    agents={
        "reviewer": {
            "description": "Reviews code for bugs and style",
            "prompt": "You are a senior code reviewer. Focus on correctness and readability."
        },
        "security": {
            "description": "Security audit agent",
            "prompt": "You are a security expert. Find vulnerabilities."
        }
    }
)

# Use a specific custom agent
response = client.ask("Check auth.py", agent="reviewer")

# Or use the default agent but it can spawn your custom agents as subagents
response = client.ask("Do a full review and security audit of src/")
# Claude can now spawn "reviewer" and "security" as subagents
```

### What the SDK exposes

The response tells you what happened with subagents:

```python
response = client.ask("Complex task here", safety="full")
print(response.num_turns)     # How many turns (including subagent work)
print(response.cost_usd)      # Total cost (including subagent costs)
print(response.model_usage)   # Per-model breakdown shows subagent model usage
```

---

## Session Management: How It Works

### The Rules

1. **No flags** → every `client.ask()` creates a **new session** automatically.
2. **`continue_session=True`** → reuses the `session_id` from the **last call** on this client.
   Internally stores it in `self._last_session_id`.
3. **`resume="<id>"`** → resumes a **specific** session by explicit ID.
4. **`fork=True`** (with resume or continue_session) → **branches** the conversation.
   Creates a new session ID but carries the full history. Original session is untouched.
5. **`session_id="<uuid>"`** → forces a specific UUID as the session ID (for deterministic testing).
6. **`session_name="..."`** → gives the session a human-readable label (`--name`).
7. **`from_pr="..."`** → resumes a session linked to a PR (`--from-pr`).
8. **`no_session_persistence=True`** (on client) → sessions are ephemeral, never saved to disk.

### Internal Flow

```
client.ask("prompt", continue_session=True)
    │
    ├─ Has self._last_session_id?
    │   ├─ Yes → add --resume <self._last_session_id> to command
    │   └─ No  → skip (first call, so it's a new session)
    │
    ├─ Run subprocess: claude -p "prompt" --output-format json [--resume ...]
    │
    ├─ Parse JSON response
    │
    ├─ Store response.session_id → self._last_session_id
    │
    └─ Return ClaudeResponse
```

### Priority (if conflicting flags are passed)

1. `resume="<id>"` wins (explicit ID always takes priority)
2. `from_pr="..."` (specific PR session)
3. `continue_session=True` uses `self._last_session_id`
4. If all absent → new session
5. `fork=True` adds `--fork-session` alongside whichever resume method was chosen

---

## Conversation Helper

For multi-turn conversations, a dedicated `Conversation` class makes it even simpler:

```python
from claude_sdk import Claude, Conversation

client = Claude(model="sonnet")

# Starts a new session, auto-continues on every .say() call
conv = Conversation(client, system_prompt="You are a helpful tutor")

r1 = conv.say("What is recursion?")
print(r1.result)

r2 = conv.say("Show me a Python example")
print(r2.result)  # Claude remembers the previous context

r3 = conv.say("Now explain the base case")
print(r3.result)  # Still in the same session

# Access session info
print(conv.session_id)       # The session ID
print(conv.total_cost_usd)   # Cumulative cost across all turns
print(conv.turn_count)       # Number of turns so far
print(conv.history)          # List of (prompt, response) tuples

# Fork the conversation (try a different direction without losing history)
conv2 = conv.fork()
r4 = conv2.say("Actually explain with a tree analogy instead")
# conv2 has a NEW session id, but starts with all the history from conv
# conv is untouched
```

### Why Conversation exists separately from Claude

- `Claude` is stateless (except `_last_session_id` for convenience).
  Each `.ask()` is independent unless you explicitly pass `continue_session=True`.
- `Conversation` is stateful by design — it tracks session ID, cost, turns, and history.
  Every `.say()` automatically continues the session.
- This separation means you can use one `Claude` client for many independent calls,
  but when you want a multi-turn chat, `Conversation` handles all the bookkeeping.

---

## CLI Flags Mapped to Python Parameters

| Python Parameter          | CLI Flag                                    | Type              |
|--------------------------|---------------------------------------------|-------------------|
| **Model & Prompt** | | |
| `model`                  | `--model`                                   | str               |
| `system_prompt`           | `--system-prompt`                           | str               |
| `append_system_prompt`    | `--append-system-prompt`                    | str               |
| `effort`                 | `--effort`                                  | str               |
| `fallback_model`         | `--fallback-model`                          | str               |
| **Tools & Permissions** | | |
| `allowed_tools`          | `--allowedTools`                            | list[str]         |
| `disallowed_tools`       | `--disallowedTools`                         | list[str]         |
| `tools`                  | `--tools`                                   | list[str]         |
| `permission_mode`        | `--permission-mode`                         | str               |
| `dangerously_skip_permissions` | `--dangerously-skip-permissions`       | bool              |
| `allow_dangerously_skip_permissions` | `--allow-dangerously-skip-permissions` | bool          |
| `disable_slash_commands` | `--disable-slash-commands`                  | bool              |
| **Session** | | |
| `continue_session`       | (uses stored session_id → `--resume`)       | bool (per-call)   |
| `resume`                 | `--resume`                                  | str (per-call)    |
| `fork`                   | `--fork-session`                            | bool (per-call)   |
| `session_id`             | `--session-id`                              | str (per-call)    |
| `session_name`           | `--name`                                    | str (per-call)    |
| `from_pr`                | `--from-pr`                                 | str (per-call)    |
| `no_session_persistence` | `--no-session-persistence`                  | bool              |
| **Agents** | | |
| `agent`                  | `--agent`                                   | str               |
| `agents`                 | `--agents`                                  | dict (→ JSON str) |
| **Budget** | | |
| `max_budget_usd`         | `--max-budget-usd`                          | float             |
| `max_turns`              | (handled internally)                         | int               |
| **Output** | | |
| `output_format`          | `--output-format`                           | str               |
| `json_schema`            | `--json-schema`                             | dict              |
| **MCP & Plugins** | | |
| `mcp_config`             | `--mcp-config`                              | str or list[str]  |
| `strict_mcp_config`      | `--strict-mcp-config`                       | bool              |
| `plugin_dirs`            | `--plugin-dir` (repeatable)                 | list[str]         |
| **Directories** | | |
| `cwd`                   | (subprocess cwd)                             | str               |
| `add_dirs`               | `--add-dir`                                 | list[str]         |
| **Input/Output** | | |
| `input_format`           | `--input-format`                            | str               |
| `replay_user_messages`   | `--replay-user-messages`                    | bool              |
| **Settings** | | |
| `settings`               | `--settings`                                | str               |
| `setting_sources`        | `--setting-sources`                         | list[str]         |
| **Remote Control** | | |
| `remote_control_prefix`  | `--remote-control-session-name-prefix`      | str               |
| **Advanced** | | |
| `bare`                   | `--bare`                                    | bool              |
| `betas`                  | `--betas`                                   | list[str]         |
| `verbose`                | `--verbose`                                 | bool              |
| `debug`                  | `--debug`                                   | bool or str       |
| `debug_file`             | `--debug-file`                              | str               |
| `files`                  | `--file`                                    | list[str]         |
| `worktree`               | `--worktree`                                | bool or str       |
| `brief`                  | `--brief`                                   | bool              |
| `exclude_dynamic_prompt` | `--exclude-dynamic-system-prompt-sections`  | bool              |
| **Streaming-specific (per-call)** | | |
| `include_hook_events`    | `--include-hook-events`                     | bool              |
| `include_partial_messages`| `--include-partial-messages`               | bool              |

---

## Response Model

```python
@dataclass
class ClaudeResponse:
    result: str              # The text response
    is_error: bool           # Whether the CLI reported an error
    cost_usd: float          # Total cost of the call
    duration_ms: int         # Wall clock time
    duration_api_ms: int     # API time only
    num_turns: int           # Number of conversation turns
    session_id: str          # For resuming later
    stop_reason: str         # "end_turn", "max_turns", etc.
    usage: dict              # Raw token usage dict
    model_usage: dict        # Per-model breakdown (tokens, cost, context window)
    permission_denials: list # Tools that were blocked by permission checks
    parsed: dict | None      # If json_schema was used, the parsed structured output
    raw: dict                # The full raw JSON from the CLI (for anything we missed)
```

---

## Safety & Permissions

This is critical. Our SDK runs `claude -p` as a subprocess. Claude Code has tools
that can run shell commands, edit files, delete things. In `-p` mode there is NO
interactive prompt to ask "are you sure?" — it either does the action or skips it
based on the permission mode. So our SDK must be safe by default.

### Layer 1: Safe Defaults (what the SDK does out of the box)

```python
# These are the DEFAULTS if the user doesn't set anything:
DEFAULT_PERMISSION_MODE = "plan"        # Read-only. Cannot write files or run commands.
DEFAULT_TOOLS = ["Read", "Glob", "Grep"] # Only read-access tools
DEFAULT_MAX_TURNS = 1                    # Single turn, no agentic loops
DEFAULT_MAX_BUDGET_USD = 1.0             # Cap at $1 per call
```

With these defaults, even if the user writes:
```python
client = Claude()
client.ask("Delete all my files")
```
Nothing bad happens — Claude is in `plan` mode with only read tools. It will
say "I would delete the files" but cannot actually do it.

### Layer 2: Explicit Opt-in for Danger (escalation levels)

We define 3 safety presets that map to sensible combinations:

```python
# SAFE (default) — read-only, cannot modify anything
client = Claude()
# permission_mode="plan", tools=["Read","Glob","Grep"], max_turns=1

# CAREFUL — can edit files but cannot run arbitrary shell commands
client = Claude(safety="careful")
# permission_mode="acceptEdits", tools=["Read","Glob","Grep","Edit","Write"]
# disallowed_tools=["Bash"], max_turns=3, max_budget_usd=5.0

# FULL — full access including subagents, user takes responsibility
client = Claude(safety="full")
# permission_mode="auto", tools=default (all, including Agent), max_turns=10
# max_budget_usd=20.0
# Prints a warning to stderr: "WARNING: Full tool access enabled. Claude can
# run commands, modify files, and spawn subagents."
```

Users can also override individual settings — the presets are just starting points.
Any explicit parameter overrides the preset:

```python
# Start from "careful" but also allow Bash for git commands only
client = Claude(safety="careful", allowed_tools=["Bash(git:*)"])
```

### Layer 3: Dangerous Mode Validation

The SDK **refuses** certain combinations unless the user explicitly acknowledges the risk:

```python
# This RAISES ClaudeSafetyError:
client = Claude(permission_mode="bypassPermissions")
# Error: "bypassPermissions skips ALL safety checks. Pass confirm_unsafe=True
#         if you understand the risk."

# This works (user explicitly opted in):
client = Claude(permission_mode="bypassPermissions", confirm_unsafe=True)
# Still prints a WARNING to stderr
```

Rules enforced:
- `permission_mode="bypassPermissions"` → requires `confirm_unsafe=True`
- `dangerously_skip_permissions=True` → requires `confirm_unsafe=True`
- `allow_dangerously_skip_permissions=True` → requires `confirm_unsafe=True`
- `permission_mode="auto"` + no tool restrictions → prints warning (but allows)
- `max_turns > 20` → prints warning about cost/runaway loops

### Layer 4: Tool Restrictions (what Claude CAN'T do)

The CLI supports fine-grained tool control. Our SDK exposes this clearly:

```python
# Only allow read operations
client = Claude(tools=["Read", "Glob", "Grep"])

# Allow Bash but ONLY for git commands
client = Claude(allowed_tools=["Bash(git:*)"])

# Allow everything EXCEPT file deletion
client = Claude(disallowed_tools=["Bash(rm:*)", "Bash(rmdir:*)"])

# No tools at all (pure text Q&A, like a chatbot)
client = Claude(tools=[])
```

### Layer 5: Directory Sandboxing

By default, the subprocess runs in the current working directory.
Claude Code can only access files in the working directory and `--add-dir` directories.

```python
# Claude can only see/touch files in /tmp/sandbox
client = Claude(cwd="/tmp/sandbox")

# Claude can see /tmp/sandbox + one more directory (read-only access)
client = Claude(cwd="/tmp/sandbox", add_dirs=["/data/inputs"])
```

### Layer 6: Budget Protection

Prevents runaway costs:

```python
client = Claude(
    max_budget_usd=5.0,   # Hard spending cap (CLI enforces this)
    max_turns=3,           # Max 3 back-and-forth turns
)
```

### Layer 7: Response Validation

The SDK checks the response for signs of trouble:

```python
response = client.ask("Do something")

# These are always available:
response.is_error          # CLI reported an error
response.permission_denials # List of tools that were DENIED by permission checks
response.stop_reason       # "end_turn" (normal) vs "max_turns" (hit limit)
```

If `permission_denials` is non-empty, it means Claude tried to do something
that the permission mode blocked. The SDK can optionally warn about this:

```python
client = Claude(warn_on_permission_denial=True)
# Prints: "WARNING: Claude tried to use Bash but was denied by permission mode"
```

### Summary: What Happens by Default

| Concern | Default Protection |
|---------|-------------------|
| File deletion | Blocked (plan mode + read-only tools) |
| Arbitrary commands | Blocked (Bash not in default tools) |
| File modification | Blocked (Edit/Write not in default tools) |
| Subagent spawning | Blocked (Agent not in default tools) |
| Runaway cost | Capped at $1.00 per call |
| Agentic loops | Limited to 1 turn |
| Dangerous permission modes | Requires `confirm_unsafe=True` |

**The principle: safe by default, dangerous only by explicit choice.**

---

## Error Handling

- `ClaudeCLINotFound` - `claude` binary not in PATH
- `ClaudeCLIError` - CLI returned an error (auth issues, invalid flags, etc.)
- `ClaudeSessionNotFound` - resume/continue with a session_id that doesn't exist
- `ClaudeSafetyError` - unsafe configuration without `confirm_unsafe=True`
- All inherit from `ClaudeSDKError` base class

---

## Streaming Support

For real-time output processing using `--output-format stream-json`:

```python
# Option A: callback-based
def on_event(event: dict):
    """Called for each JSON line from stream-json output"""
    if event.get("type") == "assistant":
        content = event["message"]["content"]
        for block in content:
            if block["type"] == "text":
                print(block["text"], end="", flush=True)

response = client.stream("Write a story", on_event=on_event)
# on_event is called in real-time as chunks arrive
# response is the final ClaudeResponse after completion

# Option B: iterator-based
for event in client.stream_iter("Write a story"):
    # process each event dict
    pass

# Option C: with partial messages (live token-by-token)
response = client.stream(
    "Write a story",
    on_event=on_event,
    include_partial_messages=True  # get chunks as they arrive
)

# Option D: with hook events (see tool lifecycle)
response = client.stream(
    "Fix this bug",
    on_event=on_event,
    include_hook_events=True  # see hook before/after events
)
```

### How streaming works internally

1. Runs `claude -p "..." --output-format stream-json [--include-partial-messages]`
2. Reads stdout line by line (each line is a JSON object)
3. Calls `on_event(parsed_json)` for each line
4. The **last** line with `type: "result"` is parsed into `ClaudeResponse`

---

## Built-in Tools Available to Claude

When Claude runs via our SDK, it has access to these tools (depending on permission/safety level):

### Always loaded
| Tool | What it does |
|------|-------------|
| `Read` | Read files |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents |
| `Edit` | Edit files (requires acceptEdits or higher) |
| `Write` | Create/overwrite files |
| `Bash` | Run shell commands |
| `Agent` | Spawn subagents for parallel work |
| `Skill` | Execute skills/slash commands |
| `ToolSearch` | Activate deferred tools |
| `ScheduleWakeup` | Schedule delayed work |

### Deferred (activated on demand by Claude via ToolSearch)
| Tool | What it does |
|------|-------------|
| `WebSearch` | Search the web |
| `WebFetch` | Fetch a URL |
| `NotebookEdit` | Edit Jupyter notebooks |
| `Monitor` | Stream events from background processes |
| `EnterWorktree` / `ExitWorktree` | Git worktree isolation |
| `EnterPlanMode` / `ExitPlanMode` | Switch to/from plan mode |
| `CronCreate` / `CronDelete` / `CronList` | Scheduled tasks |
| `RemoteTrigger` | Trigger remote agents |

Our SDK's safety presets control which of these tools Claude can use via the
`--tools`, `--allowedTools`, and `--disallowedTools` flags.

---

## Implementation Steps

1. **`exceptions.py`** - Define exception classes
   - `ClaudeSDKError` (base), `ClaudeCLINotFound`, `ClaudeCLIError`,
     `ClaudeSessionNotFound`, `ClaudeSafetyError`

2. **`models.py`** - Define `ClaudeResponse` dataclass
   - `from_json(raw: dict)` classmethod that maps CLI JSON → dataclass
   - Handles `permission_denials`, `model_usage`, `parsed` (structured output)

3. **`client.py`** - The `Claude` class:
   - `__init__` stores config + `_last_session_id = None`
   - `_apply_safety_preset(safety)` sets defaults based on "safe"/"careful"/"full"
   - `_validate_config()` checks for dangerous combos, raises `ClaudeSafetyError`
   - `_build_command(prompt, **overrides)` assembles the CLI args list
   - `_find_cli()` checks `claude` is in PATH, raises `ClaudeCLINotFound`
   - `_run(command)` runs subprocess, returns raw output
   - `ask(prompt, **overrides)` full pipeline: validate → build → run → parse → store session → return
   - `stream(prompt, on_event, **overrides)` streams output line by line, calls callback
   - `stream_iter(prompt, **overrides)` returns an iterator over stream events

4. **`conversation.py`** - The `Conversation` class:
   - `__init__(client, system_prompt)` creates a new conversation context
   - `say(prompt)` sends a message (auto-continues session)
   - `fork()` creates a branched copy via `--fork-session`
   - Properties: `session_id`, `total_cost_usd`, `turn_count`, `history`

5. **`streaming.py`** - Stream parser utilities:
   - `parse_stream_line(line)` parses a single JSON line
   - `StreamHandler` class that manages the line-by-line reading

6. **`__init__.py`** - Export `Claude`, `Conversation`, `ClaudeResponse`, and exceptions

---

## What this does NOT do (v1 scope)

- No async (`asyncio.subprocess`) - can be added in v2
- No conversation memory management beyond session resume (CLI handles persistence)
- No file upload handling beyond `--file` flag
- No bidirectional streaming (`--input-format stream-json` both directions)
- No interactive mode (stdin/stdout back and forth)

These can be added later if needed.
