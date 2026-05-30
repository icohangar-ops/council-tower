# 🏛️ Council Tower Pipeline

**AI Deliberation Engine — Tower Pipeline Orchestration**

Council is a multi-agent AI deliberation system that runs structured reasoning
pipelines on the Tower platform. A council of 4 specialized AI agents debates
decisions through a rigorous 5-phase protocol, producing quality-scored
recommendations stored in Tower's Iceberg lakehouse.

## How It Works

The deliberation protocol ensures adversarial rigor:

| Phase | Description |
|-------|-------------|
| **ANALYSIS** | Each specialist agent independently analyzes the topic |
| **CHALLENGE** | The contrarian challenges all other analyses |
| **VALIDATION** | Challenged agents defend or revise their positions |
| **LOCK** | All agents commit to their final positions |
| **SUMMARY** | The summarizer synthesizes into a final recommendation |

### The Council Agents

| Agent | Role | Focus |
|-------|------|-------|
| **Ava Chen** | Financial Analyst | DCF, NPV, growth, synergies, benchmarking |
| **Marcus Webb** | Contrarian | Adversarial stress-testing, blind spots |
| **Priya Sharma** | Compliance Validator | SOX, GDPR, antitrust, regulatory gates |
| **David Kim** | Council Summarizer | Synthesis, consensus measurement, final recommendation |

## Quick Start

### Prerequisites

- Python 3.10+
- Tower CLI: `pip install -U tower`
- Tower account: [app.tower.dev](https://app.tower.dev)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Locally

```bash
python task.py --topic "Should the Federal Reserve cut interest rates?"
```

### Deploy to Tower

```bash
# Login to Tower
tower login

# Create the app (first time only)
tower apps create --name="council-deliberation"

# Set API key secret
tower secrets create --name=OPENAI_API_KEY --value="your-zhipu-api-key"

# Deploy
tower deploy

# Run with parameters
tower run --parameter=topic="Should Apple acquire NVIDIA?" --parameter=domain=finance
```

### Schedule Deliberations

```bash
# Daily market analysis at 9 AM UTC
tower schedules create --app="council-deliberation" \
    --cron="0 9 * * *" \
    --parameter=topic="Analyze today's market conditions and provide trading recommendations" \
    --parameter=domain=finance
```

## Project Structure

```
council-tower/
├── Towerfile              # Tower manifest (app config, parameters)
├── task.py                # Main pipeline entry point
├── requirements.txt       # Python dependencies
├── council/               # Core deliberation engine
│   ├── agents.py          # Agent definitions and system prompts
│   ├── deliberation.py    # 5-phase deliberation protocol
│   ├── llm.py             # LLM client (zhipu GLM-4-plus via OpenAI API)
│   └── models.py          # Data models (Post, DeliberationResult, etc.)
├── fetchers/              # External data fetchers
│   └── __init__.py        # SEC EDGAR, Yahoo Finance, news APIs
├── storage/               # Iceberg lakehouse storage layer
│   └── __init__.py        # Tower Iceberg table operations
├── dashboard/             # Marimo analytics dashboard
│   └── council_dashboard.py
└── tests/                 # Test suite
    └── test_deliberation.py
```

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────┐
│  Parameters  │────▶│  task.py         │────▶│  Council       │
│  (topic,     │     │  (Orchestrator)  │     │  Deliberation  │
│   domain)    │     └──────────────────┘     │  Engine        │
└─────────────┘              │                │                │
                             ▼                │  Phase 1:      │
                    ┌──────────────────┐      │  ANALYSIS      │
                    │  Data Fetchers   │      │  Phase 2:      │
                    │  - SEC EDGAR     │      │  CHALLENGE     │
                    │  - Yahoo Finance │      │  Phase 3:      │
                    │  - News API      │      │  VALIDATION    │
                    └──────────────────┘      │  Phase 4: LOCK │
                             │                │  Phase 5: SUMMARY│
                             ▼                └───────┬───────┘
                    ┌──────────────────┐              │
                    │  zhipu GLM-4-Plus │◀─────────────┘
                    │  (OpenAI API)     │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐     ┌───────────────┐
                    │  Tower Lakehouse  │────▶│  Marimo        │
                    │  (Iceberg Tables) │     │  Dashboard     │
                    │                   │     │               │
                    │  - deliberations  │     │  - Trends      │
                    │  - posts          │     │  - Scores      │
                    │  - analytics      │     │  - Breakdown   │
                    └──────────────────┘     └───────────────┘
```

## Tower Pipeline Features

- **Parameterized**: Topic, domain, and context are all configurable via Towerfile parameters
- **Schedulable**: Run recurring deliberations (daily market analysis, weekly strategy reviews)
- **Orchestratable**: Chain multiple council runs using `tower.run_app()`
- **Lakehouse Storage**: All results stored in Iceberg tables for analytics
- **Secrets Management**: API keys managed via Tower secrets (never in code)
- **Marimo Dashboard**: Interactive analytics on deliberation history

## Configuration

### Environment Variables / Tower Secrets

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | zhipu API key | (required) |
| `OPENAI_BASE_URL` | zhipu API base URL | `https://open.bigmodel.cn/api/paas/v4` |
| `MODEL_NAME` | LLM model name | `glm-4-plus` |
| `NEWS_API_KEY` | News API key (optional) | (none) |

### Tower Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `topic` | Deliberation topic/question | (see Towerfile) |
| `domain` | finance, strategy, or general | `finance` |
| `context` | Additional context | (empty) |
| `fetch_data` | Fetch external data | `true` |
| `output_file` | JSON output path | (none) |

## Testing

```bash
python -m pytest tests/ -v
# or
python tests/test_deliberation.py
```

## LLM Configuration

Council uses the **zhipu GLM-4-Plus** model via the OpenAI-compatible API.
The `council/llm.py` module handles all LLM communication.

For other models, set:
```bash
tower secrets create --name=OPENAI_BASE_URL --value="https://api.openai.com/v1"
tower secrets create --name=MODEL_NAME --value="gpt-4o"
```

## License

MIT
