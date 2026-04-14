# Claude SDK (Python)

A Python wrapper around the `claude` CLI that lets you call Claude from your code using your existing Claude subscription — no API key needed.

It works by spawning `claude -p <prompt> --output-format json` as a subprocess and parsing the response.

## Installation

```bash
git clone https://github.com/rmnjaat/claude_sdk.git
cd claude_sdk
```

**Prerequisite:** The [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) must be installed and authenticated.

```bash
npm install -g @anthropic-ai/claude-code
```

## Quick Start

```python
from claude_sdk import Claude

# Safe by default — read-only, $1 budget cap
client = Claude()
response = client.ask("Explain Python decorators")
print(response.result)
print(response.cost_usd)
```

## Features

- **One-shot queries** — `client.ask("prompt")`
- **Streaming** — `client.stream("prompt", on_event=callback)` or `client.stream_iter("prompt")`
- **Multi-turn conversations** — `Conversation` class with automatic session tracking
- **Session management** — resume, fork, name sessions, and resume from PRs
- **Structured output** — pass a JSON schema, get parsed dicts back
- **Custom agents** — define and use your own agent types
- **Safety presets** — `"safe"`, `"careful"`, `"full"` with sane defaults
- **Fine-grained tool control** — allow/disallow specific tools or tool patterns
- **Directory sandboxing** — restrict Claude's file access to specific directories
- **Budget protection** — per-call spending caps and turn limits
- **No external dependencies** — pure Python stdlib

## Safety Presets

| Preset | Permission Mode | Tools | Max Turns | Budget |
|--------|----------------|-------|-----------|--------|
| `safe` (default) | `plan` | Read, Glob, Grep | 1 | $1 |
| `careful` | `acceptEdits` | + Edit, Write | 3 | $5 |
| `full` | `auto` | All (including Bash, Agent) | 10 | $20 |

```python
# Read-only (default)
client = Claude()

# Can edit files but not run shell commands
client = Claude(safety="careful")

# Full access — use with caution
client = Claude(safety="full")
```

Any explicit parameter overrides the preset:

```python
# Start from "careful" but also allow Bash for git commands only
client = Claude(safety="careful", allowed_tools=["Bash(git:*)"])
```

## Usage Examples

### Choose a model

```python
client = Claude(model="sonnet")
# Also: "opus", "haiku", or a full model ID like "claude-sonnet-4-6"
```

### One-shot query

```python
response = client.ask("Explain Python decorators")
print(response.result)
```

### Continue a conversation

```python
response = client.ask("What is recursion?")
response = client.ask("Show me an example", continue_session=True)
```

### Resume a specific session

```python
response = client.ask("Where were we?", resume="5b81a84a-c6d3-...")
```

### Fork a session (branch the conversation)

```python
# Creates a NEW session that starts with full history of the original
response = client.ask("Try a different approach", resume="abc-123", fork=True)
# response.session_id is now a new ID; the original session is untouched
```

### Named sessions

```python
response = client.ask("Start my code review", session_name="code-review-pr-42")
```

### Custom session ID

```python
import uuid
my_id = str(uuid.uuid4())
response = client.ask("Hello", session_id=my_id)
```

### Resume from a PR

```python
response = client.ask("What's the status?", from_pr="123")
response = client.ask("Review this", from_pr="https://github.com/org/repo/pull/123")
```

### Multi-turn with Conversation helper

```python
from claude_sdk import Claude, Conversation

client = Claude(model="sonnet")
conv = Conversation(client, system_prompt="You are a helpful tutor")

r1 = conv.say("What is recursion?")
r2 = conv.say("Show me a Python example")  # auto-continues
r3 = conv.say("Now explain the base case")  # still same session

print(conv.session_id)       # session UUID
print(conv.total_cost_usd)   # cumulative cost
print(conv.turn_count)       # 3
print(conv.history)          # list of (prompt, response) tuples

# Fork the conversation (try a different direction)
conv2 = conv.fork()
r4 = conv2.say("Try a tree analogy instead")
# conv2 has a new session; conv is untouched
```

