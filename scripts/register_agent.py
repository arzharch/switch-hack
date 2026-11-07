"""One-time setup: registers blocker-bot with a real Switch server using the
Agent Protocol (POST /agents with a registration key), then caches the
returned {id, api_key} locally so switch_transport.py can reuse it across
runs. Only needed when TRANSPORT=switch.

Usage:
    python scripts/register_agent.py
"""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config

CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / ".agent_credentials.json"


def main() -> None:
    if not config.SWITCH_REGISTRATION_TOKEN:
        raise SystemExit("SWITCH_REGISTRATION_TOKEN is not set in .env -- get it from your Switch server admin.")

    if CREDENTIALS_FILE.exists():
        existing = json.loads(CREDENTIALS_FILE.read_text())
        print(f"Already registered as agent_id={existing['id']} (delete {CREDENTIALS_FILE.name} to re-register).")
        return

    resp = httpx.post(
        f"{config.SWITCH_BASE_URL}/agents",
        headers={"Authorization": f"Bearer {config.SWITCH_REGISTRATION_TOKEN}"},
        json={
            "name": config.SWITCH_AGENT_NAME,
            "description": "Picks up assigned tasks, works them, and pages the correct owner when blocked.",
            "connector_type": "custom",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    print(f"Registered. agent_id={data['id']}. Credentials cached in {CREDENTIALS_FILE.name}.")
    print("Now invite it into a room from Switch Console, then set SWITCH_ROOM_ID in .env.")


if __name__ == "__main__":
    main()
