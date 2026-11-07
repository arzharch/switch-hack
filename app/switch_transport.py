"""Real transport, built against Switch's documented Agent Protocol
(docs.switchagents.ai/switch-rooms/internals/agent-protocol.md and
agent-connection.md). Not exercised by the test suite -- that needs a live
Switch server with Discord connected -- but it talks the real wire protocol:

  * registration is a one-time step done by scripts/register_agent.py
  * outbound: POST /agents/{agent_id}/message  (simple REST, no socket needed)
  * inbound:  GET  /agents/{agent_id}/connection/ws  (WebSocket, ping/pong
              keepalive every ~2s, reconnect-and-resume on drop)

The exact nesting of some WebSocket frame fields isn't published in full, so
this logs every raw frame at startup -- check the console the first time you
point it at a real server and adjust `_extract_message` if a field name
doesn't match.
"""

import asyncio
import json
import uuid
from pathlib import Path

import httpx
import websockets

from app import config
from app.transport import InboundMessage, OnMessage, RoomTransport

CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / ".agent_credentials.json"


class SwitchRoomTransport(RoomTransport):
    def __init__(self) -> None:
        if not CREDENTIALS_FILE.exists():
            raise RuntimeError("No agent credentials found. Run scripts/register_agent.py first.")
        creds = json.loads(CREDENTIALS_FILE.read_text())
        self.agent_id = creds["id"]
        self.api_key = creds["api_key"]
        self.room_id = config.SWITCH_ROOM_ID
        if not self.room_id:
            raise RuntimeError("SWITCH_ROOM_ID is not set in .env.")

        self._connection_id = str(uuid.uuid4())
        self._on_message: OnMessage | None = None
        self._task: asyncio.Task | None = None
        self._stop = False

    async def send_message(self, room_id: str, content: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{config.SWITCH_BASE_URL}/agents/{self.agent_id}/message",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"room_id": room_id, "content": content},
                timeout=30,
            )
            resp.raise_for_status()

    async def start(self, on_message: OnMessage) -> None:
        self._on_message = on_message
        self._stop = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        ws_url = (
            f"{config.SWITCH_WS_BASE_URL}/agents/{self.agent_id}/connection/ws"
            f"?connection_id={self._connection_id}&rooms={self.room_id}"
        )
        while not self._stop:
            try:
                async with websockets.connect(
                    ws_url, additional_headers={"Authorization": f"Bearer {self.api_key}"}
                ) as ws:
                    print(f"[switch] connected, connection_id={self._connection_id}")
                    cursor = 0
                    async for raw in ws:
                        frame = json.loads(raw)
                        print("[switch] frame:", frame)  # remove once field names are confirmed live

                        if frame.get("type") == "ping":
                            cursor = frame.get("cursor", cursor)
                            await ws.send(json.dumps({"type": "pong", "cursor": cursor}))
                            continue

                        if frame.get("type") == "connection_state":
                            cursor = frame.get("cursor", cursor)
                            continue

                        inbound = self._extract_message(frame)
                        if inbound and self._on_message:
                            await self._on_message(inbound)
            except (websockets.exceptions.ConnectionClosed, OSError) as exc:
                if self._stop:
                    break
                print(f"[switch] connection dropped ({exc}), reconnecting in 2s")
                await asyncio.sleep(2)

    def _extract_message(self, frame: dict) -> InboundMessage | None:
        """Best-effort parse of a `message` event. The protocol doc gives the
        field names (addressed, sender, body, room_id) but not the exact
        top-level nesting, so this checks both the flat and payload-nested
        shapes seen in similar event-sourced APIs."""
        if frame.get("type") != "message":
            return None
        payload = frame.get("payload", frame)
        if not payload.get("addressed", True):
            return None
        return InboundMessage(
            room_id=payload.get("room_id", self.room_id),
            sender=payload.get("sender_name") or payload.get("sender", "unknown"),
            body=payload.get("body", ""),
            addressed=True,
        )
