# LinkedIn Post Generator — v2 Upgrade Plan

## Context

The current app is a single-process Streamlit cockpit ([app.py](app.py)) that imports engines directly and runs the 3-agent Authority Crew kickoff inline (a 2–4 minute blocking call). All file I/O, DALL-E calls, and cost tracking happen inside Streamlit fragments. Engines work but are coupled to the UI, there are no tests, and the image-generation step produces abstract "minimalist brutalist" prompts that read like Wired magazine covers — they do not emotionally connect to the post and do not stop the scroll on LinkedIn.

This upgrade has two halves:

1. **Architecture** — split the app into a FastAPI backend + a Streamlit UI client that talks only over HTTP. Long crew runs become async jobs the UI polls. Add a file-based job/history index, structured config, logging, error contracts, and a deployable Docker setup for Fly.io.
2. **Quality** — overhaul the Authority Crew prompts, upgrade the LLMs (Opus 4.7 for the writer, GPT-5 for research, Sonnet 4.6 as critic), replace DALL-E 3 with **gpt-image-1**, and rebuild the image-prompt step so the visual is grounded in the *emotional hook* of the finalized post (not just the topic noun).

Outcome: portfolio-grade dual-engine system with a clean API surface, a proper UI, and visibly better posts + scroll-stopping images.

---

## Scope (locked from clarifying questions)

- **Approach:** Modularize + APIify (keep engine logic, split layers). Not a full rewrite.
- **Image model:** `gpt-image-1` (replaces DALL-E 3).
- **Deploy:** Fly.io (single Docker app, region `syd`).
- **History:** file-based JSON manifest indexing `outputs/`. No DB.
- **Auth:** none (single-user portfolio demo).

Non-goals: multi-tenant, Postgres, Celery/Redis, rewriting scout modules, replacing crewAI, adding LinkedIn API publishing.

---

## New project structure

The whole `src/linkedin_post_generator/` nesting goes away. There is one top-level **`backend/`** package and one top-level **`ui/`** package, side by side. Inside `backend/`, the two engines become first-class folders: **`scout/`** and **`post_generator/`** (renamed from `authority_crew/`).

