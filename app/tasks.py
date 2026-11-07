"""Mocked stand-in for a real ticket tracker (Jira/Linear) and a real org-chart /
CODEOWNERS lookup. Everything in this file is the part of the demo that's
faked -- swap it for real API calls later without touching blocker_resolver.py
or tools.py, since both only ever call get_task()/owner_for() by name.
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
    room_id: str
    status: TaskStatus = TaskStatus.OPEN
    blocked_on: str | None = None   # owner handle currently paged
    log: list[str] = field(default_factory=list)


# component -> the one person who actually owns unblocking it.
# "legacy-report-export" is deliberately absent, to prove the agent handles a
# missing owner instead of inventing a name.
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
        room_id="eng-room",
    ),
    "T-102": Task(
        id="T-102",
        title="Add CSV export to reports page",
        assignee="you",
        component="design-review",
        room_id="eng-room",
    ),
    "T-103": Task(
        id="T-103",
        title="Migrate user table index",
        assignee="you",
        component="db-admin",
        room_id="eng-room",
    ),
    "T-104": Task(
        id="T-104",
        title="Rotate log retention to 30 days",
        assignee="you",
        component="logging-pipeline",
        room_id="eng-room",
    ),
    "T-105": Task(
        id="T-105",
        title="Re-enable legacy CSV report export",
        assignee="you",
        component="legacy-report-export",
        room_id="eng-room",
    ),
}


def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise KeyError(f"no such task: {task_id}")
    return TASKS[task_id]


def owner_for(component: str) -> str | None:
    return OWNER_MAP.get(component)


def list_tasks() -> list[Task]:
    return list(TASKS.values())


def reset() -> None:
    """Restores all seed tasks to OPEN. Used by the eval script so scenarios
    don't leak state into each other between runs."""
    for task in TASKS.values():
        task.status = TaskStatus.OPEN
        task.blocked_on = None
        task.log.clear()
