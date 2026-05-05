# LinkedIn Post Generator

A dual-engine system that turns *what's actually happening in AI this week* into a LinkedIn post that reads like a real practitioner wrote it — and a scroll-stopping image that fits the post's emotion, not generic stock-AI imagery.

Two engines:

- **Pulse Scout** — pulls signals from ArXiv, Hacker News, Tavily-indexed news, Reddit, X, and a handful of curated newsletters across five configurable modules, then synthesises them into a Market Intelligence Briefing.
- **Authority Crew** — a three-agent crewAI pipeline (Researcher → Writer → Critic) followed by a standalone **Visual Director** step that produces a structured image plan, then `gpt-image-1` for the final render.

Backend is FastAPI with async job queues and a JSONL-backed history store. UI is a Streamlit client that talks to the API over HTTP only — no shared imports, no shared process.

## Architecture

```mermaid
flowchart LR
  subgraph UI["Streamlit UI"]
    UA[ui/streamlit_app.py]
    UC[ui/api_client.py]
    UA --> UC
  end

  UC -->|HTTP /api/v1| API

  subgraph API["FastAPI"]
    R1[/scout]
    R2[/posts]
    R3[/images]
    R4[/history]
    JR[Async JobRunner]
    JS[(JSONL JobStore)]
    R1 --> JR
    R2 --> JR
    JR --> JS
  end

  JR --> SCOUT[Pulse Scout]
  JR --> CREW[Authority Crew]
  CREW --> VD[Visual Director]
  R3 --> IMG[gpt-image-1]

  SCOUT --> ARXIV[(ArXiv)]
  SCOUT --> HN[(Hacker News)]
  SCOUT --> TAV[(Tavily)]
  CREW --> GPT5[(GPT-5)]
  CREW --> OPUS[(Claude Opus 4.7)]
  CREW --> SONNET[(Claude Sonnet 4.6)]
  VD --> SONNET
```

## Models

| Role | Model | Why |
|---|---|---|
| Researcher | `openai/gpt-5` | Better recency-aware fact assembly than 4o, and more honest about gaps in evidence. |
| Writer | `anthropic/claude-opus-4-7` | Best LLM for tone, voice, first-person practitioner prose. |
| Critic | `anthropic/claude-sonnet-4-6` | Sharp line-editor; reliably catches "smells like an LLM" patterns. |
| Visual Director | `anthropic/claude-sonnet-4-6` | Returns a structured image plan grounded in the post's emotional beats. |
| Image | `openai/gpt-image-1` | Composition + typography that feels editorial, not stock-AI. |

## What makes the output different

Most AI-written LinkedIn posts get caught by their own fingerprints: lists of three abstract nouns, em-dash pile-ups, stock metaphors ("brain with circuits"). This system is opinionated about avoiding all of that:

- The Researcher emits a `## Emotional Beats` section (3 short phrases, *practitioner-specific*) so downstream steps anchor on a real feeling rather than a generic topic noun.
- The Writer follows a hard 5-part anatomy (HOOK / BRAIN / SOUL / GIFT / HANDSHAKE), enforces ≤220 chars per line and ≤7 line clusters, and **must** weave a concrete noun pulled from the Fact Sheet into whichever hook it picks. Forced numbers and fake time anchors are explicitly worse than a clean opinion hook.
- The Critic does a cross-check pass against the Fact Sheet's `## Sources`, then a line-by-line LLM-smell pass.
- The **Visual Director** picks one of three styles based on the post's tone — Documentary still, Object portrait, or **Witty visual gag** — and emits a JSON plan with scene, emotion, composition, optional 3-7 word text overlay, and accent colour. Witty visuals are the default for contrarian / cheeky posts because that's what actually gets shared.
- Audience radio (engineering vs business) flips the scene defaults so business posts never get terminals and engineering posts never get boardrooms.

## Project layout

