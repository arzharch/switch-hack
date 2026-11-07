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
  real `LlmAgent` through an `InMemoryRunner` for every message it writes.
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

## What's real vs. mocked

| Piece | Status |
|---|---|
| Agent reasoning (kickoff message, blocker ping, completion summary) | **Real** — live calls to OpenRouter through Google ADK |
| Routing a blocker to the correct owner, and gating resume on that owner's reply | **Real** — this is the actual workflow logic in `app/blocker_resolver.py` |
| FastAPI backend | **Real** |
| Switch Agent Protocol client | **Real code**, written against the published protocol docs — untested against a live server (see below) |
| The task tracker (what tasks exist, who's assigned) | **Mocked** — `app/tasks.py`, stands in for Jira/Linear |
| The ownership map (which person owns which component) | **Mocked** — same file, stands in for an org chart / CODEOWNERS |
| Discord itself | **Not connected in this run** — swapped for `MockRoomTransport`, an in-process room that behaves like the real one (see `app/transport.py`) |

The mock boundary is intentional and documented, not hidden: swap
`TRANSPORT=mock` for `TRANSPORT=switch` in `.env` and nothing in
`blocker_resolver.py` changes — it only ever talks to the `RoomTransport`
interface.

## Project layout

```
app/
  config.py            env vars
  tasks.py              mocked task store + owner map (the demo's fake data)
  agent.py              Google ADK agent wired to OpenRouter
  transport.py           RoomTransport interface (abstract)
  mock_transport.py      in-process fake room, no network
  switch_transport.py    real Switch Agent Protocol client
  blocker_resolver.py     the actual workflow: route + gate + resume
  main.py                 FastAPI app
scripts/
  test_llm.py             smoke test for the ADK+OpenRouter wiring alone
  register_agent.py       one-time Switch agent registration
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
# Assign a task -- agent posts a kickoff message, finds the blocker,
# resolves the owner, and pages them by name.
curl -X POST localhost:8080/tasks/T-101/assign

# Watch what it posted into the room.
curl localhost:8080/rooms/eng-room/transcript

# The wrong person replying does nothing -- proves routing isn't "anyone unblocks it".
curl -X POST localhost:8080/rooms/eng-room/messages \
  -H "Content-Type: application/json" -d '{"sender":"sam","body":"hey"}'

# The actual owner replies -- agent resumes and closes the task itself.
curl -X POST localhost:8080/rooms/eng-room/messages \
  -H "Content-Type: application/json" -d '{"sender":"alice","body":"done, granted access"}'

curl localhost:8080/tasks/T-101   # status: done
```

Three seed tasks (`T-101`, `T-102`, `T-103`) each block on a **different**
owner (`alice`, `priya`, `sam`) to prove the routing is resolved per-task,
not hardcoded to one name.

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
```

The curl sequence above under "Run it" is the actual end-to-end test —
it was run against this exact code before writing this README (three
tasks, three different owners, one wrong-person reply correctly ignored,
one correct-owner reply correctly resuming and completing the task).
