# YouTube Community Manager Agent

**A production-ready LangGraph agent for automated YouTube channel engagement**

The YouTube Community Manager Agent logs into YouTube with your credentials, navigates to a **specific target channel** you configure, opens that channel's **latest video**, scrapes and analyzes **all comments**, selects **top positive reply targets**, generates humorous AI replies, optionally posts them, builds HTML/PDF reports, and emails summaries — all through a LangGraph workflow with Playwright browser automation and a React agent dashboard.

| | |
|---|---|
| **Author** | Muhammad Qasim Shabbir |
| **Email** | [muhammadqasimshabbir3@gmail.com](mailto:muhammadqasimshabbir3@gmail.com) |
| **Version** | 0.2.0 |
| **License** | MIT |

---

## How It Works

The agent uses **two separate concepts** in `.env`:

| Role | Variables | Purpose |
|------|-----------|---------|
| **Login account** | `YOUTUBE_EMAIL`, `YOUTUBE_PASSWORD` | The Google account used to sign in, browse YouTube, and post replies |
| **Target channel** | `YOUTUBE_CHANNEL_NAME`, `YOUTUBE_CHANNEL_URL` | The **specific channel** where work is performed — this does **not** have to be the login account's channel |

### Runtime flow

```
1. Log in          →  YOUTUBE_EMAIL / YOUTUBE_PASSWORD
2. Open channel    →  YOUTUBE_CHANNEL_NAME (or YOUTUBE_CHANNEL_URL)
3. Latest video    →  Agent opens the target channel's most recent upload
4. Scrape          →  All visible comments (MAX_COMMENTS_PER_VIDEO=0)
5. Analyze         →  LLM classifies every comment by sentiment/category
6. Select targets  →  Top N positive comments ranked by likes + sentiment
7. Reply           →  Generate (and optionally post) humorous AI replies
8. Report          →  HTML dashboard → PDF → email (when enabled)
```

```
┌──────────────────┐      ┌─────────────────────────┐      ┌────────────────────────┐
│  Login Account   │      │   Target Channel          │      │   Latest Video         │
│  (your .env      │ ───▶ │   YOUTUBE_CHANNEL_NAME    │ ───▶ │   All comments scraped,│
│   credentials)   │      │   e.g. @OldeWorldMelodies │      │   analyzed & replied   │
└──────────────────┘      └─────────────────────────┘      └────────────────────────┘
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Agent Web UI** | React + Vite dashboard with live LangGraph pipeline streaming |
| **LangGraph Server** | Backend API (`langgraph dev`) — deploy separately from frontend |
| **Browser automation** | Playwright Chromium; session persisted; Chrome stays open through posting |
| **Full comment scrape** | `MAX_COMMENTS_PER_VIDEO=0` analyzes all visible comments |
| **Top positive replies** | Selects up to `MAX_REPLIES_PER_VIDEO` best positive comments |
| **Humorous replies** | `REPLY_PERSONALITY=humorous` community-manager tone |
| **Automated posting** | `ENABLE_COMMENT_REPLIES=true` posts via browser on target video |
| **New video comments** | Optional top-level comment (`ENABLE_NEW_COMMENTS`) |
| **HTML dashboard** | Interactive report with reply targets, failures, LLM summary |
| **PDF reporting** | ReportLab summary reports |
| **Email automation** | Gmail SMTP with HTML + PDF attachments |
| **Legacy Streamlit UI** | Still available via `./start.sh streamlit` |

---

## Architecture (local & deployment)

```
┌─────────────────────────┐     LangGraph SDK / REST      ┌──────────────────────────┐
│  Agent Web UI (React)   │  ───────────────────────────▶ │  LangGraph Server        │
│  http://localhost:5173  │     stream: updates + events  │  http://127.0.0.1:2024   │
│  frontend/              │                               │  graph id: agent         │
└─────────────────────────┘                               │  Playwright + .env       │
                                                          └──────────────────────────┘
