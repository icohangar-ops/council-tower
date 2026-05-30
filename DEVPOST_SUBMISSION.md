# Council Tower Pipeline — DevPost Submission

---

## Inspiration

In high-stakes financial and strategic decision-making, a single AI model's output is a single point of failure. We've all seen cases where confident LLM recommendations turn out to be wrong — not because the model is inherently bad, but because no adversarial pressure was applied to its reasoning. The idea for Council came from a simple observation: real boards of directors don't reach consensus from a single analyst's report. They debate, challenge assumptions, and force each other to defend or revise their positions before committing to a decision.

We asked ourselves: what if we could replicate that adversarial deliberation process with AI agents, and what if we could run it as a repeatable, schedulable data pipeline? When we discovered Tower's Python-native orchestration platform with Iceberg lakehouse storage, we realized we had the perfect infrastructure to turn this idea into a production-ready system. Instead of building yet another chatbot wrapper, we set out to build a deliberation engine — a pipeline that treats AI reasoning as a structured, multi-phase process with built-in quality controls.

## What it does

Council Tower Pipeline is a multi-agent AI deliberation engine that runs structured reasoning pipelines on the Tower platform. It orchestrates a council of four specialized AI agents through a rigorous five-phase deliberation protocol:

**Phase 1 — ANALYSIS:** Each specialist agent independently analyzes the topic. The Financial Analyst (Ava Chen) examines DCF models, growth projections, and synergies. The Contrarian (Marcus Webb) looks for flaws in conventional wisdom. The Compliance Validator (Priya Sharma) evaluates regulatory frameworks like SOX, GDPR, and antitrust law. Each agent produces a structured analysis with a confidence score.

**Phase 2 — CHALLENGE:** The Contrarian reviews all other agents' analyses and produces targeted challenges — finding methodological flaws, overlooked risks, stress-testing key assumptions, and proposing alternative interpretations.

**Phase 3 — VALIDATION:** Each challenged agent must respond to the Contrarian's attack — acknowledging valid concerns, providing counter-evidence where the challenge is overstated, and explicitly stating whether they've adjusted their position and confidence level.

**Phase 4 — LOCK:** All agents review their full deliberation history (their own analysis, the challenge they received, their validation response) and commit to a final locked position with a hard confidence score between 0.0 and 1.0.

**Phase 5 — SUMMARY:** The Council Summarizer (David Kim) synthesizes all contributions — identifying areas of consensus, mapping disagreements, and producing a final recommendation with an overall consensus level (High/Medium/Low/None).

The result is a quality-scored deliberation record stored in Tower's Iceberg lakehouse, viewable in a Marimo analytics dashboard. Users can schedule recurring deliberations (daily market analysis, weekly strategy reviews) via Tower's scheduling system, making Council a continuously operating AI deliberation service rather than a one-off tool.

## How we built it

The project is built as a pure Python Tower pipeline with a clean modular architecture:

**Core Deliberation Engine (`council/`):** We ported our deliberation logic from TypeScript (the original Next.js Council app) into a clean Python implementation. The engine defines four agent configurations with distinct system prompts, implements the five-phase protocol as a sequential pipeline, and includes a confidence extraction system that parses LLM output for numerical confidence scores using regex patterns.

**LLM Integration (`council/llm.py`):** We use zhipu's GLM-4-Plus model via the OpenAI-compatible API. The client is abstracted behind a simple `call_llm()` function, making it trivial to swap models. Environment variable configuration means secrets never appear in code — they're injected via Tower's secrets management system.

**Data Fetchers (`fetchers/`):** We built async fetchers for SEC EDGAR filings (detecting tickers in the topic automatically), Yahoo Finance commodity prices (gold, silver, oil, copper), and news APIs. A smart `fetch_context_for_topic()` function inspects the deliberation topic for keywords and automatically fetches relevant data to enrich the agents' context.

**Lakehouse Storage (`storage/`):** Results are written to two Tower Iceberg tables — `council_deliberations` (one row per deliberation with summary metrics) and `council_posts` (one row per agent post with phase, confidence, and content). The module includes a local JSON fallback for development, making it easy to test without Tower infrastructure.

**Dashboard (`dashboard/`):** A Marimo notebook provides interactive analytics — confidence/quality trend charts, domain distribution pie charts, posts-per-deliberation histograms, and a detailed results table. It auto-detects whether it's running against Tower Iceberg or local data.

**Orchestration (`task.py` + `Towerfile`):** The Towerfile defines five parameters (topic, domain, context, fetch_data, output_file). The `task.py` entry point reads Tower parameters, fetches context data, runs the deliberation, stores results, and prints a structured summary with confidence bar charts.

## Challenges we ran into

**API compatibility:** The zhipu GLM API required careful configuration. The internal `internal-api.z.ai` endpoint worked in development but was unreachable from production environments. We had to switch to the public `open.bigmodel.cn/api/paas/v4` endpoint and discover that not all models are available on the public API (GLM-4-Flash returned errors, GLM-4-Plus works). This taught us to always validate API endpoints from the actual deployment environment, not just locally.

**Async-to-sync bridge:** Tower pipelines run synchronous Python scripts, but our data fetchers use `httpx.AsyncClient` for non-blocking HTTP calls. We resolved this with `asyncio.run()` calls at the orchestration layer, keeping the fetcher code properly async while maintaining a synchronous entry point.

