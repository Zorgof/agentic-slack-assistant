# Slack setup

This guide connects the AI Trends Scout "brain" (this repository) to a Slack workspace.
Slack only hosts a **bot user**; everything else (the agents, tools and memory) runs in the
Python process started from this repository.

```
Slack workspace ──(WebSocket, Socket Mode)──► python -m trends_agent slack ──► OpenAI + web sources
```

**Time needed:** about 10 minutes. **You need:** permission to install apps in the workspace
(or a workspace admin to approve the install).

---

## 1. Create the Slack app from the manifest

The manifest (`slack/manifest.yaml`) describes the whole app: bot user, permissions (scopes),
events, the `/ai-trends` command and Socket Mode. Creating the app from it avoids clicking
through every setting by hand.

1. Open <https://api.slack.com/apps> and sign in to your workspace.
2. Click **Create New App** → **From a manifest**.
3. Pick the workspace where the bot should live → **Next**.
4. Choose the **YAML** tab, delete the example content and paste the whole content of
   [`slack/manifest.yaml`](../slack/manifest.yaml) → **Next**.
5. Review the summary (bot scopes, events, slash command) → **Create**.

What the manifest configures:

| Section | Value | Why |
|---|---|---|
| `bot_user` | `ai-trends-scout` | The bot users see and mention. |
| `slash_commands` | `/ai-trends` | Ask a question from any channel. |
| `oauth_config.scopes.bot` | `app_mentions:read`, `chat:write`, `commands`, `im:history`, `im:read`, `im:write`, `reactions:write` | Minimum permissions: receive mentions and DMs, post/update answers, status reactions. The bot **cannot** read channel history. |
| `event_subscriptions.bot_events` | `app_mention`, `message.im` | Events the bot receives: mentions in channels and direct messages. |
| `socket_mode_enabled` | `true` | Slack pushes events over a WebSocket opened by our process — no public URL, no ngrok. |
| `app_home.messages_tab_enabled` | `true` | Lets users DM the bot. |

## 2. Create the app-level token (for Socket Mode)

Socket Mode connections are authenticated with an **app-level token** (starts with `xapp-`).

1. In your app's settings, open **Basic Information**.
2. Scroll to **App-Level Tokens** → **Generate Token and Scopes**.
3. Name it e.g. `socket-mode`, click **Add Scope** → `connections:write` → **Generate**.
4. Copy the token (`xapp-…`) — this is `SLACK_APP_TOKEN`.

## 3. Install the app and get the bot token

1. Open **Install App** (left menu) → **Install to <workspace>** → **Allow**.
   If your workspace requires approval, an admin has to approve the request first.
2. Copy the **Bot User OAuth Token** (`xoxb-…`) — this is `SLACK_BOT_TOKEN`.

## 4. Configure and start the brain

Put both tokens into `.env` (never commit this file):

```dotenv
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_MODE=socket
```

Start the bot:

```bash
uv run python -m trends_agent slack
```

You should see `slack_socket_mode_starting` followed by a
`A new session has been established` log line. The process must keep running for the bot to
answer — if it stops, the bot stays online in Slack but does not reply.

## 5. Add the bot to a channel

1. Create a channel (e.g. `#ai-trends`) or open an existing one.
2. Type `/invite @ai-trends-scout` in the channel (or: channel name → **Integrations** →
   **Add apps**).

Direct messages and `/ai-trends` work without inviting the bot anywhere; **@mentions only
work in channels the bot is a member of**.

## 6. Test it

| Try | Expected |
|---|---|
| `@ai-trends-scout what's new in AI this week?` in the channel | 👀 reaction, a "Researching…" reply in a thread, replaced by the answer after ~20-70 s; ✅ reaction at the end. |
| Reply in that thread: `@ai-trends-scout tell me more about the first one` | Follow-up answer that uses the earlier conversation. |
| DM the bot: `latest LangGraph release?` | Answer in a thread under your DM. Replies in that thread don't need a mention. |
| `/ai-trends what did Anthropic release lately?` | An ephemeral "Researching…" note, then the answer posted to the channel (or only to you if `SLASH_RESPONSE_VISIBILITY=ephemeral`). |
| `@ai-trends-scout` with no question | A short help message. |

Each answer ends with `ref trace_…`: look it up in the OpenAI dashboard → **Traces** to see
every step (handoff, tool calls, searches).

## 7. Optional settings

| Env var | Effect |
|---|---|
| `SLASH_RESPONSE_VISIBILITY=ephemeral` | `/ai-trends` answers are visible only to the person who asked. |
| `ALLOWED_CHANNEL_IDS=C0123,C0456` | Only these channels may use the bot (DMs are always allowed). Channel ID: channel name → **About** → bottom of the dialog. |

## 8. Changing the app later

- Edit `slack/manifest.yaml`, then in the app settings open **App Manifest**, paste the new
  version and **Save Changes**.
- If you **added scopes**, Slack shows a banner asking to **reinstall** the app — do it, and
  the bot token stays the same.

## 9. Moving to production (HTTP mode, optional)

Socket Mode is ideal for running on a laptop/WSL. For a server with a public HTTPS URL:

1. In the manifest set `socket_mode_enabled: false` and add
   `request_url: https://<your-host>/slack/events` under `event_subscriptions`, under
   `interactivity`, and to the `/ai-trends` slash command entry.
2. Copy **Basic Information → Signing Secret** into `SLACK_SIGNING_SECRET`.
3. Set `SLACK_MODE=http` (and `SLACK_HTTP_PORT`, default 3000) and start the same command;
   it serves `POST /slack/events`. Put it behind HTTPS (reverse proxy or a platform that
   terminates TLS).

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `SLACK_BOT_TOKEN is not set` on start | Tokens missing or still the `xoxb-` placeholder in `.env`. |
| `invalid_auth` / `not_authed` in logs | Wrong or revoked token; copy it again (steps 2-3). |
| Bot online but never answers | The process is not running, or `SLACK_APP_TOKEN` lacks `connections:write`. |
| Mention does nothing in a channel | Bot is not a member: `/invite @ai-trends-scout`. |
| `/ai-trends` says "dispatch_failed" | The process is not running (Slack could not deliver the command). |
| `not_in_channel` in logs | Bot was removed from the channel; invite it again. |
| `missing_scope` in logs | Scopes changed in the manifest but the app was not reinstalled (step 8). |
| "Sorry, I'm not enabled in this channel" | Channel not in `ALLOWED_CHANNEL_IDS`. |
| Answer says "took too long" | Raise `AGENT_TIMEOUT_SECONDS` or ask a narrower question. |
| Replies appear twice | Two bot processes are running with the same app token; stop one. |