```

**Local:** `./start.sh both` starts LangGraph + UI. Vite proxies `/api` → LangGraph or uses `VITE_LANGGRAPH_API_URL` directly.

**Production:** Deploy LangGraph backend on Railway; deploy frontend on Vercel with `VITE_LANGGRAPH_API_URL=https://<railway-app>.up.railway.app`. CORS is configured via `CORS_ALLOW_ORIGINS` (not hardcoded).

---

## Workflow (graph nodes)

```
START
  → prepare_agent
  → decide_agent
  → login_youtube
  → fetch_channel_data         ← scrape all comments; browser session kept open
  → analyze_comments           ← classify every comment
  → select_reply_targets       ← top N positive (not already channel-replied)
  → generate_replies           ← humorous AI drafts
  → post_replies               ← if ENABLE_COMMENT_REPLIES=true
  → generate_new_comment       ← if ENABLE_NEW_COMMENTS=true (else skip)
  → post_new_comment           ← if ENABLE_NEW_COMMENTS=true (else skip)
  → generate_html_report       ← closes browser here
  → generate_pdf_report
  → email_report
  → END
```

See [AgentWorkflow.md](AgentWorkflow.md) for routing details, state fields, and diagrams.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph `StateGraph` |
| Backend API | LangGraph Server (`langgraph dev`) |
| Frontend | React 19 + Vite + `@langchain/langgraph-sdk` |
| LLM | Groq `llama-3.1-8b-instant` |
| Browser | Playwright (Chromium) |
| PDF | ReportLab |
| Email | Gmail SMTP |
| Legacy UI | Streamlit (`streamlit_ui.py`) |

---

## Quick Start

### 1. Install dependencies

```bash
./setup.sh
```

Or manually:

```bash
uv sync
uv run playwright install chromium
cd frontend && npm install && cd ..
cp .env.example .env
```

### 2. Configure `.env`

Minimum required:

```env
GROQ_API_KEY=gsk_your_key_here
YOUTUBE_EMAIL=manager@gmail.com
YOUTUBE_PASSWORD=your_password_here
YOUTUBE_CHANNEL_NAME=@YourChannel

ENABLE_COMMENT_REPLIES=true
MAX_COMMENTS_PER_VIDEO=0
MAX_REPLIES_PER_VIDEO=5
REPLY_PERSONALITY=humorous
KEEP_BROWSER_OPEN=true
```

### 3. Run backend + Agent UI

```bash
./start.sh both
```

| Service | URL |
|---------|-----|
| **Agent UI** | http://localhost:5173 |
| **LangGraph API** | http://127.0.0.1:2024 |
| **LangSmith Studio** | https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024 |

In the UI:

1. Confirm **LangGraph connected** (green status in sidebar)
2. Set channel name / URL, **max replies**, and **email recipient**
3. Click **▶️ Start Agent**
4. Watch the **Agent Pipeline** stream step-by-step

---

## Commands

```bash
./start.sh both       # LangGraph + Agent Web UI (recommended)
./start.sh ui         # Agent UI only (needs server running)
./start.sh server     # LangGraph Server + Studio only
./start.sh streamlit  # Legacy Streamlit UI → :8501
./start.sh stop       # Stop services on :2024 and :5173
./start.sh restart both
```

---

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | Required for LLM analysis and replies |
| `YOUTUBE_EMAIL` / `YOUTUBE_PASSWORD` | — | Login account for Playwright |
| `YOUTUBE_CHANNEL_NAME` / `YOUTUBE_CHANNEL_URL` | — | Target channel (latest video) |