### Streaming (callback-based)

```python
def on_event(event):
    if event.get("type") == "assistant":
        for block in event["message"]["content"]:
            if block["type"] == "text":
                print(block["text"], end="", flush=True)

response = client.stream("Write a poem about code", on_event=on_event)
```

### Streaming (iterator-based)

```python
for event in client.stream_iter("Write a poem about code"):
    if event.get("type") == "assistant":
        for block in event["message"]["content"]:
            if block["type"] == "text":
                print(block["text"], end="", flush=True)
```

### Streaming with partial messages

```python
response = client.stream(
    "Write a story",
    on_event=on_event,
    include_partial_messages=True  # get token-by-token chunks
)
```

### Structured output

```python
response = client.ask(
    "Extract name and age from: John is 30",
    json_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"]
    }
)
print(response.parsed)  # {"name": "John", "age": 30}
```

### Custom agents

```python
client = Claude(
    safety="full",
    agents={
        "reviewer": {
            "description": "Reviews code for bugs and style",
            "prompt": "You are a senior code reviewer."
        },
        "security": {
            "description": "Security audit agent",
            "prompt": "You are a security expert. Find vulnerabilities."
        }
    }
)
response = client.ask("Check auth.py", agent="reviewer")
```

## Tool Control

Fine-grained control over what Claude can do:

```python
# Only allow read operations (default in "safe" preset)
client = Claude(tools=["Read", "Glob", "Grep"])

# Allow Bash but ONLY for git commands
client = Claude(allowed_tools=["Bash(git:*)"])

# Allow everything EXCEPT file deletion
client = Claude(disallowed_tools=["Bash(rm:*)", "Bash(rmdir:*)"])

# No tools at all (pure text Q&A, like a chatbot)
client = Claude(tools=[])
```

## Directory Sandboxing

Restrict which directories Claude can access:

```python
# Claude can only see/touch files in /tmp/sandbox
client = Claude(cwd="/tmp/sandbox")

# Claude can access /tmp/sandbox + an additional directory
client = Claude(cwd="/tmp/sandbox", add_dirs=["/data/inputs"])
```

## Budget Protection

Prevent runaway costs:

```python
client = Claude(
    max_budget_usd=5.0,  # hard spending cap per call
    max_turns=3,          # max agentic turns per call
)
```

## Dangerous Mode

Certain configurations require explicit opt-in:

```python
# This RAISES ClaudeSafetyError:
client = Claude(permission_mode="bypassPermissions")

# This works (explicit acknowledgement):
client = Claude(permission_mode="bypassPermissions", confirm_unsafe=True)
```

Rules enforced:
- `permission_mode="bypassPermissions"` requires `confirm_unsafe=True`
- `dangerously_skip_permissions=True` requires `confirm_unsafe=True`
- `allow_dangerously_skip_permissions=True` requires `confirm_unsafe=True`
- `max_turns > 20` prints a warning about runaway cost

## MCP & Plugins

```python
# Use an MCP config file
client = Claude(mcp_config="/path/to/mcp-config.json")

# Multiple MCP configs
client = Claude(mcp_config=["/path/to/config1.json", "/path/to/config2.json"])

# Strict MCP (only use explicitly configured MCP servers)
client = Claude(mcp_config="/path/to/config.json", strict_mcp_config=True)

# Plugin directories
client = Claude(plugin_dirs=["/path/to/plugins"])
```

## Advanced Options

```python
client = Claude(
    system_prompt="You are ...",              # replace default system prompt
    append_system_prompt="Also do ...",       # add to default system prompt
    effort="high",                            # "low", "medium", "high", "max"
    fallback_model="haiku",                   # fallback model on overload
    no_session_persistence=True,              # ephemeral sessions (not saved to disk)
    bare=True,                                # minimal mode (no hooks, LSP, plugins)
    verbose=True,                             # verbose output
    debug=True,                               # debug logging
    debug_file="/tmp/claude-debug.log",       # write debug logs to file
    files=["file_abc:doc.txt"],               # file resources
    worktree=True,                            # create git worktree for isolation
    brief=True,                               # enable SendUserMessage tool
    settings="/path/to/settings.json",        # custom settings file
    setting_sources=["user", "project"],      # which setting sources to use
    betas=["beta-feature"],                   # beta feature flags
    disable_slash_commands=True,              # disable all skills/slash commands
    exclude_dynamic_prompt=True,              # exclude dynamic system prompt sections
)
```

