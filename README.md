# Claude SDK (Python)

A Python wrapper around the `claude` CLI that lets you call Claude from your code using your existing Claude subscription — no API key needed.

It works by spawning `claude -p <prompt> --output-format json` as a subprocess and parsing the response.

## Installation

```bash
git clone https://github.com/rmnjaat/claude_sdk.git
cd claude_sdk
```

**Prerequisite:** The [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) must be installed and authenticated.

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
- **Streaming** — `client.stream("prompt", on_event=callback)`
- **Multi-turn conversations** — `Conversation` class with automatic session tracking
- **Session management** — resume, fork, and name sessions
- **Structured output** — pass a JSON schema, get parsed dicts back
- **Custom agents** — define and use your own agent types
- **Safety presets** — `"safe"`, `"careful"`, `"full"` with sane defaults
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

## Usage Examples

### Continue a conversation

```python
response = client.ask("What is recursion?")
response = client.ask("Show me an example", continue_session=True)
```

### Multi-turn with Conversation helper

```python
from claude_sdk import Claude, Conversation

client = Claude(model="sonnet")
conv = Conversation(client)

r1 = conv.say("What is recursion?")
r2 = conv.say("Show me a Python example")  # auto-continues

print(conv.total_cost_usd)
print(conv.turn_count)
```

### Streaming

```python
def on_event(event):
    if event.get("type") == "assistant":
        for block in event["message"]["content"]:
            if block["type"] == "text":
                print(block["text"], end="", flush=True)

response = client.stream("Write a poem about code", on_event=on_event)
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
        }
    }
)
response = client.ask("Check auth.py", agent="reviewer")
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

## Response Object

```python
response = client.ask("Hello")

response.result            # The text response
response.cost_usd          # Cost of the call
response.session_id        # For resuming later
response.duration_ms       # Wall clock time
response.usage             # Token counts
response.num_turns         # Conversation turns
response.stop_reason       # "end_turn", "max_turns", etc.
response.permission_denials # Tools blocked by permissions
response.parsed            # Structured output (if json_schema used)
```

## Error Handling

```python
from claude_sdk import Claude
from claude_sdk.exceptions import (
    ClaudeSDKError,         # Base exception
    ClaudeCLINotFound,      # claude binary not in PATH
    ClaudeCLIError,         # CLI returned an error
    ClaudeSessionNotFound,  # Invalid session ID
    ClaudeSafetyError,      # Unsafe config without confirm_unsafe=True
)
```

## License

MIT
