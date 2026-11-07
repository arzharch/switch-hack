"""In-process stand-in for a real chat platform. Lets the whole agent loop
run and be tested with no Discord, no Switch server, and no network calls
other than the real OpenRouter ones. Drive it by calling `inbound()` the way
the FastAPI demo endpoints do -- that's the only thing a real transport would
otherwise deliver from the wire."""

from app.transport import InboundMessage, OnMessage, RoomTransport


class MockRoomTransport(RoomTransport):
    def __init__(self) -> None:
        self.transcript: dict[str, list[dict]] = {}
        self._on_message: OnMessage | None = None

    async def start(self, on_message: OnMessage) -> None:
        self._on_message = on_message

    async def stop(self) -> None:
        self._on_message = None

    async def send_message(self, room_id: str, content: str) -> None:
        self.transcript.setdefault(room_id, []).append({"sender": "blocker-bot", "body": content})

    async def inbound(self, room_id: str, sender: str, body: str) -> None:
        """Simulates a human (or another agent) posting into the room."""
        self.transcript.setdefault(room_id, []).append({"sender": sender, "body": body})
        if self._on_message:
            await self._on_message(InboundMessage(room_id=room_id, sender=sender, body=body, addressed=True))

    def get_transcript(self, room_id: str) -> list[dict]:
        return self.transcript.get(room_id, [])
