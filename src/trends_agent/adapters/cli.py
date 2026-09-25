"""Local terminal adapter — talk to the agents without Slack.

Interactive REPL by default; pass a question for one-shot mode.
Commands in the REPL: `/new` starts a fresh conversation, `/quit` exits.
"""

import asyncio
import time
import uuid

from trends_agent.config import Settings
from trends_agent.core.models import AgentRequest
from trends_agent.core.service import AgentService

HELP = "Ask about the latest AI/LLM news. Commands: /new (fresh conversation), /quit"


def _new_session_id() -> str:
    return f"cli:{uuid.uuid4().hex[:12]}"


async def _ask(service: AgentService, text: str, session_id: str) -> None:
    started = time.monotonic()
    response = await service.run(AgentRequest(text=text, session_id=session_id, channel="cli"))
    elapsed = time.monotonic() - started
    print(f"\n{response.text}\n")
    print(f"[{response.agent_name} · {elapsed:.1f}s · trace {response.trace_id}]\n")


async def run_cli(settings: Settings, question: str | None = None) -> int:
    service = AgentService.from_settings(settings)
    session_id = _new_session_id()

    if question:
        await _ask(service, question, session_id)
        return 0

    print(HELP)
    while True:
        try:
            text = (await asyncio.to_thread(input, "you> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text == "/quit":
            return 0
        if text == "/new":
            session_id = _new_session_id()
            print("Started a new conversation.")
            continue
        print("…researching")
        await _ask(service, text, session_id)
