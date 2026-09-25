# Implementation Plan — Agentic Slack Assistant ("AI Trends Scout")

> Status: **PLAN ready for POC implementation**

---

## 1. Goal & Scope

Build a Python service (the **"brain"**) that:

1. Runs an LLM agent powered by **OpenAI** (`OPENAI_API_KEY`).
2. Gives the agent **tools** to search the web and trusted sources for the newest AI/LLM news
   (new models from frontier labs, new frameworks/libraries, notable releases, papers).
3. Is reachable from **Slack**, where only a thin **bot** lives (defined by a YAML manifest).
   Slack is just the I/O surface — all reasoning, tool calls and state live in this service.
4. Is structured so new capabilities (new tools, new agents, new Slack entry points) can be
   added without touching the core.
5. Ships with documentation: tech-stack rationale + step-by-step Slack setup.

**Out of scope for v1**: scheduled/automatic digests (decided: the bot answers **only when called by a user**), persistence in a real DB,
multi-workspace distribution (OAuth install flow), cloud deployment/IaC.

---

## 2. High-Level Architecture

```
┌──────────────────────── Slack workspace ────────────────────────┐
│  User: "@TrendsBot what new models were released this week?"   │
│  or DM to bot, or /ai-trends <question>                        │
└───────────────┬────────────────────────────────▲────────────────┘
                │ events (WebSocket, Socket Mode) │ chat.postMessage / chat.update
┌───────────────▼────────────────────────────────┴────────────────┐
│  slack_adapter/   (Slack Bolt for Python)                       │
│   - receives app_mention / DM / slash command                   │
│   - acks immediately, posts "🔎 Researching…" placeholder        │
│   - maps Slack thread → conversation session id                 │
│   - converts agent Markdown → Slack mrkdwn / Block Kit          │
└───────────────┬─────────────────────────────────────────────────┘
                │ AgentRequest(text, session_id, user, channel)
┌───────────────▼─────────────────────────────────────────────────┐
│  core/  (channel-agnostic brain — no Slack imports here)        │
│   - AgentService.run(request) -> AgentResponse                  │
│   - Agent registry (router/triage agent + specialist agents)    │
│   - Session memory per thread (SQLite)                          │
│   - Guardrails, tracing, error handling                         │
└───────────────┬─────────────────────────────────────────────────┘
                │ tool calls
┌───────────────▼─────────────────────────────────────────────────┐
│  tools/  (pluggable tool registry)                              │
│   - web_search         (OpenAI hosted web search)               │
│   - fetch_url          (read & extract article text)            │
│   - provider_feeds     (RSS/blog feeds of OpenAI, Anthropic,    │
│                         Google DeepMind, Meta AI, Mistral, …)   │
│   - github_releases    (latest releases of tracked frameworks)  │
│   - hacker_news        (HN Algolia API – trending AI stories)   │
│   - arxiv_search       (recent cs.CL / cs.LG papers)            │
│   - huggingface_trending (trending models)                      │
└─────────────────────────────────────────────────────────────────┘
```

Key design decision: **the core never imports Slack**. The Slack adapter is one "channel";
a CLI adapter (for local testing) is a second one. Later, Teams/Discord/HTTP API could be added
as further adapters with zero changes in `core/` or `tools/`.

---

## 3. Technology Choices (and why)

