# Claude SDK - Architecture Diagram

## High-Level Overview

How your Python code talks to Claude through the CLI:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        YOUR PYTHON CODE                             │
│                                                                     │
│   from claude_sdk import Claude, Conversation                       │
│   client = Claude(model="sonnet", safety="careful")                 │
│   response = client.ask("Explain recursion")                        │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         claude_sdk (Python)                          │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │__init__.py│  │client.py │  │models.py   │  │exceptions.py     │  │
│  │          │  │          │  │            │  │                  │  │
│  │ Public   │  │ Claude   │  │ Claude     │  │ ClaudeSDKError   │  │
│  │ exports  │  │ class    │  │ Response   │  │ ClaudeCLINotFound│  │
│  │          │  │          │  │ dataclass  │  │ ClaudeCLIError   │  │
│  │          │  │ .ask()   │  │            │  │ ClaudeSession    │  │
│  │          │  │ .stream()│  │ .from_json │  │  NotFound        │  │
│  │          │  │          │  │ ()         │  │ ClaudeSafetyError│  │
│  └──────────┘  └──────────┘  └────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌───────────────┐  ┌──────────────┐                                │
│  │conversation.py│  │streaming.py  │                                │
│  │               │  │              │                                │
│  │ Conversation  │  │ StreamHandler│                                │
│  │ class         │  │              │                                │
│  │               │  │ parse_stream │                                │
│  │ .say()        │  │ _line()      │                                │
│  │ .fork()       │  │              │                                │
│  └───────────────┘  └──────────────┘                                │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                      subprocess.run()
                      or subprocess.Popen()
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     CLAUDE CLI (subprocess)                          │
│                                                                     │
│   claude -p "Explain recursion"                                     │
│          --output-format json                                       │
│          --model sonnet                                             │
│          --permission-mode acceptEdits                              │
│          --tools "Read,Glob,Grep,Edit,Write"                        │
│          --max-budget-usd 5.0                                       │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                          HTTPS / API
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     ANTHROPIC API (cloud)                            │
│                                                                     │
│   Claude model processes the request                                │
│   Uses tools (Read, Bash, Agent, etc.) as needed                    │
│   Returns JSON response                                             │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                          JSON response
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     BACK TO claude_sdk                               │
│                                                                     │
│   stdout → JSON string → ClaudeResponse dataclass                   │
│                                                                     │
│   ClaudeResponse(                                                   │
│     result="Recursion is when a function calls itself...",          │
│     cost_usd=0.035,                                                 │
│     session_id="5b81a84a-c6d3-...",                                 │
│     ...                                                             │
│   )                                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Dependency Graph

Who imports whom:

```
__init__.py
    ├── imports from client.py        → Claude
    ├── imports from conversation.py  → Conversation
    ├── imports from models.py        → ClaudeResponse
    └── imports from exceptions.py    → All exceptions

client.py
    ├── imports from models.py        → ClaudeResponse
    ├── imports from exceptions.py    → All exceptions
    └── imports from streaming.py     → StreamHandler

conversation.py
    ├── imports from client.py        → Claude (type hint only)
    └── imports from models.py        → ClaudeResponse

streaming.py
    ├── imports from models.py        → ClaudeResponse
    └── imports from exceptions.py    → ClaudeCLIError

models.py
    └── (no internal imports — leaf module)

exceptions.py
    └── (no internal imports — leaf module)
```

Build order (bottom-up): `exceptions.py` → `models.py` → `streaming.py` → `client.py` → `conversation.py` → `__init__.py`

---

## Data Flow: client.ask()

What happens when you call `client.ask("prompt")`:

