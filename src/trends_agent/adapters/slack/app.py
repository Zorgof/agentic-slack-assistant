"""Slack adapter (Slack Bolt for Python, async).

Slack is only the I/O surface: events are converted to `AgentRequest`s for the core
`AgentService`, and answers are rendered back as Block Kit messages.

Entry points:
- @mention in a channel      -> answer in a thread under the message
- direct message to the bot  -> answer in a thread under the message
- /ai-trends <question>      -> answer in the channel (or ephemeral, per settings)
Every Slack thread is one conversation (session), so follow-ups keep context.
"""

import re
import time
import uuid
from typing import Any

import structlog
from cachetools import TTLCache
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from trends_agent.adapters.slack.formatting import build_blocks, fallback_text
from trends_agent.config import Settings
from trends_agent.core.models import AgentRequest, AgentResponse
from trends_agent.core.service import AgentService

log = structlog.get_logger(__name__)

PLACEHOLDER = ":mag: Researching the latest AI news… this usually takes 20-60 seconds."
HELP = (
    "Hi! I track the newest AI/LLM releases — models from frontier labs, agent frameworks, "
    "trending open-weight models and papers.\n"
    "Try: `what's new in AI this week?`, `what did Anthropic release lately?` or "
    "`latest LangGraph release?` — mention me, DM me, or use `/ai-trends <question>`.\n"
    "Reply in the thread (mentioning me) to ask follow-up questions."
)
NOT_ALLOWED = "Sorry, I'm not enabled in this channel."
_MENTION = re.compile(r"<@[A-Z0-9]+>")


def _footer(response: AgentResponse, elapsed: float) -> str:
    return f"AI Trends Scout · {elapsed:.0f}s · ref `{response.trace_id}`"


class SlackBot:
    """Event handlers, independent of Bolt registration (easy to unit test)."""

    def __init__(self, settings: Settings, service: AgentService) -> None:
        self._settings = settings
        self._service = service
        # Slack may redeliver an event (retries); remember recently seen event ids.
        self._seen_events: TTLCache[str, bool] = TTLCache(maxsize=2048, ttl=600)

    def is_duplicate(self, event_id: str | None) -> bool:
        if not event_id:
            return False
        if event_id in self._seen_events:
            return True
        self._seen_events[event_id] = True
        return False

    def is_allowed(self, channel_id: str) -> bool:
        allowed = self._settings.allowed_channel_ids
        # Direct messages (channel ids starting with "D") are always allowed.
        return not allowed or channel_id in allowed or channel_id.startswith("D")

    async def handle_mention(self, event: dict[str, Any], client: AsyncWebClient) -> None:
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        if not self.is_allowed(channel):
            await client.chat_postEphemeral(channel=channel, user=event["user"], text=NOT_ALLOWED)
            return
        text = _MENTION.sub("", event.get("text", "")).strip()
        await self._answer_in_thread(client, channel, thread_ts, event["ts"], event["user"], text)

    async def handle_direct_message(self, event: dict[str, Any], client: AsyncWebClient) -> None:
        # Ignore edits/deletions/bot messages (they carry a subtype or bot_id).
        if event.get("channel_type") != "im" or event.get("subtype") or event.get("bot_id"):
            return
        thread_ts = event.get("thread_ts") or event["ts"]
        text = event.get("text", "").strip()
        await self._answer_in_thread(
            client, event["channel"], thread_ts, event["ts"], event["user"], text
        )

    async def handle_slash_command(self, command: dict[str, Any], respond: AsyncRespond) -> None:
        text = command.get("text", "").strip()
        channel = command["channel_id"]
        if not text:
            await respond(text=HELP, response_type="ephemeral")
            return
        if not self.is_allowed(channel):
            await respond(text=NOT_ALLOWED, response_type="ephemeral")
            return

        public = self._settings.slash_response_visibility == "public"
        # Placeholder is always ephemeral (only the requester sees "researching…").
        await respond(text=PLACEHOLDER, response_type="ephemeral")
        started = time.monotonic()
        response = await self._service.run(
            AgentRequest(
                text=text,
                session_id=f"slack:slash:{uuid.uuid4().hex}",
                user_id=command["user_id"],
                channel="slack",
                metadata={"slack_channel": channel, "entry": "slash_command"},
            )
        )
        question = f"<@{command['user_id']}> asked: _{text}_"
        blocks = build_blocks(response.text, _footer(response, time.monotonic() - started))
        blocks.insert(0, {"type": "context", "elements": [{"type": "mrkdwn", "text": question}]})
        await respond(
            text=fallback_text(response.text),
            blocks=blocks,
            response_type="in_channel" if public else "ephemeral",
            replace_original=not public,
            unfurl_links=False,
            unfurl_media=False,
        )

    async def _answer_in_thread(
        self,
        client: AsyncWebClient,
        channel: str,
        thread_ts: str,
        message_ts: str,
        user: str,
        text: str,
    ) -> None:
        bound = log.bind(slack_channel=channel, thread_ts=thread_ts, user=user)
        if not text:
            await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=HELP)
            return

        await self._react(client, channel, message_ts, "eyes", add=True)
        placeholder = await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=PLACEHOLDER
        )
        started = time.monotonic()
        response = await self._service.run(
            AgentRequest(
                text=text,
                session_id=f"slack:{channel}:{thread_ts}",
                user_id=user,
                channel="slack",
                metadata={"slack_channel": channel, "thread_ts": thread_ts},
            )
        )
        elapsed = time.monotonic() - started
        try:
            await client.chat_update(
                channel=channel,
                ts=placeholder["ts"],
                text=fallback_text(response.text),
                blocks=build_blocks(response.text, _footer(response, elapsed)),
                unfurl_links=False,
                unfurl_media=False,
            )
        except SlackApiError as exc:
            bound.error("slack_update_failed", error=exc.response.get("error"))
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=fallback_text(response.text)
            )
        await self._react(client, channel, message_ts, "eyes", add=False)
        await self._react(
            client, channel, message_ts, "warning" if response.is_error else "white_check_mark"
        )
        bound.info("slack_answer_sent", seconds=round(elapsed, 1), is_error=response.is_error)

    @staticmethod
    async def _react(
        client: AsyncWebClient, channel: str, ts: str, name: str, add: bool = True
    ) -> None:
        """Reactions are cosmetic: never let them break the answer flow."""
        try:
            if add:
                await client.reactions_add(channel=channel, timestamp=ts, name=name)
            else:
                await client.reactions_remove(channel=channel, timestamp=ts, name=name)
        except SlackApiError as exc:
            log.debug("slack_reaction_failed", name=name, error=exc.response.get("error"))