| Area | Choice | Why |
|---|---|---|
| Language | **Python 3.12+** | Best ecosystem for LLM/agents; repo already has a Python `.gitignore`. |
| Package/env mgmt | **uv** (`pyproject.toml` + `uv.lock`) | Fast, reproducible installs, single tool for venv + deps + running. |
| Agent framework | **OpenAI Agents SDK** (`openai-agents`) | First-party for our required provider; built-in agent loop, function tools from type-hinted Python functions, **hosted `WebSearchTool`**, handoffs between agents (extensibility), sessions (memory), guardrails, and built-in tracing. Lightweight vs. LangChain/LangGraph — fewer abstractions to learn and debug. |
| LLM API | OpenAI **Responses API** (used by the SDK) | Required for hosted tools such as web search. **Two-tier models** configured via env: `OPENAI_MODEL_RESEARCH` (strong model for the research agent) and `OPENAI_MODEL_TRIAGE` (small, cheap model for routing); exact defaults chosen at implementation time from the current OpenAI lineup. |
| Web search | OpenAI hosted **`WebSearchTool`** (primary) | No extra API key/vendor, returns results with citations. Fallback/alternative abstraction allows swapping to Tavily/Brave/SerpAPI later if needed. |
| Targeted sources | `httpx` + `feedparser` + public APIs (GitHub REST, HN Algolia, arXiv, Hugging Face Hub) | Web search alone is noisy for "what's new *this week*"; direct feeds give fresh, dated, authoritative signals. All free / key-optional. |
| Article extraction | `trafilatura` | Robust main-text extraction from HTML pages for `fetch_url`. |
| Slack integration | **Slack Bolt for Python** (`slack-bolt`) + `slack-sdk` | Official Slack framework: event routing, ack handling, retries, Socket Mode support. |
| Slack transport | **Socket Mode** (WebSocket) | No public URL / ngrok / TLS needed — works from a laptop or WSL. Can switch to HTTP Events API for production by changing config only. |
| Config | `pydantic-settings` | Typed settings loaded from `.env`/env vars, validated at startup. |
| Memory | Agents SDK `SQLiteSession` keyed by Slack `thread_ts` | Follow-up questions in the same thread keep context; zero infra. |
| Caching | small TTL cache (`cachetools`) on tool results | Avoid hammering feeds/APIs when several users ask similar questions. |
| Logging | `structlog` (JSON logs) + SDK tracing | Debuggable tool calls; OpenAI traces dashboard shows every agent step. |
| Testing | `pytest`, `pytest-asyncio`, `respx` (mock httpx) | Unit tests for tools, adapter formatting; agent tests with mocked model. |
| Lint/format/types | `ruff`, `mypy` | Standard, fast. |
| Container (optional) | `Dockerfile` | Easy deploy later; not required for local run. |

All of this will be written up in `docs/TECH_STACK.md` with the "what / why / where used" per library.

### 3.1 Learning track: the "Lang*" ecosystem and other alternatives

**The implementation stays as planned (OpenAI Agents SDK).** For learning purposes a dedicated doc,
`docs/ALTERNATIVES_LANG_ECOSYSTEM.md`, will map every component of *this* project to its
LangChain / LangGraph (and other framework) equivalent: what it would replace, and when that would
be the better choice. Package names and product names in that ecosystem change often, so they will
be checked against the current docs when the file is written.

**Who is responsible for what in the Lang* family**

| Project | Responsibility | Think of it as |
|---|---|---|
| **LangChain** (`langchain`, `langchain-core`) | Building blocks: a common interface for chat models, prompts, tools, output parsers, retrievers; in v1+ also `create_agent` (a ready-made agent loop that runs on LangGraph). | A standard library of LLM components |
| **Integration packages** (`langchain-openai`, `langchain-community`, `langchain-tavily`, …) | Connectors to model providers, search APIs, document loaders, vector stores. | Adapters to external services |
| **LangGraph** | Low-level orchestration: agents as **state graphs** (nodes and edges, loops, branches), durable **checkpointing**, human-in-the-loop pauses, multi-agent topologies (supervisor, swarm). | A state-machine / workflow engine for agents |
| **LangSmith** | Observability: tracing, datasets, evaluations, prompt versioning; works with any framework, not only LangChain. | Monitoring and testing for LLM apps |
| **LangGraph Server / Platform** (now sold under the LangSmith brand) + **LangGraph Studio** | Deploying and hosting LangGraph agents as an API with persistence and task queues; Studio is a visual debugger for graphs. | Runtime and hosting for agents |
| **LangServe** | Older way to expose LangChain chains as a REST API; in maintenance mode, replaced by LangGraph Server. | Legacy, mentioned only for context |
| **LangChain Hub / LangSmith prompts** | Sharing and versioning prompts. | A prompt registry |
| **`langchain-mcp-adapters`** | Lets LangChain/LangGraph agents use MCP tool servers. | MCP bridge |

**Mapping: this project's components → Lang* alternatives**