```
                    client.ask("Explain recursion")
                               │
                ┌──────────────┴──────────────┐
                │     1. SAFETY CHECK          │
                │                              │
                │  _apply_safety_preset()      │
                │  _validate_config()          │
                │                              │
                │  Is permission_mode unsafe?  │
                │  Is confirm_unsafe=True?     │
                │  Are tools restricted?       │
                │                              │
                │  FAIL → ClaudeSafetyError    │
                └──────────────┬──────────────┘
                               │ PASS
                ┌──────────────┴──────────────┐
                │     2. FIND CLI              │
                │                              │
                │  _find_cli()                 │
                │  shutil.which("claude")      │
                │                              │
                │  NOT FOUND → ClaudeCLI       │
                │              NotFound        │
                └──────────────┬──────────────┘
                               │ FOUND
                ┌──────────────┴──────────────┐
                │     3. BUILD COMMAND         │
                │                              │
                │  _build_command(prompt)       │
                │                              │
                │  Merges: client defaults     │
                │        + safety preset       │
                │        + per-call overrides   │
                │                              │
                │  Resolves session:            │
                │    resume > from_pr >        │
                │    continue_session > new    │
                │                              │
                │  Output:                     │
                │  ["claude", "-p", "...",     │
                │   "--output-format", "json", │
                │   "--model", "sonnet", ...]  │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │     4. RUN SUBPROCESS        │
                │                              │
                │  _run(command)                │
                │                              │
                │  subprocess.run(             │
                │    command,                  │
                │    capture_output=True,      │
                │    text=True,                │
                │    cwd=self.cwd              │
                │  )                           │
                │                              │
                │  ERROR → ClaudeCLIError      │
                └──────────────┬──────────────┘
                               │ SUCCESS
                ┌──────────────┴──────────────┐
                │     5. PARSE RESPONSE        │
                │                              │
                │  json.loads(stdout)           │
                │  ClaudeResponse.from_json()  │
                │                              │
                │  Maps JSON fields:           │
                │    result, cost, session_id, │
                │    usage, model_usage,       │
                │    permission_denials, etc.  │
                │                              │
                │  If json_schema was used:    │
                │    response.parsed = dict    │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │     6. POST-PROCESS          │
                │                              │
                │  Store session_id:           │
                │    self._last_session_id =   │
                │      response.session_id     │
                │                              │
                │  Check permission_denials:   │
                │    if warn_on_permission_    │
                │      denial → print warning  │
                │                              │
                │  Return ClaudeResponse       │
                └─────────────────────────────┘
```

---

## Data Flow: client.stream()

What happens when you call `client.stream("prompt", on_event=callback)`:

```
                  client.stream("Write a story", on_event=cb)
                               │
                ┌──────────────┴──────────────┐
                │  Steps 1-3 same as .ask()    │
                │  but output_format =         │
                │  "stream-json"               │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │     4. RUN WITH POPEN        │
                │                              │
                │  subprocess.Popen(           │
                │    command,                  │
                │    stdout=PIPE,              │
                │    text=True,                │
                │    cwd=self.cwd              │
                │  )                           │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │     5. STREAM LOOP           │
                │                              │
                │  for line in proc.stdout:    │
                │    event = json.loads(line)  │
                │    cb(event)  ◄── callback   │
                │                              │
                │    if event.type == "result":│
                │      final = event           │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │     6. RETURN                │
                │                              │
                │  ClaudeResponse.from_json(   │
                │    final                     │
                │  )                           │
                └─────────────────────────────┘
```

---

## Safety Presets: What Each Level Unlocks

```
    SAFE (default)            CAREFUL                    FULL
    ──────────────            ───────                    ────
    permission: plan          permission: acceptEdits    permission: auto
    tools: Read,Glob,Grep     tools: +Edit,Write         tools: ALL (default)
    max_turns: 1              max_turns: 3               max_turns: 10
    budget: $1                budget: $5                 budget: $20
    Bash: BLOCKED             Bash: BLOCKED              Bash: ALLOWED
    Agent: BLOCKED            Agent: BLOCKED             Agent: ALLOWED
    Edit/Write: BLOCKED       Edit/Write: ALLOWED        Edit/Write: ALLOWED

    ◄─── safer ──────────────────────────────────── more powerful ───►

    Can read code             Can read + edit code       Can do anything
    Can answer questions      Can refactor files         Can run commands
    Cannot change anything    Cannot run shell cmds      Can spawn subagents
                                                         Can search the web
```

---

## Session Flow