**Confidence extraction reliability:** LLMs don't always output confidence in a parseable format. We implemented a cascading regex system that tries five different patterns (explicit labels, slash notation, percentage notation) with a sensible default of 0.7 when no pattern matches. This prevents pipeline failures from unexpected LLM output formatting.

**Tower SDK conditional imports:** The Tower SDK is only available when running in Tower's infrastructure. We designed the storage layer with a `HAS_TOWER` flag that gracefully falls back to local JSON files, so the entire pipeline can be developed and tested locally without any Tower dependencies.

## Accomplishments that we're proud of

We're proud of building a genuinely novel AI architecture — not a chatbot, not a RAG system, but a structured deliberation protocol that treats AI reasoning as a multi-agent adversarial process. The five-phase protocol (Analyze → Challenge → Validate → Lock → Summarize) ensures that no analysis goes unchallenged and no agent can lock a position without defending it against adversarial scrutiny.

The codebase is clean and modular — 17 files, ~2000 lines of Python with zero dependencies on the original TypeScript codebase. Every module has a single responsibility, making it easy to extend with new agents, new data sources, or new storage backends.

The Tower integration is production-ready: parameterized execution, secret management, Iceberg lakehouse storage, scheduling support, and a Marimo dashboard. This isn't a prototype — it's a pipeline that could be deployed today and run daily deliberations on financial topics.

## What we learned

Building Council on Tower taught us a lot about data pipeline architecture versus web application architecture. In a web app, you think in terms of request/response cycles. In a pipeline, you think in terms of parameterized batch jobs, data lineage, and storage layers. The Iceberg lakehouse integration was particularly enlightening — having deliberation results stored as queryable tables opens up possibilities that a simple database never could: time-series analysis of confidence trends, cross-topic pattern mining, and agent performance benchmarking.

On the AI side, we learned that the adversarial protocol produces materially different results than single-model prompting. In our tests, the Contrarian phase consistently surfaced risks that the initial analysis phase missed entirely, and the Validation phase forced analysts to either strengthen their arguments or revise their confidence downward. This "adversarial cooling" effect is exactly the kind of AI safety mechanism that production decision-making systems need.

We also learned that Tower's approach — Python scripts, TOML manifests, and Iceberg tables — is remarkably developer-friendly compared to heavier orchestration tools. The entire pipeline can be understood by reading a single `Towerfile` and one `task.py` file, which dramatically lowers the barrier to contribution.

## What's next for Council Tower Pipeline

We plan to expand Council in several directions:

**Multi-model deliberation:** Right now all agents use GLM-4-Plus. We want to enable mixed-model councils where each agent can use a different model (GLM-4-Plus for financial analysis, a different model for compliance, etc.) to maximize perspective diversity.

**Chain-of-council reasoning:** Tower's `run_app()` orchestration enables cascading deliberations — the summary from one council becomes the input topic for a second council with different agents. This creates a recursive reasoning pipeline that can handle increasingly complex multi-step decisions.

**Real-time market integration:** We'll build dedicated fetchers for SEC 10-K/10-Q full-text extraction, options chain data, and earnings call transcripts, giving agents much richer context for financial deliberations.

**Historical accuracy tracking:** By storing all deliberations in Iceberg, we can retroactively evaluate whether the council's recommendations were correct and build accuracy dashboards. This creates a feedback loop that could inform agent selection and prompt engineering.

**Agent marketplace:** We want to make it easy for users to define custom agents with their own system prompts and add them to the council. A "compliance agent for healthcare" or "a technical due diligence agent for M&A" could plug into the same deliberation protocol.

---

## Built with

**Languages:** Python 3.10+

**Frameworks & Libraries:**
- `openai` — OpenAI-compatible API client (zhipu GLM-4-Plus)
- `polars` — Fast DataFrame operations for analytics
- `pyarrow` — Arrow schema definitions for Iceberg tables
- `httpx` — Async HTTP client for data fetching
- `pydantic` — Data validation and modeling
- `marimo` — Interactive analytics dashboard

**Platform:**
- Tower (tower.dev) — Pipeline orchestration, execution, scheduling, secrets management

**Data & Storage:**
- Tower Iceberg Lakehouse — `council_deliberations` and `council_posts` tables
- Local JSON fallback for development

**LLM:**
- zhipu GLM-4-Plus via OpenAI-compatible API (`open.bigmodel.cn/api/paas/v4`)

**Data Sources:**
- SEC EDGAR API — Filing search and retrieval
- Yahoo Finance — Commodity price data (gold, silver, oil, copper)
- News API — Market news aggregation

**Dashboards:**
- Marimo — Interactive Python notebooks for analytics

**Testing:**
- Python built-in `unittest` — 6 tests covering models, agents, confidence extraction, protocol phases, prompt templates, and storage

---

## Try it out links

- **GitHub (zan-maker):** https://github.com/zan-maker/council-tower
- **GitHub (Cubiczan):** https://github.com/Cubiczan/council-tower
- **Codeberg:** https://codeberg.org/cubiczan/council-tower

## Video demo

(Upload your 3-minute video to YouTube and paste the link here)