```
linkedin_post_generator/                 # repo root
├── pyproject.toml                       # package = "backend"; add fastapi, uvicorn, pydantic-settings, pytest
├── README.md                            # rewritten: portfolio-style with architecture diagram
├── Makefile                             # make api / ui / dev / test / fmt / docker-build
├── .env.example                         # new — keys + defaults; real .env stays gitignored
├── fly.toml                             # new — Fly.io app config
├── deploy/
│   ├── Dockerfile                       # rewritten for multi-process (api + ui via supervisord)
│   └── docker-compose.yml               # local dev: api on 8000, ui on 8501
├── ui/                                  # Streamlit client, no engine imports
│   ├── streamlit_app.py
│   └── api_client.py
├── backend/                             # the entire backend, flat at repo root
│   ├── __init__.py
│   ├── main.py                          # CLI entry: run-api, run-ui, run-scout, run-post
│   ├── api/                             # FastAPI layer
│   │   ├── main.py                      # app factory, CORS, lifespan
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── scout.py                 # POST /scout, GET /scout/{job_id}
│   │   │   ├── posts.py                 # POST /posts, GET /posts/{job_id}, PATCH /posts/{id}
│   │   │   ├── images.py                # POST /images, regen
│   │   │   └── history.py               # GET /history, GET /history/{id}
│   │   ├── schemas.py                   # pydantic request/response models
│   │   ├── deps.py                      # job store, settings, LLM clients (DI)
│   │   └── errors.py                    # app exceptions → consistent JSON errors
│   ├── core/                            # shared infra
│   │   ├── settings.py                  # pydantic-settings, single source for env
│   │   ├── logging.py                   # structlog JSON logging
│   │   ├── jobs.py                      # in-process job runner + JSONL job store
│   │   ├── pricing.py                   # per-model cost table
│   │   └── paths.py                     # output dir helpers
│   ├── scout/                           # Engine 1 (was engines/pulse_scout*)
│   │   ├── __init__.py
│   │   ├── engine.py                    # PulseScout class (was pulse_scout.py)
│   │   └── modules/                     # was pulse_scout_modules/
│   │       ├── base.py
│   │       ├── community_sentiment.py
│   │       ├── technical_deep_dive.py
│   │       ├── tooling_and_tactics.py
│   │       ├── long_form_strategy.py
│   │       ├── expert_synthesis.py
│   │       ├── crawl4ai_helper.py
│   │       └── time_utils.py
│   ├── post_generator/                  # Engine 2 (was authority_crew/)
│   │   ├── __init__.py
│   │   ├── crew.py                      # the 3-agent crew + cost callback
│   │   ├── visual_director.py           # NEW — emotion-grounded image prompt builder
│   │   └── config/
│   │       ├── agents.yaml              # rewritten — model bumps, sharper goals
│   │       └── tasks.yaml               # rewritten — drop image-prompt task
│   ├── tools/
│   │   ├── arxiv_search.py              # unchanged
│   │   ├── hn_search.py                 # unchanged
│   │   └── image_gen.py                 # NEW — gpt-image-1 wrapper
│   ├── prompts/                         # extracted prompt templates
│   │   ├── scout_synthesis.txt
│   │   ├── post_writer.txt
│   │   ├── post_critic.txt
│   │   └── image_prompt_builder.txt
│   └── utils/
│       ├── cost_tracker.py              # rewritten to read real API usage
│       ├── user_profile.py              # unchanged
│       └── history.py                   # NEW — JSONL manifest read/write
└── tests/
    ├── conftest.py
    ├── test_api_health.py
    ├── test_api_jobs.py                 # job lifecycle with mocked engines
    ├── test_post_parser.py              # extract_finalized_post round-trip
    ├── test_history.py                  # manifest read/write
    └── test_image_prompt.py             # image prompt builder shape contract
```

**Imports** under the new layout: `from backend.scout.engine import PulseScout`, `from backend.post_generator.crew import PostGeneratorCrew`, `from backend.tools.image_gen import generate_image`. `pyproject.toml` updates `[tool.hatch.build.targets.wheel] packages = ["backend"]` and the `[project.scripts]` entries point at `backend.main:run_api` etc.

---

## Backend — FastAPI service

**Endpoints (versioned under `/api/v1`):**

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness + Ollama + key presence check |
| `POST` | `/scout` | Start a Pulse Scout job. Body: `{modules: [...], days: int}`. Returns `{job_id, status}`. |
| `GET`  | `/scout/{job_id}` | Poll job state. Returns `{status, progress, report_md?, error?}`. |
| `POST` | `/posts` | Start an Authority Crew job. Body: topic, leader_angle, mood, author profile. Returns `{job_id}`. |
| `GET`  | `/posts/{job_id}` | Poll. Returns `{status, progress, post_draft?, image_prompt?, cost?, error?}`. |
| `PATCH`| `/posts/{job_id}` | Save edited final post body. |
| `POST` | `/images` | Generate or regenerate an image. Body: `{job_id, prompt}`. Returns `{image_url, image_id}`. |
| `GET`  | `/images/{image_id}` | Serve PNG bytes. |
| `GET`  | `/history` | List past runs from JSON manifest. |
| `GET`  | `/history/{run_id}` | One run's full record (post + image refs + cost). |

**Job model** (`core/jobs.py`):

- `JobStore` writes one JSONL file per kind under `outputs/jobs/{scout|posts}.jsonl`. Each line: `{job_id, kind, status, created_at, updated_at, inputs, result, error}`.
- `JobRunner` uses `asyncio.create_task` (single-process, single-replica is fine for a portfolio app) — no Redis/Celery. Cap: max 2 concurrent crew runs (`asyncio.Semaphore(2)`).
- Engines stay sync; we run them in `loop.run_in_executor(None, fn)` so the event loop stays responsive.
- `progress_callback` already exists for Scout — wire it through the job record.