### Comments & replies

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_COMMENTS_PER_VIDEO` | `0` | `0` = scrape/analyze **all** visible comments |
| `MAX_REPLIES_PER_VIDEO` | `5` | Top N **positive** comments to reply to |
| `REPLY_PERSONALITY` | `humorous` | Reply tone (`humorous`, etc.) |
| `ENABLE_COMMENT_REPLIES` | `false` | Post replies on YouTube via browser |
| `ENABLE_NEW_COMMENTS` | `false` | Generate/post a new top-level video comment |
| `KEEP_BROWSER_OPEN` | `true` | Keep Chrome open from scrape through posting; closed before HTML report |
| `REPLY_TO_POSITIVE` | `true` | Include positive comments in reply generation |

### Email

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_REPORTS` | `false` | Send HTML + PDF via Gmail SMTP |
| `GMAIL_SMTP_USER` / `GMAIL_APP_PASSWORD` | — | Gmail credentials |
| `GMAIL_DEFAULT_RECIPIENT` | — | Default To address (overridable per run from UI) |

### Services & frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGGRAPH_PORT` | `2024` | LangGraph Server port |
| `FRONTEND_PORT` | `5173` | Agent Web UI port |
| `VITE_LANGGRAPH_API_URL` | `http://127.0.0.1:2024` | Frontend → backend URL |
| `VITE_API_URL` / `NEXT_PUBLIC_API_URL` | — | Aliases for `VITE_LANGGRAPH_API_URL` (Vercel) |
| `CORS_ALLOW_ORIGINS` | localhost origins | Comma-separated CORS origins for LangGraph API |
| `PORT` | `8000` | LangGraph API port in Docker/Railway (`2024` for local `langgraph dev`) |
| `VITE_LANGGRAPH_ASSISTANT_ID` | `agent` | Graph id from `langgraph.json` |
| `VITE_DEFAULT_CHANNEL_NAME` | — | Pre-fill channel in UI |
| `VITE_DEFAULT_MAX_REPLIES` | `5` | Pre-fill max replies in UI |
| `VITE_DEFAULT_EMAIL_RECIPIENT` | — | Pre-fill email recipient in UI |

Per-run UI overrides (sent in graph input): `max_replies_per_video`, `email_recipient`.

---

## Project Structure

```
├── frontend/                      # Agent Web UI (React + Vite)
│   ├── src/
│   │   ├── lib/agentClient.ts     # LangGraph SDK connection layer
│   │   ├── hooks/useAgentRun.ts   # Streaming pipeline + results
│   │   └── components/            # Pipeline, dashboard, forms
│   └── package.json
├── src/agent/
│   ├── graph.py                   # LangGraph definition
│   ├── config.py                  # .env + per-run overrides
│   ├── workflow_executor.py       # Pipeline step execution
│   └── custom_tools/
│       ├── youtube_tools.py       # Scrape, post replies, browser session
│       ├── comment_selection.py   # Top positive reply target ranking
│       ├── comment_analyzer.py    # LLM classification
│       ├── reply_generator.py     # Humorous AI replies
│       ├── new_comment_generator.py
│       ├── html_report_generator.py
│       ├── pdf_generator.py
│       └── email_tools.py
├── streamlit_ui.py                # Legacy UI (in-process graph)
├── langgraph.json                 # LangGraph server config (graphs, deps)
├── Dockerfile                     # Railway / LangGraph API production image
├── railway.json                   # Railway deployment config
├── .dockerignore
├── requirements.txt               # Exported from pyproject.toml (reference)
├── start.sh / setup.sh
├── AgentWorkflow.md               # Detailed workflow documentation
└── reports/                       # Generated HTML/PDF outputs
```

---

## Reply target selection

After analyzing **all** comments, the agent:

1. Filters **positive** comments only
2. Skips channel-owner comments, pinned comments, and threads where the channel already replied (`channel_replied`)
3. Ranks by likes + sentiment + engagement priority
4. Selects up to `MAX_REPLIES_PER_VIDEO` targets
5. Generates humorous replies; posts when `ENABLE_COMMENT_REPLIES=true`

When `ENABLE_NEW_COMMENTS=false`, the graph **skips** new comment generation and posting entirely.

---

## Production deployment

### Architecture