| Our component (plan) | Lang* alternative | When the alternative is the better choice |
|---|---|---|
| OpenAI Agents SDK `Agent` + `Runner` (agent loop) | LangChain `create_agent`, or a custom LangGraph graph | You need to switch model providers often (Anthropic, Gemini, local models) behind one interface, or need explicit control over every step of the loop. |
| Triage agent + handoffs (`core/registry.py`, `agents/triage.py`) | LangGraph **supervisor** pattern / conditional edges (`langgraph-supervisor`) | Routing becomes complex: multi-step plans, specialist agents running in parallel, or deterministic branches mixed with LLM decisions. |
| `SQLiteSession` (thread memory) | LangGraph **checkpointer** (`SqliteSaver` / `PostgresSaver`) | You need long-running workflows that survive restarts, "time travel" back to an earlier state, or pause/resume. |
| Hosted `WebSearchTool` | `langchain-tavily`, Brave/SerpAPI/DuckDuckGo tools from `langchain-community` | You move away from OpenAI or want a dedicated search provider with more control over results. |
| Custom `fetch_url` (`httpx` + `trafilatura`) | LangChain document loaders (`WebBaseLoader`, etc.) | You're building RAG: loading, splitting and embedding many documents. |
| `feedparser` / arXiv / HN tools | Community tools/loaders (`ArxivLoader`, RSS loaders, …) | Fast prototyping; our own tools are kept for full control over output and caching. |
| Guardrails (`core/guardrails.py`) | LangGraph nodes / LangChain middleware for validation, moderation, human approval | You need approval steps ("human-in-the-loop") before an agent acts. |
| OpenAI tracing + `structlog` | **LangSmith** | You want evaluations, datasets and regression testing of prompts, or tracing across several providers. |
| Our own Slack adapter + Socket Mode process | LangGraph Server deployment (Slack still calls through our adapter) | You deploy many agents and need hosted persistence, queues and scaling out of the box. |
| (not in v1) vector store / RAG over past news | LangChain retrievers + vector store integrations, or **LlamaIndex** | You want "what did we learn about X over the last 3 months" style questions over stored history. |

**Other (non-Lang) frameworks, briefly**: **LlamaIndex** (data/RAG-first, also has agent workflows),
**CrewAI** (role-based "crews" of agents), **AutoGen / Microsoft Agent Framework** (conversational
multi-agent), **Pydantic AI** (type-safe, provider-agnostic agents), **DSPy** (programmatic prompt
optimization), **Semantic Kernel** (enterprise/.NET-oriented orchestration). The doc will explain
each in 2–3 sentences with the rule of thumb of when to pick it.

**Rule of thumb that the doc will explain in detail**
- *OpenAI Agents SDK*: one provider (OpenAI), fairly linear agent + tools + handoffs, minimal code — **our case**.
- *LangChain*: provider-agnostic components and many ready integrations; quickest to prototype across vendors.
- *LangGraph*: complex, stateful, long-running or human-in-the-loop workflows where you want explicit control over the flow.
- *LangSmith*: add it for observability/evals whatever framework you use.

The doc will also include a **short side-by-side code sketch** of the same "trends agent with
web search tool" in (a) OpenAI Agents SDK, (b) LangChain `create_agent`, (c) a LangGraph graph,
so the differences are concrete. These are illustrations only and not part of the runtime code.

---

## 4. Proposed Repository Layout