## Project Structure

```
claude_sdk/
├── __init__.py        # Public API exports
├── client.py          # Core Claude class — builds CLI commands, runs subprocess, parses output
├── models.py          # ClaudeResponse dataclass
├── exceptions.py      # Custom exceptions (CLINotFound, CLIError, SafetyError, etc.)
├── conversation.py    # Multi-turn Conversation helper with session tracking
└── streaming.py       # Streaming response handler (stream-json parsing + callbacks)
```

No external dependencies — pure Python stdlib.

## Response Object

```python
response = client.ask("Hello")

response.result              # The text response
response.is_error            # Whether the CLI reported an error
response.cost_usd            # Cost of the call
response.duration_ms         # Wall clock time
response.duration_api_ms     # API-only time
response.num_turns           # Conversation turns
response.session_id          # Session UUID for resuming later
response.stop_reason         # "end_turn", "max_turns", etc.
response.usage               # Raw token usage dict
response.model_usage         # Per-model breakdown (tokens, cost, context window)
response.permission_denials  # Tools blocked by permissions
response.parsed              # Structured output dict (if json_schema used)
response.raw                 # Full raw JSON dict from the CLI
```

## Error Handling

```python
from claude_sdk.exceptions import (
    ClaudeSDKError,         # Base exception for all SDK errors
    ClaudeCLINotFound,      # claude binary not in PATH
    ClaudeCLIError,         # CLI returned an error (auth issues, invalid flags, etc.)
    ClaudeSessionNotFound,  # Invalid session ID for resume/continue
    ClaudeSafetyError,      # Unsafe config without confirm_unsafe=True
)

try:
    response = client.ask("Hello")
except ClaudeCLINotFound:
    print("Install Claude CLI: npm install -g @anthropic-ai/claude-code")
except ClaudeSessionNotFound as e:
    print(f"Session {e.session_id} not found")
except ClaudeSafetyError as e:
    print(f"Unsafe setting: {e.unsafe_setting}")
except ClaudeCLIError as e:
    print(f"CLI error (exit {e.exit_code}): {e.message}")
```

## CLI Flags Reference

Every `claude` CLI flag has a corresponding Python parameter:

| Python Parameter | CLI Flag | Type |
|---|---|---|
| `model` | `--model` | `str` |
| `system_prompt` | `--system-prompt` | `str` |
| `append_system_prompt` | `--append-system-prompt` | `str` |
| `effort` | `--effort` | `str` |
| `fallback_model` | `--fallback-model` | `str` |
| `allowed_tools` | `--allowedTools` | `list[str]` |
| `disallowed_tools` | `--disallowedTools` | `list[str]` |
| `tools` | `--tools` | `list[str]` |
| `permission_mode` | `--permission-mode` | `str` |
| `dangerously_skip_permissions` | `--dangerously-skip-permissions` | `bool` |
| `max_budget_usd` | `--max-budget-usd` | `float` |
| `json_schema` | `--json-schema` | `dict` |
| `mcp_config` | `--mcp-config` | `str` or `list[str]` |
| `cwd` | subprocess working directory | `str` |
| `add_dirs` | `--add-dir` | `list[str]` |
| `agent` | `--agent` | `str` |
| `agents` | `--agents` | `dict` |
| `verbose` | `--verbose` | `bool` |
| `debug` | `--debug` | `bool` or `str` |
| `bare` | `--bare` | `bool` |
| `files` | `--file` | `list[str]` |
| `worktree` | `--worktree` | `bool` or `str` |

See [PLAN.md](PLAN.md) for the full mapping of all 40+ parameters.

## License

MIT
