"""Transport abstraction: anything that can deliver a message into a room and
notify us when one comes back. blocker_resolver.py only talks to this
interface, so swapping MockRoomTransport for the real SwitchRoomTransport is
a one-line change (TRANSPORT=mock|switch in .env)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class InboundMessage:
    room_id: str
    sender: str
    body: str
    addressed: bool = True


OnMessage = Callable[[InboundMessage], Awaitable[None]]


class RoomTransport(ABC):
    @abstractmethod
    async def send_message(self, room_id: str, content: str) -> None:
        """Post a message into a room, as the agent."""

    @abstractmethod
    async def start(self, on_message: OnMessage) -> None:
        """Begin listening for inbound messages, calling on_message for each."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and release any connection."""