**Settings** (`core/settings.py`) — pydantic-settings, one class `Settings`. Reads `.env`. Used by `Depends(get_settings)`. Replaces scattered `os.getenv()`.

**Logging** (`core/logging.py`) — `structlog` JSON renderer. One log line per request, one per job state transition, one per LLM call (model, latency, tokens). Toggle pretty console renderer with `LOG_PRETTY=true`.

**Errors** (`api/errors.py`) — single exception handler maps `EngineError`, `ValidationError`, generic `Exception` → consistent JSON shape `{error: {code, message, request_id}}`.

---

## UI — Streamlit as pure API client

[ui/streamlit_app.py](ui/streamlit_app.py) keeps the same 3-section flow (Intelligence Feed → Production Studio → Final Output + Image Studio) but **imports nothing from `linkedin_post_generator`**.

- A single `api_client.py` module wraps `httpx.Client(base_url=API_URL)` with helpers: `start_scout`, `poll_scout`, `start_post`, `poll_post`, `gen_image`, etc.
- Polling: `st.fragment(run_every=2)` rerenders the active job's status until terminal. Replaces the current blocking `st.spinner`.
- The "Run Crew" button no longer freezes the page for 4 minutes — user sees per-stage progress (`research`, `writing`, `critique`).
- Add a new "📚 History" tab at the top showing the manifest (recent runs, click to reload).
- Cost tracker reads from the API (`/posts/{id}` returns real token usage from LLM callbacks, not text-estimated).

`API_URL` defaults to `http://localhost:8000` and is overridable via env so the same Streamlit app works locally and in Fly.io.

---

## Engine improvements (the quality half)

### 1. Model upgrades

| Role | Current | New | Why |
|---|---|---|---|
| Researcher | `openai/gpt-4o` | `openai/gpt-5` | Reasoning + recency on factual tasks; better at saying "no evidence" than 4o. |
| Thought Leader | `anthropic/claude-sonnet-4-20250514` | `anthropic/claude-opus-4-7` | Opus 4.7 is the strongest LLM for tone, voice, and human-sounding prose — this is the heart of the post. |
| Critic | `openai/gpt-4o` | `anthropic/claude-sonnet-4-6` | Sonnet 4.6 is a sharper line-editor and follows the banned-words checklist more reliably than 4o. |
| Image | `dall-e-3` | `gpt-image-1` | Native multimodal, far better composition, can render legible text in image (used for the hook overlay). |

All model strings stay in `agents.yaml` so they remain swappable without code changes.

### 2. Authority Crew prompt revisions

[`agents.yaml`](src/linkedin_post_generator/engines/authority_crew/config/agents.yaml) and [`tasks.yaml`](src/linkedin_post_generator/engines/authority_crew/config/tasks.yaml):

- **Researcher fact sheet** — add an explicit `## Emotional Beats` section: 3 short phrases capturing the *feeling* a practitioner has about this topic right now (e.g., "quiet relief", "delayed buyer's remorse", "vindicated skepticism"). The Visual Director uses these.
- **Thought Leader** — keep the 5-part anatomy (HOOK / BRAIN / SOUL / GIFT / HANDSHAKE) since it works well, but tighten:
  - Output contract: ≤220 chars per line, ≤7 line clusters, single first-person voice.
  - Hooks: keep the existing five options as-is. They cover the useful ground; forcing a number or a time anchor when the post doesn't have one produces fake specificity, which is worse than a clean opinion hook. Instead, add one cross-cutting rule: **whichever hook is chosen, it must contain at least one concrete noun pulled from the Fact Sheet** (a specific paper, model name, company, benchmark, dollar figure if and only if the Fact Sheet contains one).
  - Add a hard rule: the SOUL line must reference a concrete artifact from the Fact Sheet (a specific paper, benchmark, company), not generic "I've seen this before".
