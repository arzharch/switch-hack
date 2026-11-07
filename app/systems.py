"""Mocked stand-in for the systems a real agent would actually query to find
out if something is blocked -- an infra API, a CI status check, a design-tool
webhook. This is what makes blocker detection a real branch instead of a
pre-written fact: the agent has to call check_status(component) and read the
result, it isn't told the answer up front."""

STATUS: dict[str, dict] = {
    "infra-access": {"blocked": True, "reason": "staging infra access not yet granted"},
    "design-review": {"blocked": True, "reason": "export column layout awaiting sign-off"},
    "db-admin": {"blocked": True, "reason": "production migration window not approved"},
    "logging-pipeline": {"blocked": False, "reason": None},
    "legacy-report-export": {"blocked": True, "reason": "needs a maintainer sign-off, but no CODEOWNERS entry exists for this component"},
}


def check(component: str) -> dict:
    return STATUS.get(component, {"blocked": False, "reason": None})
