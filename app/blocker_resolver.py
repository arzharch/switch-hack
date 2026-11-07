"""The actual workflow: pick up a task, let the agent itself check (via a
real tool call) whether it's blocked, and if so let it resolve the owner
(via another real tool call) and page them by name -- then only resume when
that specific person replies, not just whoever talks in the room next.

The paging decision and the owner name are no longer computed in this file
and handed to the model as a fact -- they're the model's own tool calls,
captured in the returned AgentRun so they can be audited (see
scripts/eval.py). The one thing that stays deterministic in Python, by
design, is *gating*: whether a reply counts as unblocking a task is a plain
sender-match, not an LLM judgment call, because getting that wrong is the
one failure mode that can't be caught by reading the message it posts.
"""

from app import agent, tasks
from app.tools import build_tools
from app.transport import InboundMessage, RoomTransport


class BlockerResolver:
    def __init__(self, transport: RoomTransport) -> None:
        self.transport = transport
        # Every AgentRun this resolver has produced, keyed by task id -- lets
        # scripts/eval.py (and anyone debugging a demo run) inspect the real
        # tool-call trace instead of re-parsing log strings.
        self.runs: dict[str, list[agent.AgentRun]] = {}

    async def start_task(self, task_id: str) -> tasks.Task:
        task = tasks.get_task(task_id)
        if task.status != tasks.TaskStatus.OPEN:
            return task

        task.status = tasks.TaskStatus.IN_PROGRESS
        tools = build_tools(task, self.transport)
        prompt = (
            f"You're picking up task {task.id}: \"{task.title}\". Find out whether it's "
            f"actually blocked before assuming anything.\n\n"
            f"Call check_blocker_status first.\n"
            f"- If it reports blocked=false: post a short message announcing the task is "
            f"done, then call mark_done. Do not call get_component_owner or mark_blocked.\n"
            f"- If it reports blocked=true: call get_component_owner. If it returns a real "
            f"owner, post a message addressed to that exact person (use the reason the "
            f"status check gave you) explaining what you need from them, then call "
            f"mark_blocked with that same owner name. If it returns no owner, say in your "
            f"message that you're blocked but no owner is mapped for this component yet, "
            f"and call mark_blocked with \"unassigned\"."
        )
        run = await agent.run_agentic_task(prompt, tools)
        self.runs.setdefault(task.id, []).append(run)
        task.log.append(f"start_task: tools={[c.name for c in run.calls]!r} message={run.final_text!r}")
        return task

    async def handle_inbound(self, msg: InboundMessage) -> None:
        """Only resumes a task if the reply comes from the specific person
        that task is blocked on -- anyone else talking in the room is just
        chatter and is ignored. This is a plain string comparison, not the
        LLM's judgment call."""
        blocked_tasks = [
            t for t in tasks.list_tasks()
            if t.status == tasks.TaskStatus.BLOCKED and t.room_id == msg.room_id and t.blocked_on == msg.sender
        ]
        if not blocked_tasks:
            return

        for task in blocked_tasks:
            await self._resume_task(task, msg)

    async def _resume_task(self, task: tasks.Task, reply: InboundMessage) -> None:
        tools = build_tools(task, self.transport)
        prompt = (
            f"Task {task.id} (\"{task.title}\") was blocked, waiting on @{reply.sender}. "
            f"They just replied: \"{reply.body}\". Post a short message thanking them by "
            f"name and confirming you're resuming task {task.id}, then call mark_done with "
            f"a one-line summary of what unblocked it."
        )
        run = await agent.run_agentic_task(prompt, tools)
        self.runs.setdefault(task.id, []).append(run)
        task.log.append(f"resume ({reply.sender}): tools={[c.name for c in run.calls]!r} message={run.final_text!r}")