- **Critic** — split into two sub-checks: (a) factual cross-check against the Fact Sheet's `## Sources`; (b) line-by-line rewrite pass for any sentence that "smells like an LLM" (token-pattern heuristics: lists of three, "not just X but Y", em-dash-heavy clauses).

### 3. The image-prompt overhaul (the part you specifically called out)

The current critic produces image prompts like *"minimalist brutalist composition of RAG retrieval pipeline, deep contrast, one accent color, no people, no text"*. That feels like a Wired cover, not something that makes a LinkedIn reader stop scrolling. LinkedIn's algorithm rewards images that look human, emotionally legible at thumbnail size, and *match the post's vibe* — not abstract architecture.

**New approach:** a dedicated `Visual Director` step ([`engines/authority_crew/visual_director.py`](src/linkedin_post_generator/engines/authority_crew/visual_director.py)) that runs *after* the critic finalizes the post. It is a single LLM call (Claude Sonnet 4.6) with this contract:

Input:
- The finalized post text (full)
- The fact sheet's `## Emotional Beats`
- Author profile (name, title)
- Target audience: **engineering peers** OR **business audience** — selectable from the UI as a single radio button on the Production Studio. The audience changes scene defaults: engineering audience leans toward IDEs, terminals, whiteboards, server rooms, late-night labs; business audience leans toward boardrooms, dashboards, handshakes, conference stages, coffee meetings. The Visual Director is told the audience explicitly and instructed to never produce a scene that feels foreign to it.

Output: a structured JSON image plan with 4 fields, then converted to a single gpt-image-1 prompt:

```json
{
  "scene": "<one literal real-world scene that could be photographed — a person, an object, a moment>",
  "emotion": "<the single dominant feeling — must come from Emotional Beats>",
  "composition": "<framing, lens, lighting>",
  "text_overlay": "<3-7 words drawn directly from the post hook OR null if the scene speaks for itself>"
}
```

**Hard rules baked into the builder prompt** (`prompts/image_prompt_builder.txt`):

1. **No abstract metaphors** unless the post is itself about an abstraction. A post about RAG pipelines failing in production gets a photograph of a frustrated engineer at a monitor — *not* a "filing cabinet with light beams". Abstract metaphors only when the post is meta/strategic.
2. **One subject, one moment, one feeling.** Forbid lists of objects, forbid "elements representing X". The image must read in 0.4 seconds at thumbnail size.
3. **Banned vocabulary in the image prompt itself**: "futuristic", "glowing", "circuits", "neural", "brain", "robot", "holographic", "binary code", "matrix", "cyberpunk", "digital art" — the entire visual stack of stock AI imagery.
4. **Prefer photographic realism** over illustration. Reference specific photographers/styles only if it sharpens intent (e.g., "shot on 35mm, Gregory Crewdson lighting") — not as decoration.
5. **Optional text overlay** rendered *inside* the image (gpt-image-1 handles this well). Use the exact 3-7 words of the post's hook if it stands alone. Center-bottom or upper-third placement, sans-serif.
6. **Accent color** derived from the emotion, not arbitrary: relief → soft daylight; vindication → warm tungsten; skepticism → overcast cyan; loss → muted amber.

Three preset styles the Visual Director picks between (no longer "brutalist vs diagram"):