def build_app(settings: Settings, service: AgentService) -> AsyncApp:
    if settings.slack_bot_token is None:
        raise ValueError("SLACK_BOT_TOKEN is required")
    http_mode = settings.slack_mode == "http"
    app = AsyncApp(
        token=settings.slack_bot_token.get_secret_value(),
        signing_secret=(
            settings.slack_signing_secret.get_secret_value()
            if settings.slack_signing_secret
            else None
        ),
        # Socket Mode traffic is authenticated by the app token; HTTP requests are signed.
        request_verification_enabled=http_mode,
    )
    bot = SlackBot(settings, service)

    @app.event("app_mention")
    async def on_mention(
        event: dict[str, Any], body: dict[str, Any], client: AsyncWebClient
    ) -> None:
        if not bot.is_duplicate(body.get("event_id")):
            await bot.handle_mention(event, client)

    @app.event("message")
    async def on_message(
        event: dict[str, Any], body: dict[str, Any], client: AsyncWebClient
    ) -> None:
        if not bot.is_duplicate(body.get("event_id")):
            await bot.handle_direct_message(event, client)

    @app.command("/ai-trends")
    async def on_command(ack: Any, command: dict[str, Any], respond: AsyncRespond) -> None:
        await ack()  # must happen within 3 seconds
        await bot.handle_slash_command(command, respond)

    @app.error
    async def on_error(error: Exception) -> None:
        log.exception("slack_handler_error", error=str(error))

    return app


def _require(value: Any, name: str) -> str:
    secret = value.get_secret_value() if value is not None else ""
    # ".env.example" ships "xoxb-"/"xapp-" placeholders; treat those as missing too.
    if len(secret) < 10:
        raise SystemExit(f"{name} is not set. See docs/SLACK_SETUP.md.")
    return str(secret)


async def run_socket_mode(settings: Settings) -> None:
    _require(settings.slack_bot_token, "SLACK_BOT_TOKEN")
    app_token = _require(settings.slack_app_token, "SLACK_APP_TOKEN")
    app = build_app(settings, AgentService.from_settings(settings))
    log.info("slack_socket_mode_starting")
    await AsyncSocketModeHandler(app, app_token).start_async()  # type: ignore[no-untyped-call]


def run_http_mode(settings: Settings) -> None:
    _require(settings.slack_bot_token, "SLACK_BOT_TOKEN")
    _require(settings.slack_signing_secret, "SLACK_SIGNING_SECRET")
    app = build_app(settings, AgentService.from_settings(settings))
    log.info("slack_http_mode_starting", port=settings.slack_http_port)
    app.start(port=settings.slack_http_port, path="/slack/events")
