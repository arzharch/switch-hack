from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import config, tasks
from app.blocker_resolver import BlockerResolver
from app.mock_transport import MockRoomTransport

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.TRANSPORT == "switch":
        from app.switch_transport import SwitchRoomTransport

        transport = SwitchRoomTransport()
    else:
        transport = MockRoomTransport()

    resolver = BlockerResolver(transport)
    await transport.start(resolver.handle_inbound)

    state["transport"] = transport
    state["resolver"] = resolver
    yield

    await transport.stop()


app = FastAPI(title="blocker-bot", lifespan=lifespan)


class InboundMessageIn(BaseModel):
    sender: str
    body: str


@app.get("/health")
async def health():
    return {"ok": True, "transport": config.TRANSPORT, "model": config.OPENROUTER_MODEL}


@app.get("/tasks")
async def list_tasks():
    return [_task_dict(t) for t in tasks.list_tasks()]


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        return _task_dict(tasks.get_task(task_id))
    except KeyError:
        raise HTTPException(404, f"no such task: {task_id}")


@app.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str):
    try:
        task = await state["resolver"].start_task(task_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return _task_dict(task)


@app.post("/rooms/{room_id}/messages")
async def post_room_message(room_id: str, msg: InboundMessageIn):
    """Simulates a human (e.g. the paged owner) replying in the room."""
    transport = state["transport"]
    if not hasattr(transport, "inbound"):
        raise HTTPException(400, "current transport doesn't support simulated inbound messages")
    await transport.inbound(room_id, msg.sender, msg.body)
    return {"ok": True}


@app.get("/rooms/{room_id}/transcript")
async def get_transcript(room_id: str):
    transport = state["transport"]
    if not hasattr(transport, "get_transcript"):
        raise HTTPException(400, "current transport doesn't expose a transcript")
    return transport.get_transcript(room_id)


def _task_dict(task: tasks.Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "blocked_on": task.blocked_on,
        "component": task.component,
        "room_id": task.room_id,
        "log": task.log,
    }