- **Style A — Documentary still**: a single human moment (engineer staring at a screen, hands on a whiteboard, an empty office at 11pm; for the business audience: a founder mid-pitch, an exec staring at a dashboard at sunrise, a quiet handshake at the end of a meeting). Photographic, 35mm, natural light. Default for posts with strong personal SOUL.
- **Style B — Object portrait**: a single physical object that *is* the metaphor (a ripped-out server cable, a sticky-note pyramid, a hand erasing a whiteboard, a single coffee-stained whiteboard marker on a clean desk). Macro, shallow depth of field. Default for technical posts where a person would feel forced.
- **Style C — Witty visual gag**: a single funny, slightly absurd moment that earns a smirk in the half-second it takes to scroll past. Examples: a Jenga tower of MacBooks labelled "tech debt", a tiny umbrella over an overheating server, a rubber duck wearing a tie giving a code review, a printer on fire while the engineer calmly pours coffee, a "PRODUCTION" mug filled with crumpled deploy notes. Real photography or photoreal CGI — never cartoon. The humor lands because the scene is plausible, just exaggerated. Default for posts with a contrarian, cheeky, or self-deprecating tone — and the right call far more often than people think; humor is what makes a LinkedIn post actually shareable.

The Visual Director chooses A vs B vs C based on the post's tone:
- Earnest / personal SOUL → A.
- Sober / technical / a-thing-failed → B.
- Contrarian / cheeky / "I told you so" / self-deprecating → C.

Default mix target across a body of work: roughly **30% A / 30% B / 40% C**, because witty visuals dramatically outperform earnest ones in feed engagement and the current pipeline produces zero of them.

### 4. `image_gen.py` (replaces `dalle_image.py`)

Wraps the OpenAI `images.generate` endpoint with `model="gpt-image-1"`. Differences vs DALL-E 3:
- Use `size="1024x1024"` for square LinkedIn images (also supports `1536x1024` and `1024x1536`).
- `quality="high"` and `output_format="png"`.
- Response returns base64 (`b64_json`) — no second HTTP fetch needed (current DALL-E flow does an extra `httpx.get(image_url)` which can fail). Decode and write directly.
- Persist `outputs/posts/{run_id}/{seq}.png` so multiple regenerations are kept side by side. Manifest records each.

### 5. Cost tracker — real usage, not estimates

[`utils/cost_tracker.py`](src/linkedin_post_generator/utils/cost_tracker.py) currently re-tokenizes the input/output text with tiktoken and applies GPT-4o pricing — wrong for Anthropic, wrong for gpt-image-1, and underestimates cached tokens. Replace with:

- A crewAI step callback (`step_callback` on `Crew`) that reads `usage_metrics` from each agent run.
- Per-model pricing table (`core/pricing.py`) keyed by model string from `agents.yaml`.
- Image cost added per `gpt-image-1` call by size+quality.
- Returns a `CostBreakdown` per run: `{by_agent: {researcher: $, writer: $, critic: $}, image: $, total: $}`.

---

## History (file-based, lightweight)

[`utils/history.py`](src/linkedin_post_generator/utils/history.py) — append-only JSONL at `outputs/history.jsonl`. Each finalized post writes one line:

```json
{
  "run_id": "20260502_142133",
  "created_at": "2026-05-02T14:21:33Z",
  "topic": "...",
  "leader_angle": "...",
  "post_path": "outputs/posts/20260502_142133/post_final.md",
  "image_paths": ["outputs/posts/20260502_142133/01.png", ".../02.png"],
  "cost_breakdown": {...},
  "models": {"researcher": "gpt-5", "writer": "claude-opus-4-7", ...}
}
```

UI "📚 History" tab paginates the manifest, lets the user click a run to reload its post + image into the Production Studio for editing or image regen.

---

## Deployment — Fly.io

`fly.toml` defines a single VM (`shared-cpu-2x`, 2 GB RAM, region `syd`) running both API and UI.

- New unified Dockerfile (`deploy/Dockerfile`): Python 3.12-slim, uv-managed deps, Playwright/Chromium for crawl4ai (already there), `supervisord` runs uvicorn (port 8000) and `streamlit` (port 8080) inside the container.
- Fly's `[http_service]` exposes port 8080 (the UI). UI talks to API at `http://localhost:8000` inside the container — no public API exposure needed.
- Secrets via `fly secrets set OPENAI_API_KEY=… ANTHROPIC_API_KEY=… TAVILY_API_KEY=…`.
- Volume mount `/app/outputs` (1 GB) so history + generated PNGs survive deploys.
- `make deploy` → `fly deploy`. README shows a one-line deploy.

