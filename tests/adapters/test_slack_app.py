from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from trends_agent.adapters.slack.app import HELP, NOT_ALLOWED, PLACEHOLDER, SlackBot, build_app
from trends_agent.config import Settings
from trends_agent.core.models import AgentRequest, AgentResponse
from trends_agent.core.service import AgentService


class FakeService:
    def __init__(self, text: str = "**Answer** [src](https://x.io)", is_error: bool = False):
        self.requests: list[AgentRequest] = []
        self.text = text
        self.is_error = is_error

    async def run(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(self.text, "Research", "trace_1", is_error=self.is_error)


def make_client() -> AsyncMock:
    client = AsyncMock(spec=AsyncWebClient)
    client.chat_postMessage.return_value = {"ts": "999.1"}
    return client


def make_bot(settings: Settings, service: FakeService) -> SlackBot:
    return SlackBot(settings, cast(AgentService, service))


MENTION = {"channel": "C1", "user": "U1", "ts": "100.1", "text": "<@UBOT> what's new?"}


async def test_mention_answers_in_thread_and_updates_placeholder(settings: Settings) -> None:
    service, client = FakeService(), make_client()

    await make_bot(settings, service).handle_mention(MENTION, client)

    request = service.requests[0]
    assert request.text == "what's new?"
    assert request.session_id == "slack:C1:100.1"
    assert request.user_id == "U1"
    client.chat_postMessage.assert_awaited_once_with(
        channel="C1", thread_ts="100.1", text=PLACEHOLDER
    )
    update = client.chat_update.await_args.kwargs
    assert update["ts"] == "999.1"
    assert update["text"] == "*Answer* <https://x.io|src>"
    assert "trace_1" in update["blocks"][-1]["elements"][0]["text"]
    reactions = [c.kwargs["name"] for c in client.reactions_add.await_args_list]
    assert reactions == ["eyes", "white_check_mark"]


async def test_mention_inside_thread_reuses_thread_session(settings: Settings) -> None:
    service, client = FakeService(), make_client()
    event = {**MENTION, "ts": "105.5", "thread_ts": "100.1"}

    await make_bot(settings, service).handle_mention(event, client)

    assert service.requests[0].session_id == "slack:C1:100.1"
    assert client.chat_postMessage.await_args.kwargs["thread_ts"] == "100.1"


async def test_empty_mention_gets_help(settings: Settings) -> None:
    service, client = FakeService(), make_client()
    await make_bot(settings, service).handle_mention({**MENTION, "text": "<@UBOT>"}, client)
    assert not service.requests
    assert client.chat_postMessage.await_args.kwargs["text"] == HELP


async def test_error_answer_gets_warning_reaction(settings: Settings) -> None:
    service, client = FakeService(is_error=True), make_client()
    await make_bot(settings, service).handle_mention(MENTION, client)
    assert client.reactions_add.await_args_list[-1].kwargs["name"] == "warning"


async def test_reaction_failures_do_not_break_answer(settings: Settings) -> None:
    service, client = FakeService(), make_client()
    client.reactions_add.side_effect = SlackApiError("no", {"error": "missing_scope"})  # type: ignore[no-untyped-call]
    await make_bot(settings, service).handle_mention(MENTION, client)
    client.chat_update.assert_awaited_once()


async def test_channel_allowlist(settings: Settings) -> None:
    settings.allowed_channel_ids = ["C_OK"]
    service, client = FakeService(), make_client()

    await make_bot(settings, service).handle_mention(MENTION, client)

    assert not service.requests
    client.chat_postEphemeral.assert_awaited_once_with(channel="C1", user="U1", text=NOT_ALLOWED)


@pytest.mark.parametrize(
    "event",
    [
        {"channel_type": "channel", "channel": "C1", "user": "U1", "ts": "1", "text": "hi"},
        {
            "channel_type": "im",
            "channel": "D1",
            "user": "U1",
            "ts": "1",
            "text": "hi",
            "subtype": "message_changed",
        },
        {"channel_type": "im", "channel": "D1", "ts": "1", "text": "hi", "bot_id": "B1"},
    ],
)
async def test_direct_message_ignores_non_user_messages(
    settings: Settings, event: dict[str, Any]
) -> None:
    service, client = FakeService(), make_client()
    await make_bot(settings, service).handle_direct_message(event, client)
    assert not service.requests


async def test_direct_message_allowed_even_with_allowlist(settings: Settings) -> None:
    settings.allowed_channel_ids = ["C_OK"]
    service, client = FakeService(), make_client()
    event = {"channel_type": "im", "channel": "D1", "user": "U1", "ts": "7.7", "text": "news?"}

    await make_bot(settings, service).handle_direct_message(event, client)

    assert service.requests[0].session_id == "slack:D1:7.7"


def command(text: str = "what's new?") -> dict[str, Any]:
    return {"text": text, "channel_id": "C1", "user_id": "U1"}


async def test_slash_command_public_answer(settings: Settings) -> None:
    service, respond = FakeService(), AsyncMock()

    await make_bot(settings, service).handle_slash_command(command(), respond)

    placeholder, final = respond.await_args_list
    assert placeholder.kwargs == {"text": PLACEHOLDER, "response_type": "ephemeral"}
    assert final.kwargs["response_type"] == "in_channel"
    assert final.kwargs["replace_original"] is False
    assert "<@U1> asked: _what's new?_" in final.kwargs["blocks"][0]["elements"][0]["text"]
    assert service.requests[0].session_id.startswith("slack:slash:")


async def test_slash_command_ephemeral_replaces_placeholder(settings: Settings) -> None:
    settings.slash_response_visibility = "ephemeral"
    service, respond = FakeService(), AsyncMock()

    await make_bot(settings, service).handle_slash_command(command(), respond)

    final = respond.await_args_list[-1].kwargs
    assert final["response_type"] == "ephemeral" and final["replace_original"] is True


async def test_slash_command_without_text_shows_help(settings: Settings) -> None:
    service, respond = FakeService(), AsyncMock()
    await make_bot(settings, service).handle_slash_command(command("  "), respond)
    respond.assert_awaited_once_with(text=HELP, response_type="ephemeral")
    assert not service.requests


def test_duplicate_events_are_detected(settings: Settings) -> None:
    bot = make_bot(settings, FakeService())
    assert not bot.is_duplicate("Ev1")
    assert bot.is_duplicate("Ev1")
    assert not bot.is_duplicate(None)


def test_build_app_registers_listeners(settings: Settings) -> None:
    settings.slack_bot_token = settings.openai_api_key  # any SecretStr works here
    app = build_app(settings, cast(AgentService, FakeService()))
    assert len(app._async_listeners) == 3