```
┌─────────────────────────┐         HTTPS          ┌──────────────────────────┐
│  Vercel (React/Vite UI) │  ────────────────────▶ │  Railway (LangGraph API) │
│  frontend/              │   VITE_LANGGRAPH_API_URL│  Dockerfile              │
└─────────────────────────┘                         │  Playwright + secrets    │
                                                    └──────────────────────────┘
```

| Component | Platform | Port / URL |
|-----------|----------|------------|
| Backend | Railway | `https://<app>.up.railway.app` |
| Frontend | Vercel | `https://<app>.vercel.app` |
| Local dev | `./start.sh both` | UI `:5173`, API `:2024` |

---

### Backend — Railway

**Prerequisites:** A [Railway](https://railway.app/) account and the Railway CLI installed (`railway login`).

1. **Review config** (already in repo):
   - `Dockerfile` — LangGraph API + Playwright Chromium
   - `railway.json` — Deployment configuration
   - `.dockerignore` — excludes `.env`, `frontend/`, local data

2. **Create the Railway app** (first time only):

```bash
railway init
# Choose an empty project
```

3. **Set secrets** (never commit these):
In the Railway dashboard (or via CLI `railway variables set`), add:
- `GROQ_API_KEY="gsk_..."`
- `YOUTUBE_EMAIL="your@gmail.com"`
- `YOUTUBE_PASSWORD="your_password"`
- `LANGSMITH_API_KEY="lsv2_..."`
- `GMAIL_SMTP_USER="your@gmail.com"`
- `GMAIL_APP_PASSWORD="your_app_password"`
- `CORS_ALLOW_ORIGINS="http://localhost:5173,https://your-app.vercel.app"`

Optional: `OPENAI_API_KEY`, `GMAIL_DEFAULT_RECIPIENT`, and other vars from `.env.example`.

4. **Deploy:**

```bash
railway up
```

5. **Verify API:**
Find your public domain in the Railway dashboard (Settings → Environment → Public Networking).
```bash
curl https://<your-app>.up.railway.app/ok
```

**Regenerate Dockerfile** after changing `langgraph.json`:

```bash
uv run langgraph dockerfile -c langgraph.json Dockerfile
# Re-apply the Playwright install block after the dependency install step (see Dockerfile comment)
```

---

### Frontend — Vercel

1. **Import repo** in [Vercel](https://vercel.com) → set **Root Directory** to `frontend`.

2. **Environment variables** (Project → Settings → Environment Variables):

| Variable | Example | Required |
|----------|---------|----------|
| `VITE_LANGGRAPH_API_URL` | `https://your-app.up.railway.app` | Yes |
| `VITE_LANGGRAPH_ASSISTANT_ID` | `agent` | Yes |
| `VITE_UI_URL` | `https://your-app.vercel.app` | Optional |

Aliases also supported: `VITE_API_URL`, `NEXT_PUBLIC_API_URL`.

3. **Deploy:**

```bash
cd frontend
npm install
npm run build          # local smoke test
vercel                 # or connect GitHub for auto-deploy
```

4. **Update Railway CORS** with your final Vercel URL:
Set `CORS_ALLOW_ORIGINS="http://localhost:5173,https://your-app.vercel.app"` in your Railway variables.

---

### CORS (mandatory for production)

LangGraph reads **`CORS_ALLOW_ORIGINS`** at runtime (comma-separated, no spaces).

- **Local:** `http://localhost:5173,http://127.0.0.1:5173` (in `.env` or Railway variables)
- **Production:** add your Vercel URL, e.g. `https://your-app.vercel.app`

Do **not** hardcode origins in `langgraph.json` — use the env var so dev and prod differ safely.

---

### requirements.txt

Docker/Railway installs from `pyproject.toml` via `langgraph.json` → `dependencies: ["."]`.

`requirements.txt` is exported for reference:

```bash
uv export --no-dev --no-hashes -o requirements.txt
```

---

## Testing

```bash
uv run pytest tests/ -q          # 58+ unit/integration tests
cd frontend && npm run build       # Production frontend build
```

---

## License

MIT — see [LICENSE](LICENSE).