The existing `deploy/terraform/` and `deploy/deploy.sh` (EC2/SSM) become legacy — leave on disk under `deploy/legacy/` rather than delete (small disk cost, preserves git history clarity).

---

## Production polish (the things that signal "real")

- **Type hints** everywhere new; mypy in CI mode (`strict` for `core/` and `api/`, `basic` for engines/).
- **Ruff** for linting/formatting (`make fmt`).
- **pytest** suite with at least: API health, post parser round-trip, image prompt builder JSON shape, history manifest, mocked job lifecycle. Target ≥70% coverage on `api/` and `core/`.
- **Structured logging** (structlog JSON) with a `request_id` middleware so a single post run is traceable end-to-end.
- **Graceful shutdown** — FastAPI lifespan flushes in-flight jobs to JSONL with status `cancelled` rather than dropping them.
- **Rate limiting** on `/posts` and `/images` (`slowapi`, e.g. 5/min) — small, but signals the engineer thought about abuse.
- **OpenAPI docs** at `/docs` (FastAPI gives this for free) — show in README screenshot.
- **README rewrite** — top-of-file architecture diagram (mermaid), 30-second pitch, screenshots, "Try it live" Fly URL, model card, cost-per-post table.

---

## Phased rollout (so the app is never broken on `main`)

Each phase is shippable on its own. Don't merge phase N+1 until phase N runs locally.

1. **Phase 1 — backend skeleton** (no behavior change for the user):
   - Add `api/`, `core/`, `prompts/` packages.
   - Move `os.getenv` calls into `core/settings.py`.
   - Extract synthesis/writer/critic prompts from yaml/code into `prompts/*.txt`, keep yaml referencing them.
   - Add `JobStore` + `JobRunner`.
   - Wire `/health`, `/scout`, `/posts` endpoints (engine calls still synchronous internally).
   - Tests: health + parser + history.

2. **Phase 2 — UI as API client**:
   - Add `ui/streamlit_app.py` mirroring the existing 3-section flow but via `httpx`.
   - Add polling fragments.
   - Keep current `app.py` working as a fallback for one phase, then delete it at end of phase 2.

3. **Phase 3 — engine quality pass**:
   - Bump models in `agents.yaml`.
   - Rewrite Researcher emotional-beats output, tighten Writer rules.
   - Add `visual_director.py` with the JSON image-plan contract.
   - Replace `tools/dalle_image.py` with `tools/image_gen.py` (gpt-image-1).
   - Generate 5 sample posts and 5 images side-by-side (old vs new) — paste into README as proof.

4. **Phase 4 — production polish**:
   - Cost tracker rewrite (callbacks).
   - Rate limit, logging, OpenAPI polish.
   - History tab in UI.

5. **Phase 5 — deploy**:
   - Unified Dockerfile + supervisord.
   - `fly.toml`, `fly volumes create`, `fly secrets set`, `fly deploy`.
   - README screenshots + live URL.

---

## Critical files to modify or create

**Move (Phase 1 — `git mv`, no behavior change):**
- `src/linkedin_post_generator/` → `backend/`
- `backend/engines/pulse_scout.py` → `backend/scout/engine.py`
- `backend/engines/pulse_scout_modules/` → `backend/scout/modules/`
- `backend/engines/authority_crew/` → `backend/post_generator/`
- Delete the now-empty `backend/engines/` and the `src/` wrapper.
- Update every `from linkedin_post_generator...` import in the moved files to `from backend...`.

