"""
Mocked stand-in for a real ticket tracker (Jira/Linear) and a real org-chart /
CODEOWNERS lookup. Everything in this file is the part of the demo that's
faked -- swap it for real API calls later without touching blocker_resolver.py.
"""

from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass
class Task:
    id: str
    title: str
    assignee: str
    component: str          # which part of the system the blocker belongs to
    blocker: str             # what's actually blocking it, in plain English
    room_id: str
    status: TaskStatus = TaskStatus.OPEN
    blocked_on: str | None = None   # owner handle currently paged
    log: list[str] = field(default_factory=list)


# component -> the one person who actually owns unblocking it.
# This is the part that proves routing isn't hardcoded: two different
# blockers resolve to two different people automatically.
OWNER_MAP: dict[str, str] = {
    "infra-access": "alice",
    "design-review": "priya",
    "db-admin": "sam",
}

TASKS: dict[str, Task] = {
    "T-101": Task(
        id="T-101",
        title="Fix payment webhook retry bug",
        assignee="you",
        component="infra-access",
        blocker="needs staging infra access to reproduce the webhook retries",
        room_id="eng-room",
    ),
    "T-102": Task(
        id="T-102",
        title="Add CSV export to reports page",
        assignee="you",
        component="design-review",
        blocker="needs sign-off on the export column layout before shipping",
        room_id="eng-room",
    ),
    "T-103": Task(
        id="T-103",
        title="Migrate user table index",
        assignee="you",
        component="db-admin",
        blocker="needs a production migration window approved",
        room_id="eng-room",
    ),
}


def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise KeyError(f"no such task: {task_id}")
    return TASKS[task_id]


def owner_for(component: str) -> str:
    if component not in OWNER_MAP:
        raise KeyError(f"no owner mapped for component: {component}")
    return OWNER_MAP[component]


def list_tasks() -> list[Task]:
    return list(TASKS.values())
