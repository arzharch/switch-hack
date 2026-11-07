"""One-off smoke test: confirms the ADK + LiteLlm + OpenRouter wiring actually
returns text before it gets buried inside the rest of the app."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from app import config


async def main():
    model = LiteLlm(model=f"openrouter/{config.OPENROUTER_MODEL}", api_key=config.OPENROUTER_API_KEY)
    agent = LlmAgent(
        name="smoke_test_agent",
        model=model,
        instruction="You are terse. Answer in one short sentence.",
    )
    runner = InMemoryRunner(agent=agent, app_name="smoke-test")
    session = await runner.session_service.create_session(app_name="smoke-test", user_id="demo-user")

    message = types.Content(role="user", parts=[types.Part(text="Say hello and name the model you are running as, in one sentence.")])

    final_text = None
    async for event in runner.run_async(user_id="demo-user", session_id=session.id, new_message=message):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text

    print("MODEL REPLY:", final_text)


if __name__ == "__main__":
    asyncio.run(main())
