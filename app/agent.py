"""Google ADK agent, wired to OpenRouter through LiteLlm. One shared agent,
one-shot sessions per call -- each call to ask() is a fresh turn with no
memory of the last, which is all the resolver needs."""

import uuid

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from app import config

_INSTRUCTION = (
    "You are blocker-bot, a terse engineering assistant embedded in a team chat room. "
    "You write short, direct messages (2-3 sentences max) as if posting in Slack/Discord. "
    "No markdown headers, no bullet lists, no sign-offs. Just the message body."
)

_model = LiteLlm(model=f"openrouter/{config.OPENROUTER_MODEL}", api_key=config.OPENROUTER_API_KEY)
_agent = LlmAgent(name="blocker_bot", model=_model, instruction=_INSTRUCTION)
_runner = InMemoryRunner(agent=_agent, app_name="blocker-bot")


async def ask(prompt: str) -> str:
    """Runs one isolated turn through the ADK agent and returns the reply text."""
    user_id = "blocker-bot-internal"
    session = await _runner.session_service.create_session(
        app_name="blocker-bot", user_id=user_id, session_id=str(uuid.uuid4())
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    reply = ""
    async for event in _runner.run_async(user_id=user_id, session_id=session.id, new_message=message):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    reply = part.text
    return reply.strip()
