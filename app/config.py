import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

TRANSPORT = os.environ.get("TRANSPORT", "mock")

SWITCH_BASE_URL = os.environ.get("SWITCH_BASE_URL", "http://localhost:8000")
SWITCH_WS_BASE_URL = os.environ.get("SWITCH_WS_BASE_URL", "ws://localhost:8000")
SWITCH_REGISTRATION_TOKEN = os.environ.get("SWITCH_REGISTRATION_TOKEN", "")
SWITCH_AGENT_NAME = os.environ.get("SWITCH_AGENT_NAME", "blocker-bot")
SWITCH_ROOM_ID = os.environ.get("SWITCH_ROOM_ID", "")

AGENT_DISPLAY_NAME = "blocker-bot"