```
agentic-slack-assistant/
├── pyproject.toml
├── .env.example                  # template; real .env stays git-ignored
├── README.md                     # quickstart
├── slack/
│   └── manifest.yaml             # Slack app manifest (bot, scopes, events, slash cmd)
├── docs/
│   ├── ARCHITECTURE.md           # components, data flow, sequence diagram
│   ├── TECH_STACK.md             # every tool/framework/library: what, why, where
│   ├── SLACK_SETUP.md            # step-by-step Slack app + manifest + channel setup
│   ├── EXTENDING.md              # how to add a tool / agent / channel adapter
│   ├── ALTERNATIVES_LANG_ECOSYSTEM.md  # LangChain/LangGraph/LangSmith & others vs. our choices
│   └── OPERATIONS.md             # running, logs, tracing, troubleshooting
├── src/trends_agent/
│   ├── __main__.py               # `python -m trends_agent slack|cli`
│   ├── config.py                 # pydantic-settings
│   ├── core/
│   │   ├── service.py            # AgentService: run(request) -> response
│   │   ├── models.py             # AgentRequest / AgentResponse dataclasses
│   │   ├── registry.py           # agent + tool registries
│   │   ├── sessions.py           # session store (SQLite)
│   │   └── guardrails.py         # input/output guardrails
│   ├── agents/
│   │   ├── triage.py             # router agent (handoffs to specialists)
│   │   └── ai_trends.py          # AI/LLM trends researcher agent + prompt
│   ├── tools/
│   │   ├── __init__.py           # auto-registration of tools
│   │   ├── base.py               # tool conventions, caching, error wrapping
│   │   ├── web_search.py
│   │   ├── fetch_url.py
│   │   ├── provider_feeds.py
│   │   ├── github_releases.py
│   │   ├── hacker_news.py
│   │   ├── arxiv_search.py
│   │   └── huggingface.py
│   ├── sources/
│   │   └── sources.yaml          # tracked labs' feeds + GitHub repos (editable, no code change)
│   └── adapters/
│       ├── slack/
│       │   ├── app.py            # Bolt app, handlers
│       │   └── formatting.py     # Markdown -> mrkdwn / Block Kit, chunking
│       └── cli.py                # local REPL for testing without Slack
└── tests/
    ├── tools/  ├── adapters/  └── core/
```

---

## 5. Agent Design

### 5.1 Agents
- **Triage agent** (entry point, **active from day one**, runs on the cheap `OPENAI_MODEL_TRIAGE`):
  classifies every request and hands off to a specialist. In v1 there is only one specialist, but
  this is the extension point — future capabilities (e.g. "summarize this channel", "Jira helper",
  "code review") become new specialist agents registered in `registry.py` without modifying
  existing ones. Off-topic requests get a short polite reply from triage itself (no expensive call).
- **AI Trends Researcher** (runs on `OPENAI_MODEL_RESEARCH`): system prompt instructs it to
  - resolve relative dates ("this week") against today's date (injected at runtime),
  - prefer primary sources (lab blogs, GitHub releases, papers) over aggregators,
  - cross-check claims from web search with at least one direct source when possible,
  - always return **links + dates** for each item, and say explicitly when nothing new was found,
  - output concise, Slack-friendly structure: *Headline → 3–7 bullet items (what / who / when / link) → "Why it matters"*.

### 5.2 Tools (v1)
| Tool | Input | Output | Purpose |
|---|---|---|---|
| `web_search` (hosted) | query | results + citations | Broad discovery of news/announcements. |
| `fetch_url` | url | cleaned text (truncated) | Read the actual announcement/article to verify details. |
| `get_provider_updates` | provider(s), since_days | dated list of posts | Latest posts from OpenAI, Anthropic, Google/DeepMind, Meta AI, Mistral, xAI, etc. (feeds in `sources.yaml`). |
| `get_framework_releases` | repo(s) or category, since_days | release tags, dates, notes | Tracks agent/LLM frameworks: LangChain, LangGraph, LlamaIndex, OpenAI Agents SDK, CrewAI, AutoGen, Pydantic AI, MCP SDKs, DSPy. (Inference/serving tools like vLLM/Ollama not tracked by default — can be added in `sources.yaml`.) |
| `get_hacker_news_ai` | query, since_days | top stories + points | Community signal on what's trending. |
| `search_arxiv` | query, since_days | papers | Notable new research. |
| `get_hf_trending` | type (models/spaces) | trending list | New open-weight models gaining traction. |

Tool conventions (in `tools/base.py`): async, typed params (→ JSON schema auto-generated by SDK),
timeouts, TTL cache, return compact structured text, never raise into the model (return an error
message the model can reason about).

### 5.3 Guardrails & limits
- Max agent turns / tool calls per request; request timeout (e.g. 90 s) with graceful Slack message.
- Input guardrail: reject/redirect clearly off-topic or abusive prompts (cheap model check) — optional in v1.
- Output: cap length, split into multiple Slack messages if > limits.
- Optional allowlist of Slack channels/users that may invoke the bot.