```
    ┌─────────────┐
    │  .ask()     │──── no resume flags ────► NEW SESSION
    │  call #1    │                           session_id = "aaa"
    └──────┬──────┘                           stored in _last_session_id
           │
    ┌──────┴──────┐
    │  .ask()     │──── continue_session ───► RESUME "aaa"
    │  call #2    │     =True                 session_id = "aaa" (same)
    └──────┬──────┘
           │
    ┌──────┴──────┐
    │  .ask()     │──── resume="xyz" ───────► RESUME "xyz"
    │  call #3    │                           session_id = "xyz"
    └──────┬──────┘                           _last_session_id = "xyz"
           │
    ┌──────┴──────┐
    │  .ask()     │──── continue_session ───► RESUME "xyz" (from call #3)
    │  call #4    │     =True, fork=True      + --fork-session
    └──────┬──────┘                           session_id = "new-fork-id"
           │                                  _last_session_id = "new-fork-id"
           │                                  "xyz" is UNTOUCHED
    ┌──────┴──────┐
    │  .ask()     │──── no flags ───────────► NEW SESSION (fresh)
    │  call #5    │                           session_id = "bbb"
    └─────────────┘
```

---

## Conversation Helper vs Direct Client

```
┌──────────────────────────────────────────────────────────────────┐
│                    DIRECT CLIENT USAGE                            │
│                                                                  │
│  client = Claude(model="sonnet")                                 │
│                                                                  │
│  r1 = client.ask("Hi")              → new session (aaa)         │
│  r2 = client.ask("Bye")             → new session (bbb)         │
│  r3 = client.ask("Again",                                       │
│         continue_session=True)       → resumes (bbb)            │
│                                                                  │
│  Each call is INDEPENDENT unless you manually continue.          │
│  Client only remembers the LAST session_id.                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    CONVERSATION USAGE                             │
│                                                                  │
│  conv = Conversation(client)                                     │
│                                                                  │
│  r1 = conv.say("Hi")                → new session (aaa)         │
│  r2 = conv.say("Bye")               → resumes (aaa) auto        │
│  r3 = conv.say("Again")             → resumes (aaa) auto        │
│                                                                  │
│  conv2 = conv.fork()                                             │
│  r4 = conv2.say("Different path")   → fork of (aaa) → new (ccc)│
│  r5 = conv2.say("Continue here")    → resumes (ccc) auto        │
│                                                                  │
│  Every .say() AUTOMATICALLY continues. Tracks cost, turns,       │
│  history. Can fork to branch.                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Subagent Architecture (handled by CLI, not SDK)

```
┌─────────────────────────────────────────────────────────────────┐
│  client.ask("Refactor auth module", safety="full")              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CLI PROCESS                           │
│                                                                 │
│  Main Claude instance receives the prompt                       │
│                                                                 │
│  Decides it needs help → spawns subagents via Agent tool:       │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │  Explore       │  │  General       │  │  Plan          │       │
│  │  subagent      │  │  subagent      │  │  subagent      │       │
│  │               │  │               │  │               │       │
│  │ "Find all     │  │ "Read and     │  │ "Design the   │       │
│  │  files that   │  │  analyze      │  │  refactoring  │       │
│  │  import auth" │  │  auth.py"     │  │  approach"    │       │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘       │
│          │                  │                  │               │
│          ▼                  ▼                  ▼               │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Main Claude combines results            │       │
│  │              and produces final response             │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
│  Also supports USER-DEFINED agents:                             │
│                                                                 │
│  --agents '{"reviewer": {...}, "security": {...}}'              │
│  --agent reviewer    (use as the main agent)                    │
│                                                                 │
│  Custom agents can also be spawned AS subagents by the          │
│  main agent, just like built-in Explore/Plan agents.            │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
                      Single JSON response
                  (includes ALL subagent costs)
                              │
                              ▼
                      ClaudeResponse
                      cost_usd = total
                      num_turns = total
                      model_usage = per-model breakdown
```

---

## What Gets Skipped (and Why)

These CLI flags are NOT in the SDK because they're interactive-only or deprecated:

```
SKIPPED FLAGS                  REASON
─────────────                  ──────
--chrome / --no-chrome         Browser extension, needs UI
--ide                          IDE connection, needs UI
--tmux                         Terminal multiplexer, needs terminal
--mcp-debug                    DEPRECATED → use --debug instead
--help                         CLI-only (not a runtime flag)
--version                      CLI-only (not a runtime flag)
--print                        ALWAYS used by SDK internally (every call uses -p)
```

Everything else (45 flags) is supported.