```
backend/
  api/        FastAPI app, routes, schemas, errors, rate limiter
  core/       settings, structured logging, job runner, pricing, paths
  scout/      Pulse Scout engine + 5 scanner modules
  post_generator/   crewAI 3-agent pipeline + Visual Director
  tools/      ArXiv / HN search tools + gpt-image-1 wrapper
  prompts/    extracted prompt templates (.txt)
  utils/      cost tracker, history manifest, post parser, user profile
ui/           Streamlit client (api_client.py + streamlit_app.py)
tests/        pytest suite
deploy/       Dockerfile + docker-compose for Fly.io / EC2
```

## Quick start

```bash
# 1. install
make sync

# 2. add keys
cp .env.example .env
$EDITOR .env   # OPENAI_API_KEY, ANTHROPIC_API_KEY, TAVILY_API_KEY

# 3. run both API and UI in parallel
make dev
# API → http://localhost:8000  (OpenAPI docs at /docs)
# UI  → http://localhost:8501
```

Useful targets:

```
make api      # FastAPI only
make ui       # Streamlit only
make test     # pytest suite
make fmt      # ruff format + fix
make lint     # ruff + mypy on backend/{api,core}
```

## API surface

All endpoints live under `/api/v1`. Long-running endpoints return a `job_id` immediately; clients poll the matching `GET` for status.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, key presence, scout backend label |
| `POST` | `/scout` | Start a Pulse Scout job (rate-unlimited) |
| `GET` | `/scout/{job_id}` | Poll a scout job |
| `POST` | `/posts` | Start an Authority Crew run (5/min/IP) |
| `GET` | `/posts/{job_id}` | Poll a post job; result includes `cost_breakdown` |
| `PATCH` | `/posts/{job_id}` | Save edited final post body |
| `POST` | `/images` | Generate or regenerate an image (10/min/IP) |
| `GET` | `/images/{image_id}` | Serve PNG bytes |
| `GET` | `/history` | List finalized runs from the JSONL manifest |
| `GET` | `/history/{run_id}` | One run's full record |

Every response carries an `x-request-id` header for tracing; structured JSON logs include the same id on every job state transition.

## Cost per post

Cost is computed from real provider usage at the end of a run, not estimated from token counts. Roughly:

- Crew (3 agents, Opus-heavy): typical ~$0.40–$1.20 depending on research breadth
- Visual Director: typical ~$0.01–$0.04
- Each `gpt-image-1` 1024×1024 high-quality render: ~$0.17

Pricing table lives in [backend/core/pricing.py](backend/core/pricing.py); keep it in sync with provider price lists.

## Output artifacts

Each finalized post produces a folder under `outputs/posts/{run_id}/`:

```
outputs/posts/20260503_120000/
├── post_final.md         # the post body (editable via PATCH /posts/{id})
├── raw_crew_output.md    # full crew transcript for debugging
├── fact_sheet.md         # researcher's full output
├── image_plan.json       # Visual Director plan
└── 20260503_120000_01.png  # generated image (multiple if regenerated)
```

The history manifest at `outputs/history.jsonl` indexes every run with topic, audience, post path, image paths, model identifiers, and the `cost_breakdown`.

## Run a single engine from the CLI

Both engines also work without the API:

```bash
uv run run_scout              # Pulse Scout only — all modules, last 7 days
uv run run_crew               # Authority Crew only — uses defaults from main.py
uv run run_with_trigger '{"topic": "...", "leader_angle": "..."}'
```

## Tests

```bash
uv run pytest -q              # 37 tests covering API, jobs, parsers,
                              # Visual Director, image gen (mocked), cost
                              # tracker, rate limiting, graceful shutdown
```

## Deployment

A Fly.io-targeted Dockerfile + supervisord setup is the planned path (single container running uvicorn + Streamlit, port 8080 publicly, internal :8000 API). The legacy EC2/Terraform/SSM bundle is preserved under [deploy/](deploy/) for reference.

## License

Private project — not open-source.
