"""Real ADK function tools. These are what the agent actually calls to find
out facts and take action -- it never gets a blocker description or an owner
name handed to it in a prompt. Each tool is bound to one task + transport via
closure so the model only has to supply the arguments that represent an
actual decision (what to say, who to mark as the blocker owner), not plumbing
it already knows from context.
"""

from app import systems, tasks
from app.transport import RoomTransport


def build_tools(task: tasks.Task, transport: RoomTransport) -> list:
    async def check_blocker_status() -> dict:
        """Check whether this task currently has a real blocker. Returns
        {"blocked": bool, "reason": str|None}. Always call this first --
        never assume a task is blocked."""
        return systems.check(task.component)

    async def get_component_owner() -> dict:
        """Look up who owns unblocking this task's component, CODEOWNERS-style.
        Returns {"owner": str} if someone is mapped, or {"owner": null} if no
        one is. Never invent an owner name that didn't come from this tool."""
        owner = tasks.owner_for(task.component)
        return {"owner": owner}

    async def post_message(text: str) -> str:
        """Post a message into the team room, as yourself."""
        await transport.send_message(task.room_id, text)
        return "posted"

    async def mark_blocked(owner: str) -> str:
        """Mark this task as blocked, pending a reply from the given owner.
        Pass the exact owner string from get_component_owner, or "unassigned"
        if it returned null."""
        task.status = tasks.TaskStatus.BLOCKED
        task.blocked_on = owner
        return f"task {task.id} marked blocked on {owner}"

    async def mark_done(summary: str) -> str:
        """Mark this task as complete, with a one-line summary of why."""
        task.status = tasks.TaskStatus.DONE
        task.blocked_on = None
        return f"task {task.id} marked done: {summary}"

    return [check_blocker_status, get_component_owner, post_message, mark_blocked, mark_done]