---

## 6. Slack Integration Design

### 6.1 Entry points
1. **@mention in a channel** (`app_mention` event) → answer in a thread under the message.
2. **Direct message** to the bot (`message.im`) → answer in DM.
3. **Slash command** `/ai-trends [question]` → answer **public in channel** by default; switchable to ephemeral via `SLASH_RESPONSE_VISIBILITY=public|ephemeral`.
4. Follow-ups in the same thread reuse the thread session (memory).

### 6.2 Request flow
1. Bolt receives event → `ack()` immediately (Slack requires < 3 s).
2. Post placeholder `🔎 Researching latest AI news…` in thread (optionally add 👀 reaction).
3. Run `AgentService.run()` asynchronously.
4. `chat.update` the placeholder with the final answer (Block Kit sections, links unfurl disabled
   to keep it clean). On error → friendly error message + log/trace id.
5. Dedupe Slack retries (`X-Slack-Retry-Num` / event_id cache).

### 6.3 Manifest (draft — final version goes to `slack/manifest.yaml`)
```yaml
display_information:
  name: AI Trends Scout
  description: Finds the newest AI/LLM models, frameworks and releases.
  background_color: "#1f2937"
features:
  app_home:
    home_tab_enabled: false
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
  bot_user:
    display_name: ai-trends-scout
    always_online: true
  slash_commands:
    - command: /ai-trends
      description: Ask about the latest AI/LLM trends
      usage_hint: "[what's new in open-weight models this week?]"
      should_escape: false
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - commands
      - im:history
      - im:read
      - im:write
      - reactions:write
      - channels:history   # read thread context in public channels (optional)
      - groups:history     # same for private channels (optional)
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
  interactivity:
    is_enabled: true
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
```

### 6.4 Secrets / env vars
```
OPENAI_API_KEY=...          # existing
OPENAI_MODEL_RESEARCH=...   # strong model for the research agent
OPENAI_MODEL_TRIAGE=...     # small/cheap model for the triage router
SLASH_RESPONSE_VISIBILITY=public   # public | ephemeral
SLACK_BOT_TOKEN=xoxb-...    # from "OAuth & Permissions" after install
SLACK_APP_TOKEN=xapp-...    # app-level token with connections:write (Socket Mode)
SLACK_SIGNING_SECRET=...    # only needed if switching to HTTP mode
GITHUB_TOKEN=...            # optional, raises GitHub API rate limit
ALLOWED_CHANNEL_IDS=...     # optional
```

### 6.5 `docs/SLACK_SETUP.md` will cover, with screenshots-level precision
1. Create app at api.slack.com/apps → **"From an app manifest"** → pick workspace → paste `slack/manifest.yaml`.
2. Generate **App-Level Token** (Basic Information → App-Level Tokens → scope `connections:write`) → `SLACK_APP_TOKEN`.
3. **Install to Workspace** → copy Bot User OAuth Token → `SLACK_BOT_TOKEN`.
4. Fill `.env`, run `uv run python -m trends_agent slack`, verify "connected" log.
5. Create/choose a channel (e.g. `#ai-trends`) → `/invite @ai-trends-scout`.
6. Test: mention, DM, slash command. Expected outputs.
7. Updating the manifest later (App Manifest editor / reinstall when scopes change).
8. Switching to HTTP mode for production (Request URL, signing secret, public endpoint).
9. Troubleshooting table (`not_in_channel`, `missing_scope`, `invalid_auth`, no events received, duplicate replies, etc.).

---

## 7. Extensibility Model (documented in `docs/EXTENDING.md`)

- **New tool** → add a file in `tools/` with a decorated function; it is auto-registered and can be
  attached to any agent by name in the agent definition.
- **New capability/agent** → add a module in `agents/` (prompt + tool list), register it; the
  triage agent gets it as a new handoff target.
- **New sources** → edit `sources/sources.yaml` (feeds, GitHub repos) — no code change.
- **New channel** → implement an adapter that converts its events to `AgentRequest` and renders
  `AgentResponse` (CLI adapter serves as the reference example).
