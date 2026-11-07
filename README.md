# blocker-bot

Hackathon entry for **Flip the Switch** (Track 1: Best Business Workflow).

An agent picks up a task assigned to you, works it, and when it hits a
blocker, **automatically figures out which specific person owns that
blocker and pages them by name** — instead of dumping "I'm blocked" into a
channel and waiting for someone to notice. It only resumes the task when
*that* person replies; anyone else talking in the room is ignored. When
they reply, it resumes and closes the loop itself.

That routing-and-gating step is the part a generic "agent-in-chat" setup
(including Switch's own `switch-buddy` onboarding flow) doesn't give you —
it's built here as real logic, not a hardcoded demo path.

## Stack

- **Google ADK** (`google-adk`) — the agent framework. `app/agent.py` runs a
  real `LlmAgent` through an `InMemoryRunner`, with real function-calling
  tools attached (`app/tools.py`) — not just a wrapper around a chat
  completion. The model decides whether to call each tool, in what order,
  and has to carry a tool's result forward correctly into its next call;
  nothing is handed to it pre-resolved.
- **OpenRouter** as the LLM provider, via ADK's `LiteLlm` wrapper
  (`openrouter/<model>`). Default model: `openai/gpt-4o-mini` — cheap and
  reliable. (Tried `google/gemini-2.5-flash-lite` first; it's cheaper but
  was rate-limited on OpenRouter's shared free pool during testing.)
- **FastAPI** backend orchestrating everything.
- **Switch Agent Protocol** — a real client (`app/switch_transport.py`)
  built against the documented protocol (register → WebSocket for
  inbound, REST for outbound). Not exercised in this repo's test run
  because that needs a live Switch server with Discord connected, but it's
  not a stub — see "What's real vs. mocked" below.

> **Gotcha if you're setting this up fresh:** `litellm` eagerly imports the
> `mcp` package the moment you pass `tools=` to a completion call, even
> though no MCP server is involved — if it's not installed you'll get a
> confusing `APIConnectionError: ... No module named 'mcp'` that looks like
> an OpenRouter failure. It's in `requirements.txt` now; if you hit this
> anyway, `pip install mcp`.

## The agent's actual decision loop

Earlier versions of this demo had Python decide "this task is blocked, the
owner is X" and just asked the LLM to phrase a sentence about it. That's not
an agent making a decision — it's a template with extra latency. The real
version gives the model tools and makes it use them:

- `check_blocker_status()` — is there actually a blocker right now?
- `get_component_owner()` — who owns resolving it, if anyone's mapped?
- `post_message(text)` — post into the room, as itself
- `mark_blocked(owner)` / `mark_done(summary)` — the actual state transition

The model has to call `check_blocker_status` before it can know whether to
page anyone, and if it decides to page someone, the owner name it uses has
to come from `get_component_owner`'s actual return value — there's no
owner name available to it any other way. `scripts/eval.py` asserts on that
tool-call trace directly (see below), not just on the prose it writes.

The one thing that's still deterministic Python, on purpose: whether a
reply unblocks a task is a plain `sender == blocked_on` check in
`blocker_resolver.handle_inbound`, not an LLM judgment call. That's the one
failure mode ("resumed because the wrong person said something") that
can't be caught by reading the message the agent posts, so it isn't left
to the model.

## What's real vs. mocked

| Piece | Status |
|---|---|
| Agent tool-calling (deciding whether to page, resolving the owner, posting, closing out) | **Real** — live OpenRouter calls through Google ADK, with real function tools (`app/tools.py`), not hardcoded branches |
| Routing a blocker to the correct owner | **Real decision** — the model calls `get_component_owner` itself; Python never resolves it for them |
| Gating resume on the correct owner's reply | **Real, deterministic** — a sender-match in `blocker_resolver.py`, intentionally not left to the LLM |
| FastAPI backend | **Real** |
| Switch Agent Protocol client | **Real code**, written against the published protocol docs — untested against a live server (see below) |
| The task tracker (what tasks exist, who's assigned) | **Mocked** — `app/tasks.py`, stands in for Jira/Linear |
| The "is it blocked right now" status check | **Mocked data, real decision** — `app/systems.py` stands in for an infra/CI API; the agent still has to call it and act on the result instead of being told the answer |
| The ownership map (which person owns which component) | **Mocked data, real lookup** — `app/tasks.py`, stands in for CODEOWNERS/an org chart; intentionally missing an entry for one component so the "no owner mapped" path is real, not hypothetical |
| Discord itself | **Not connected in this run** — swapped for `MockRoomTransport`, an in-process room that behaves like the real one (see `app/transport.py`) |

The mock boundary is intentional and documented, not hidden: swap
`TRANSPORT=mock` for `TRANSPORT=switch` in `.env` and nothing in
`blocker_resolver.py` or `tools.py` changes — they only ever talk to the
`RoomTransport` interface and the mocked data sources, respectively.

## Project layout

```
app/
  config.py            env vars
  tasks.py              mocked task store + owner map (the demo's fake data)
  systems.py             mocked "is it actually blocked" status source
  tools.py                real ADK function tools, bound to a task + transport
  agent.py                Google ADK agent + tool-call loop, wired to OpenRouter
  transport.py            RoomTransport interface (abstract)
  mock_transport.py       in-process fake room, no network
  switch_transport.py     real Switch Agent Protocol client
  blocker_resolver.py      the actual workflow: route + gate + resume
  main.py                  FastAPI app
scripts/
  test_llm.py              smoke test for the ADK+OpenRouter wiring alone
  eval.py                   eval suite -- asserts on tool-call traces and
                            end states across 5 scenarios, not just prose
  register_agent.py        one-time Switch agent registration
```

## Run it (no Discord needed)

```bash
python -m venv .venv
.venv/Scripts/activate        # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env           # then paste in your OPENROUTER_API_KEY
uvicorn app.main:app --port 8080
```

Drive the demo with curl (or Postman):

```bash
# Assign a task -- agent calls a tool to check if it's actually blocked,
# calls another tool to resolve the owner, and pages them by name.
curl -X POST localhost:8080/tasks/T-101/assign

# Watch what it posted into the room, and which tools it called to get there.
curl localhost:8080/rooms/eng-room/transcript
curl localhost:8080/tasks/T-101   # "log" field shows the tool-call trace

# The wrong person replying does nothing -- proves routing isn't "anyone unblocks it".
curl -X POST localhost:8080/rooms/eng-room/messages \
  -H "Content-Type: application/json" -d '{"sender":"sam","body":"hey"}'

# The actual owner replies -- agent resumes and closes the task itself.
curl -X POST localhost:8080/rooms/eng-room/messages \
  -H "Content-Type: application/json" -d '{"sender":"alice","body":"done, granted access"}'

curl localhost:8080/tasks/T-101   # status: done

# T-104 has no real blocker -- the agent should check, see that, and
# complete it directly without paging anyone.
curl -X POST localhost:8080/tasks/T-104/assign
curl localhost:8080/tasks/T-104   # status: done, blocked_on: null, no owner tool called

# T-105 is blocked but its component has no owner mapped -- the agent
# should notice and degrade to "unassigned" instead of naming alice/priya/sam.
curl -X POST localhost:8080/tasks/T-105/assign
curl localhost:8080/tasks/T-105   # blocked_on: "unassigned"
```

Five seed tasks exercise the different branches the agent actually has to
choose between: `T-101`/`T-102`/`T-103` each block on a **different** real
owner (`alice`, `priya`, `sam`), `T-104` has no real blocker at all, and
`T-105` is blocked with no owner mapped. `scripts/eval.py` runs all of this
automatically and asserts on it -- see Testing below.

## Connecting it to a real Switch server + Discord

1. Stand up Switch (Switch Console → "On this computer" is fastest, or
   self-host per `docs.switchagents.ai/switch-rooms/deploy/self-host.md`).
2. Connect Discord: create a bot in the Discord Developer Portal, enable
   the Message Content + Server Members intents, invite it with the
   `bot` + `applications.commands` scopes, then connect it in Switch
   Console under Messaging apps using the bot token + guild ID. Post one
   message in the target channel so Switch adopts it as a room.
3. Get a registration token from your Switch admin, set
   `SWITCH_REGISTRATION_TOKEN` in `.env`, run `python scripts/register_agent.py`.
4. Invite the newly-registered agent into the room from Switch Console,
   copy the room id into `SWITCH_ROOM_ID` in `.env`.
5. Set `TRANSPORT=switch` in `.env` and restart the app.

`app/switch_transport.py` logs every raw WebSocket frame on first connect —
the protocol docs give field names but not the full JSON nesting, so check
that log against `_extract_message()` if inbound messages aren't parsed
on the first try.

## Testing

```bash
python scripts/test_llm.py          # confirms ADK -> LiteLlm -> OpenRouter works at all
python scripts/eval.py              # the real eval suite, against live OpenRouter calls
```

`scripts/eval.py` doesn't grade the prose the model writes -- it grades
the tool-call trace and the resulting task state, across 5 scenarios:

1. A real blocker -> the agent checks status, resolves the owner via a
   tool call, and pages that exact person (not a name it invented).
2. The wrong person replying -> triggers no new agent run at all.
3. The actual owner replying -> resumes and closes the task.
4. No real blocker (`T-104`) -> the agent completes it directly and never
   calls the owner-lookup or paging tools. This is the scenario that
   actually proves paging is a decision: if it always paged regardless,
   this is where it would show up.
5. A real blocker with no owner mapped (`T-105`) -> the agent notices and
   marks it `"unassigned"` instead of naming one of the three real owners
   it knows about from the other tasks.

Last run: 24/24 checks passed, three runs in a row (LLM tool selection
isn't fully deterministic, so it was run more than once before trusting it).
