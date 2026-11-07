"""Google ADK agent, wired to OpenRouter through LiteLlm, with real function
tools (see app/tools.py). A fresh LlmAgent + InMemoryRunner is built per call
because the tools are bound by closure to one task + transport -- that's the
cost of keeping tool functions simple (no args the model has to get right
just to name which task it's working on).

run_agentic_task() lets the model actually decide what to do: it can call
zero or more tools, in whatever order it judges, before producing a final
message. The caller gets back the full tool-call trace, not just text --
that trace is what blocker_resolver.py uses to confirm the model actually
grounded its claims in tool results, and what scripts/eval.py asserts against.
"""

import uuid
from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from app import config

_PERSONA = (
    "You are blocker-bot, an engineering agent embedded in a team chat room. "
    "You have tools to check real system status, look up real ownership data, "
    "post messages into the room, and update task state. Use them -- never state "
    "whether something is blocked, or who owns it, unless a tool just told you so. "
    "Messages you post into the room must be short and direct (2-3 sentences), "
    "no markdown, no bullet lists, no sign-off -- written like a Slack message."
)


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ToolResult:
    name: str
    response: dict


@dataclass
class AgentRun:
    final_text: str
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)

    def called(self, name: str) -> bool:
        return any(c.name == name for c in self.calls)

    def args_for(self, name: str) -> dict | None:
        for c in reversed(self.calls):
            if c.name == name:
                return c.args
        return None

    def result_for(self, name: str) -> dict | None:
        for r in reversed(self.results):
            if r.name == name:
                return r.response
        return None


async def run_agentic_task(prompt: str, tools: list) -> AgentRun:
    """Runs one agentic turn: the model may call any of `tools` any number of
    times (ADK's runner loop handles feeding results back and re-prompting)
    before settling on a final room message."""
    model = LiteLlm(model=f"openrouter/{config.OPENROUTER_MODEL}", api_key=config.OPENROUTER_API_KEY)
    agent = LlmAgent(name="blocker_bot", model=model, instruction=_PERSONA, tools=tools)
    runner = InMemoryRunner(agent=agent, app_name="blocker-bot")

    user_id = "blocker-bot-internal"
    session = await runner.session_service.create_session(
        app_name="blocker-bot", user_id=user_id, session_id=str(uuid.uuid4())
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    run = AgentRun(final_text="")
    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=message):
        for fc in event.get_function_calls():
            run.calls.append(ToolCall(name=fc.name, args=dict(fc.args or {})))
        for fr in event.get_function_responses():
            run.results.append(ToolResult(name=fr.name, response=dict(fr.response or {})))
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    run.final_text = part.text

    run.final_text = run.final_text.strip()
    return run
