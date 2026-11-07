"""Eval suite for the agentic blocker-routing workflow.

This does NOT grade the prose the LLM writes. It grades the things that
actually matter for this workflow to be trustworthy:

  1. Did it page a human only when a tool told it there's a real blocker,
     and skip paging when a tool told it there isn't? (the paging decision
     is now the model's, not a hardcoded branch -- see T-104 below)
  2. Did it call the right tools, in the right order, with arguments that
     are actually grounded in a previous tool's result -- not invented?
  3. Does the deterministic gate (only the paged owner's reply unblocks
     the task) still hold now that paging/resuming goes through tool calls?
  4. When the data it has is incomplete (no owner mapped), does it degrade
     gracefully instead of hallucinating a name?

Run: python scripts/eval.py
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import tasks
from app.blocker_resolver import BlockerResolver
from app.mock_transport import MockRoomTransport
from app.transport import InboundMessage


@dataclass
class Check:
    description: str
    passed: bool
    detail: str = ""


def check(description: str, condition: bool, detail: str = "") -> Check:
    return Check(description, bool(condition), detail)


async def scenario_real_blocker(resolver: BlockerResolver) -> list[Check]:
    """T-101 has a real blocker (per app/systems.py) owned by alice. The
    agent should check status, resolve the owner via a tool call, page
    alice by name, and mark the task blocked on alice -- not on some other
    name it invented."""
    task = await resolver.start_task("T-101")
    run = resolver.runs["T-101"][-1]

    results = [
        check("called check_blocker_status before deciding anything", run.called("check_blocker_status")),
        check("called get_component_owner (owner resolved by the model, not handed to it)", run.called("get_component_owner")),
        check("mark_blocked was called at all", run.called("mark_blocked")),
    ]
    mark_args = run.args_for("mark_blocked") or {}
    results.append(check(
        "mark_blocked's owner arg matches get_component_owner's actual result (alice)",
        mark_args.get("owner") == "alice",
        f"mark_blocked called with owner={mark_args.get('owner')!r}",
    ))
    post_args = run.args_for("post_message") or {}
    results.append(check(
        "the posted message actually names alice (grounded, not generic)",
        "alice" in post_args.get("text", "").lower(),
        f"message was: {post_args.get('text', '')!r}",
    ))
    results.append(check(
        "task ended up BLOCKED with blocked_on=alice",
        task.status == tasks.TaskStatus.BLOCKED and task.blocked_on == "alice",
        f"status={task.status}, blocked_on={task.blocked_on}",
    ))
    return results


async def scenario_wrong_person_ignored(resolver: BlockerResolver, transport: MockRoomTransport) -> list[Check]:
    """sam replying to a task blocked on alice should trigger nothing at
    all -- no new agent run, no state change. This checks the deterministic
    gate, not the LLM."""
    runs_before = len(resolver.runs.get("T-101", []))

    await transport.inbound("eng-room", "sam", "hey, just checking in")

    task_after = tasks.get_task("T-101")
    runs_after = len(resolver.runs.get("T-101", []))

    return [
        check("wrong-person reply triggered no new agent run", runs_after == runs_before, f"{runs_before} -> {runs_after}"),
        check("task is still BLOCKED on alice, untouched", task_after.status == tasks.TaskStatus.BLOCKED and task_after.blocked_on == "alice"),
        check("transcript still only has sam's message appended, no bot reply to it", transport.get_transcript("eng-room")[-1] == {"sender": "sam", "body": "hey, just checking in"}),
    ]


async def scenario_correct_person_resumes(resolver: BlockerResolver, transport: MockRoomTransport) -> list[Check]:
    """alice (the actual owner) replying should resume and close T-101."""
    await transport.inbound("eng-room", "alice", "done, granted access")
    task = tasks.get_task("T-101")
    run = resolver.runs["T-101"][-1]

    results = [
        check("alice's reply triggered a new agent run", run is not None),
        check("called mark_done to close it out", run.called("mark_done")),
    ]
    post_args = run.args_for("post_message") or {}
    results.append(check(
        "the closing message names alice",
        "alice" in post_args.get("text", "").lower(),
        f"message was: {post_args.get('text', '')!r}",
    ))
    results.append(check(
        "task is DONE",
        task.status == tasks.TaskStatus.DONE,
        f"status={task.status}",
    ))
    return results


async def scenario_no_blocker_skips_paging(resolver: BlockerResolver) -> list[Check]:
    """T-104 has no real blocker (systems.py says blocked=False). The agent
    should check, see that, and complete it directly -- paging nobody. This
    is the scenario that actually proves paging is a decision and not a
    hardcoded branch: if this fails the same way T-101 "succeeds", paging is
    still unconditional."""
    task = await resolver.start_task("T-104")
    run = resolver.runs["T-104"][-1]

    return [
        check("called check_blocker_status", run.called("check_blocker_status")),
        check("did NOT call get_component_owner (nothing to resolve)", not run.called("get_component_owner")),
        check("did NOT call mark_blocked (nobody should be paged)", not run.called("mark_blocked")),
        check("called mark_done", run.called("mark_done")),
        check(
            "task completed DONE without ever being blocked_on anyone",
            task.status == tasks.TaskStatus.DONE and task.blocked_on is None,
            f"status={task.status}, blocked_on={task.blocked_on}",
        ),
    ]


async def scenario_missing_owner_handled(resolver: BlockerResolver) -> list[Check]:
    """T-105 is blocked (per systems.py) but its component has no entry in
    OWNER_MAP. The agent should notice get_component_owner returned no
    owner and degrade to "unassigned" -- not invent one of the other three
    real names just because it needs *some* owner to call mark_blocked with."""
    task = await resolver.start_task("T-105")
    run = resolver.runs["T-105"][-1]

    owner_result = run.result_for("get_component_owner") or {}
    mark_args = run.args_for("mark_blocked") or {}
    post_args = run.args_for("post_message") or {}
    message = post_args.get("text", "").lower()

    return [
        check("called check_blocker_status", run.called("check_blocker_status")),
        check("called get_component_owner", run.called("get_component_owner")),
        check("get_component_owner's actual result was owner=None", owner_result.get("owner") is None, f"result was {owner_result!r}"),
        check(
            "mark_blocked was NOT called with a hallucinated real owner name",
            mark_args.get("owner") not in ("alice", "priya", "sam"),
            f"mark_blocked called with owner={mark_args.get('owner')!r}",
        ),
        check(
            "the posted message doesn't name a real owner that wasn't actually resolved",
            not any(name in message for name in ("alice", "priya", "sam")),
            f"message was: {post_args.get('text', '')!r}",
        ),
        check("task ended up BLOCKED (component really is blocked)", task.status == tasks.TaskStatus.BLOCKED, f"status={task.status}"),
    ]


async def main() -> int:
    tasks.reset()
    transport = MockRoomTransport()
    resolver = BlockerResolver(transport)
    await transport.start(resolver.handle_inbound)

    scenarios = [
        ("T-101: real blocker -> correct owner paged", scenario_real_blocker(resolver)),
    ]
    all_checks: list[tuple[str, list[Check]]] = []
    for name, coro in scenarios:
        all_checks.append((name, await coro))

    all_checks.append(("T-101: wrong person's reply is ignored", await scenario_wrong_person_ignored(resolver, transport)))
    all_checks.append(("T-101: correct owner's reply resumes + completes", await scenario_correct_person_resumes(resolver, transport)))
    all_checks.append(("T-104: no real blocker -> completes without paging anyone", await scenario_no_blocker_skips_paging(resolver)))
    all_checks.append(("T-105: blocked, but no owner mapped -> degrades, doesn't hallucinate", await scenario_missing_owner_handled(resolver)))

    total = 0
    passed = 0
    for name, checks in all_checks:
        print(f"\n== {name} ==")
        for c in checks:
            total += 1
            mark = "PASS" if c.passed else "FAIL"
            passed += 1 if c.passed else 0
            line = f"  [{mark}] {c.description}"
            if c.detail and not c.passed:
                line += f"\n         -> {c.detail}"
            print(line)

    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