- **MCP servers** → the Agents SDK supports MCP; external MCP tool servers can be plugged in later
  via config.
- **Other entry points** (e.g. a scheduler) could call `AgentService` the same way — not planned; v1 is on-demand only by decision.

---

## 8. Implementation Phases

| # | Phase | Deliverables | Done when |
|---|---|---|---|
| 0 | Scaffolding | `pyproject.toml` (uv), layout, `config.py`, `.env.example`, ruff/mypy/pytest config | `uv run pytest` passes on empty suite |
| 1 | Core + CLI | `AgentService`, AI Trends agent with hosted web search, CLI adapter | Can ask a question in terminal and get a cited answer |
| 2 | Tools | `fetch_url`, provider feeds, GitHub releases, HN, arXiv, HF trending + `sources.yaml` + caching + unit tests | Each tool tested with mocked HTTP; agent uses them in CLI |
| 3 | Slack adapter | Bolt app (Socket Mode), mention/DM/slash handlers, placeholder+update, formatting/chunking, dedupe, thread sessions, `slack/manifest.yaml` | End-to-end answer in a real Slack channel thread |
| 4 | Hardening | Timeouts, turn limits, error messages, allowlist, structured logs, tracing | Failure cases handled gracefully |
| 5 | Documentation | `README`, `ARCHITECTURE`, `TECH_STACK`, `SLACK_SETUP`, `EXTENDING`, `OPERATIONS`, `ALTERNATIVES_LANG_ECOSYSTEM` | A new person can set up the bot from docs only, and can tell which Lang* tool would replace which component |
| 6 | (Optional) Packaging | `Dockerfile`, run instructions | `docker run` works with env file |

Each phase ends with a review checkpoint with you. **No commits/pushes by me** — you commit.

---

## 9. Testing Strategy
- **Unit**: tools (mocked HTTP with `respx`), Slack formatting/chunking, config validation.
- **Adapter**: Bolt handlers tested with fake events and a mocked `AgentService`.
- **Agent**: smoke tests with a stubbed model; optional live "eval" script with a few canonical
  questions ("new OpenAI models this month", "latest LangGraph release") run manually (costs tokens).
- **Manual E2E**: checklist in `docs/OPERATIONS.md`.

---

## 10. Risks & Mitigations
| Risk | Mitigation |
|---|---|
| Hallucinated "news" | Require links + dates, prefer primary sources, verify with `fetch_url`, say "nothing found" explicitly. |
| Stale results from search | Inject current date; direct dated feeds; `since_days` filters. |
| Slack 3 s ack timeout / retries | Immediate ack + async processing + event dedupe. |
| Cost / latency | Turn & tool-call caps, caching, configurable cheaper model for triage. |
| Feed URLs change / some labs lack RSS | Sources in YAML; tool tolerates failures; web search fallback. |
| Secrets leakage | `.env` git-ignored (already verified), `.env.example` without values, no tokens in logs. |

---

## 11. Decisions (answered 2026-09-26)
| # | Topic | Decision |
|---|---|---|
| 1 | Deployment | **Local (WSL) now, cloud later** → Socket Mode default; HTTP mode supported via config and documented. |
| 2 | Routing | **Triage agent active from day one** — every request goes through triage, which hands off to specialists. |
| 3 | Models | **Two tiers**: strong model for research (`OPENAI_MODEL_RESEARCH`), cheap model for triage (`OPENAI_MODEL_TRIAGE`). |
| 4 | Slash visibility | **Public in channel by default**, configurable to ephemeral (`SLASH_RESPONSE_VISIBILITY`). |
| 5 | Default sources | **Frontier labs** (OpenAI, Anthropic, Google DeepMind, Meta AI, Mistral, xAI, DeepSeek, Qwen, Microsoft AI, NVIDIA), **agent/LLM frameworks** (GitHub releases), **community & research** (HN, arXiv, HF trending). Inference/serving tools not tracked by default. |
| 6 | Scheduled digest | **No** — bot responds only when called by a user. |
| 7 | Package manager | **uv**. |
