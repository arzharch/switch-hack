"""The actual workflow: pick up a task, generate a kickoff message, detect
the blocker, resolve it to the ONE person who owns that component, page them
by name, and only resume when that specific person replies -- not just
whoever talks in the room next. That routing-and-gating step is the part
Switch doesn't give you for free; everything else here is plumbing."""

from app import agent, tasks
from app.transport import InboundMessage, RoomTransport


class BlockerResolver:
    def __init__(self, transport: RoomTransport) -> None:
        self.transport = transport

    async def start_task(self, task_id: str) -> tasks.Task:
        task = tasks.get_task(task_id)
        if task.status != tasks.TaskStatus.OPEN:
            return task

        task.status = tasks.TaskStatus.IN_PROGRESS

        kickoff = await agent.ask(
            f"You're picking up task {task.id}: \"{task.title}\". "
            f"Post a one-line message to the room announcing you're starting it."
        )
        await self.transport.send_message(task.room_id, kickoff)
        task.log.append(f"started: {kickoff}")

        owner = tasks.owner_for(task.component)
        blocker_msg = await agent.ask(
            f"While working task {task.id} (\"{task.title}\") you discovered you're blocked: "
            f"{task.blocker}. The person who owns this is @{owner}. "
            f"Write a short, direct message addressed to @{owner} explaining exactly what you "
            f"need from them to unblock task {task.id}."
        )
        await self.transport.send_message(task.room_id, blocker_msg)
        task.log.append(f"blocked, paged @{owner}: {blocker_msg}")

        task.status = tasks.TaskStatus.BLOCKED
        task.blocked_on = owner
        return task

    async def handle_inbound(self, msg: InboundMessage) -> None:
        """Only resumes a task if the reply comes from the specific person
        that task is blocked on -- anyone else talking in the room is just
        chatter and is ignored. This is the routing guarantee, not the LLM's
        judgment call."""
        blocked_tasks = [
            t for t in tasks.list_tasks()
            if t.status == tasks.TaskStatus.BLOCKED and t.room_id == msg.room_id and t.blocked_on == msg.sender
        ]
        if not blocked_tasks:
            return

        for task in blocked_tasks:
            await self._resume_task(task, msg)

    async def _resume_task(self, task: tasks.Task, reply: InboundMessage) -> None:
        summary = await agent.ask(
            f"Task {task.id} (\"{task.title}\") was blocked on: {task.blocker}. "
            f"@{reply.sender}, the owner, just replied: \"{reply.body}\". "
            f"Write a short message thanking them by name, confirming you're resuming "
            f"task {task.id}, and marking it done."
        )
        await self.transport.send_message(task.room_id, summary)
        task.log.append(f"unblocked by @{reply.sender}, completed: {summary}")
        task.status = tasks.TaskStatus.DONE
        task.blocked_on = None