**Modify (after the move):**
- `backend/post_generator/config/agents.yaml` — model bumps, sharper Researcher Emotional Beats requirement.
- `backend/post_generator/config/tasks.yaml` — tighten Writer line rules, add the noun-from-Fact-Sheet rule across all hooks, drop the image-prompt-from-critic block (Visual Director owns it now).
- `backend/post_generator/crew.py` — add Visual Director step, wire `step_callback` for cost.
- `backend/utils/cost_tracker.py` — replace with usage-metrics-driven version.
- `pyproject.toml` — `packages = ["backend"]`; add `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `structlog`, `pytest`, `pytest-asyncio`, `slowapi`, `ruff`, `mypy`. Update `[project.scripts]` to point at `backend.main:*`.
- `deploy/Dockerfile`, `deploy/docker-compose.yml` — multi-process container (api + ui via supervisord).
- `README.md` — full rewrite (portfolio framing).

**Create:**
- `backend/api/main.py`, `backend/api/routes/{health,scout,posts,images,history}.py`, `backend/api/schemas.py`, `backend/api/errors.py`, `backend/api/deps.py`
- `backend/core/{settings,jobs,logging,pricing,paths}.py`
- `backend/post_generator/visual_director.py`
- `backend/tools/image_gen.py`
- `backend/utils/history.py`
- `backend/prompts/{scout_synthesis,post_writer,post_critic,image_prompt_builder}.txt`
- `ui/streamlit_app.py`, `ui/api_client.py`
- `tests/` — 5+ test files
- `fly.toml`, `Makefile`, `.env.example`

**Delete (at end of phase 2):**
- `app.py` (replaced by `ui/streamlit_app.py`)
- `backend/tools/dalle_image.py` (replaced by `image_gen.py`)

**Reuse as-is** (no behavior changes after the move):
- `backend/scout/modules/` — five scanners are fine.
- `backend/tools/{arxiv_search,hn_search}.py`.
- `backend/utils/user_profile.py`.

---

## Verification (how we know each phase works)

**Phase 1 — backend skeleton:**
```
make api                        # uvicorn boots on :8000
curl localhost:8000/api/v1/health      # → {"status": "ok", ...}
curl -X POST localhost:8000/api/v1/scout -d '{"modules":["technical_deep_dive"],"days":7}'
                                # → {"job_id":"...","status":"queued"}
curl localhost:8000/api/v1/scout/<id>  # → status transitions running → completed
pytest -q                       # all tests pass
```

**Phase 2 — UI as API client:**
- `make dev` boots both api + ui locally.
- Run a Pulse Scout scan from the UI; verify network tab shows only API calls (no engine import errors in Streamlit logs).
- Run a full Authority Crew job and confirm UI never blocks (progress updates every 2s).

**Phase 3 — engine quality:**
- Run the same 5 topics through old prompts vs new prompts (use a saved fixture). Manually compare:
  - Hook specificity (specific number / time-anchored present?).
  - SOUL line references a concrete artifact from Fact Sheet.
  - Banned-words count = 0.
- For each post, generate one DALL-E 3 image (old) and one gpt-image-1 image (new) with the new Visual Director plan. Side-by-side: does the new image look like a photograph that fits the post's emotion? Document in README.

**Phase 4 — polish:**
- Hit `/posts` 6 times in 60s → 6th returns 429.
- `/posts/{id}` cost field now matches OpenAI/Anthropic dashboard within ±5%.
- Kill API mid-job → JSONL shows the job marked `cancelled`, not abandoned.
- History tab shows past runs and reloads them correctly.

**Phase 5 — deploy:**
- `fly deploy` succeeds.
- `fly logs` shows structured JSON.
- Public URL renders the UI; one full post run completes end-to-end on Fly.
- `fly volumes show` confirms `outputs/` survives a redeploy.

---

## Open question to revisit during implementation

The Researcher's `## Emotional Beats` field is novel — if it produces vague output (e.g. "excitement, curiosity, hope"), tighten the prompt with a 6-word example list and a "must be specific to a practitioner pain or win" rule. Treat this as a Phase 3 review checkpoint, not a blocker.
