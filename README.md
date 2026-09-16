# AEO Visibility Platform — Answer Engine Evaluation Runner

A platform that evaluates how Striim appears in AI-generated answers, analyzes citations, detects website-access issues, and generates  recommendations to improve AI visibility and discoverability.

## What This Does

The AEO Visibility Platform answers six key questions:

1. **How often does Striim appear for important buyer questions?**
2. **Which competitors appear more frequently?**
3. **Which webpages and domains are cited?**
4. **Can AI crawlers discover and access relevant Striim pages?**
5. **Why might Striim be missing or represented incorrectly?**
6. **What action should Striim take next?**

### Core Capabilities

- **Answer Engine Evaluation** — Run buyer questions against Claude or OpenAI with full cost tracking and retry/rate-limit handling (Gemini, Grok and Perplexity have config sections but no engine implementation yet)
- **Response Analysis** — Extract brand mentions, positions, claims, sentiment, and citations using LLM-powered structured extraction
- **Visibility Metrics** — Calculate mention rate, recommendation rate, top-three placement, citation frequency, and competitive share of voice, overall and by topic
- **Citation Intelligence** — Normalize URLs, classify source categories, identify most-cited pages, and detect gaps where competitors are cited but Striim isn't
- **Website Accessibility Checks** — Verify robots.txt rules per crawler, HTTP status, noindex directives, canonical URLs, and content extractability (sitemap and llms.txt checks are not implemented yet)
- **Request-Log Analysis** — Library code to parse JSONL crawler logs, classify user agents (crawlers vs. delegated agents), and normalize them for storage; not yet wired into the CLI or pipeline
- **Gap Detection** — Identify visibility gaps and citation gaps per topic (content, technical, third-party authority, and agent-experience gaps are specified but not implemented)
- **Recommendations** — For every gap, an LLM-drafted article recommendation plus Reddit/LinkedIn/Facebook social recommendations grounded in the run's evidence, with a template fallback when no LLM is available, priority scoring, effort estimates, and a cost budget
- **Dashboard** — Interactive Streamlit dashboard for exploring results, running new evaluations, approving recommendations, and tracking historical trends

For the implementation-level view (control flow, formulas, schema, decisions, and known sharp edges) see [architecture.md](architecture.md).

## Technical Stack

**Backend**
- **Python 3.9+** — Core language
- **FastAPI** (future) — API framework
- **Pydantic** — Configuration validation and data models
- **SQLite** — Persistent storage for runs, results, gaps, and recommendations

**AI & Integration**
- **OpenAI GPT** — Answer Engine
- **Anthropic Claude API** - Answer Engine
- **HTTPx** — Async HTTP client for crawler simulation and content fetching
- **Beautiful Soup 4** — HTML parsing and extraction
- **Trafilatura** — Main content extraction for web pages

**Scheduling & Processing**
- **APScheduler** — Job scheduling with cron expressions
- **urllib.robotparser** — robots.txt rule matching

**Dashboard & Visualization**
- **Streamlit** — Interactive web dashboard
- **Plotly** — Interactive charts and graphs
- **Pandas** — Data manipulation and analysis

**Testing & Quality**
- **pytest** — Test framework
- **pytest-asyncio** — Async test support
- **freezegun** — Time mocking
- **pytest-mock** — Mocking utilities

See `pyproject.toml` for the complete dependency list.

## Quick Start

### Prerequisites

- **Python 3.9 or higher**
- **API Keys** for at least one provider:
  - `ANTHROPIC_API_KEY` (Anthropic Claude)
  - `OPENAI_API_KEY` (OpenAI)
  - `GROK_API_KEY` (xAI Grok)
  - `PERPLEXITY_API_KEY` (Perplexity)

### 1. Clone and Install

```bash
git clone <repo>
cd aeovis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e .[dev]
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and any other API keys
```

Alternatively, set environment variables directly:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3. Run Your First Evaluation

**Quick test with mock engine (no API calls):**
```bash
python -m aeo_eval.cli run --engine mock --limit 5
```

**Run with Claude:**
```bash
python -m aeo_eval.cli run --engine claude --limit 5
```

**Estimate cost without running:**
```bash
python -m aeo_eval.cli run --engine claude --dry-run --limit 10
```

**Filter by topic:**
```bash
python -m aeo_eval.cli run --engine claude --topic "Oracle CDC" --limit 20
```

**Show verbose output:**
```bash
python -m aeo_eval.cli run --engine claude --verbose --limit 5
```

### 4. View Results in Dashboard

```bash
streamlit run streamlit_app.py
```

The dashboard will open at `http://localhost:8501`. You can:
- View visibility metrics and competitor comparisons
- Run new evaluations with custom filters
- Explore individual prompts and answers
- Review detected gaps and recommendations
- Compare results across runs

Alternatively, use the dashboard script:
```bash
bash scripts/dashboard.sh
```

### 5. Run Tests

```bash
pytest tests/ -v

# Run specific test module
pytest tests/test_config.py -v

# Run with coverage
pytest tests/ --cov=aeo_eval
```

## Project Structure

```
aeo_eval/
├── __init__.py
├── cli.py                      # CLI entry point (run, history, schedule)
├── config.py                   # Configuration system (Pydantic + YAML)
├── orchestrator.py             # Full pipeline orchestration
├── scheduler.py                # APScheduler integration
│
├── engine/                      # Module 2: Answer Engine Runner
│   ├── base.py                 # BaseEngine abstract class
│   ├── mock_engine.py          # MockEngine for testing
│   ├── claude_engine.py        # Claude API implementation
│   ├── openai_engine.py        # OpenAI API implementation (scaffolding)
│   ├── retry.py                # Retry logic with exponential backoff
│   ├── rate_limiter.py         # Token bucket rate limiter (TPM/RPM)
│   └── factory.py              # Engine factory
│
├── analysis/                    # Module 3: Response Analysis
│   ├── extractor.py            # Brand/claim extraction (rule-based)
│   └── llm_extractor.py        # LLM-powered structured extraction
│
├── metrics/                     # Module 4: Visibility Metrics
│   └── calculator.py           # Mention rate, citation rate, competitive share
│
├── citations/                   # Module 5: Citation Intelligence
│   ├── normalizer.py           # URL normalization and canonicalization
│   ├── deduplicator.py         # Citation deduplication and classification
│   └── classifier.py           # Source category classification
│
├── website_accessibility/       # Module 6: Website & Crawler Checks
│   ├── robots_checker.py       # robots.txt rule evaluation
│   ├── http_checker.py         # HTTP status, redirects, headers
│   ├── extractability.py       # Content extractability analysis
│   └── checker.py              # Orchestrator for all checks
│
├── request_logs/                # Module 7: Request-Log Analysis
│   ├── parser.py               # Log parsing and normalization
│   ├── classifier.py           # User-agent classification (crawlers vs agents)
│   └── analyzer.py             # Failure detection, activity aggregation
│
├── gaps/                        # Module 8: Gap Detection
│   ├── detector.py             # Identifies 6 gap types
│   └── thresholds.py           # Configurable gap thresholds
│
├── recommendations/             # Module 9: Recommendations & Auto-Approval
│   ├── generator.py            # Gap-to-action workflow with LLM & template paths
│   ├── approval.py             # Auto-approval scoring logic
│   └── rag.py                  # RAG system for methods context retrieval
│
├── runner/
│   └── evaluator.py            # Evaluator: runs prompts, tracks cost
│
├── storage/
│   └── sqlite_store.py         # SQLite schema and query layer
│
├── models/
│   ├── prompt.py               # Prompt dataclass
│   ├── result.py               # RunResult, EvaluationRun dataclasses
│   └── analysis.py             # Analysis result models
│
├── dashboard/
│   └── app.py                  # Streamlit dashboard
│
├── data/
│   └── prompt_loader.py        # Load questions from JSON
│
└── demo/
    └── report.py               # Demo report generation

config.yaml                      # Configuration file (providers, evaluation settings)
.env.example                     # Environment variable template
question.json                    # Buyer question dataset (~75 questions)
personas.json                    # User personas
data/eval_runs.db              # SQLite database (auto-created on first run)

tests/                           # Comprehensive test suite
├── test_config.py
├── test_retry_logic.py
├── test_rate_limiter.py
├── test_evaluator_cost.py
├── test_claude_engine.py
├── test_extractor.py
├── test_storage.py
└── ... (20+ test modules)

scripts/
├── dashboard.sh                # Streamlit launcher script
└── demo.sh                     # Demo runner script
```

## Configuration

### config.yaml

Define your providers, retry behavior, evaluation parameters, and crawlers:

```yaml
providers:
  claude:
    model_name: "claude-opus-5"
    rate_limit_tpm: 150000
    rate_limit_rpm: 100
    cost_per_1k_input_tokens: 0.003
    cost_per_1k_output_tokens: 0.015
  openai:
    model_name: "gpt-4o"
    rate_limit_tpm: 200000
    rate_limit_rpm: 500

retry_policy:
  max_retries: 3
  initial_delay_ms: 100
  backoff_factor: 2.0
  max_delay_ms: 30000

general:
  cost_limit_per_run: 35.0
  question_json_path: "question.json"
  output_db_path: "data/eval_runs.db"
  log_level: "INFO"

evaluation:
  competitors: [Fivetran, Oracle GoldenGate, Qlik Replicate, Confluent, AWS DMS, Estuary]
  important_striim_pages:
    - "https://www.striim.com/product/"
    - "https://www.striim.com/solutions/"
    - "https://www.striim.com/docs/"
  crawlers:
    - OAI-SearchBot
    - PerplexityBot
    - Claude-SearchBot
    - Googlebot
    - Bingbot

scheduling:
  timezone: "US/Eastern"
  default_schedule: "0 9 * * MON"  # 9am Monday
```

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional: Other API providers
OPENAI_API_KEY=sk-...
GROK_API_KEY=...
PERPLEXITY_API_KEY=pplx-...

# Optional: Override config paths
CONFIG_PATH=config.yaml
QUESTION_PATH=question.json
OUTPUT_DB_PATH=data/eval_runs.db
LOG_LEVEL=INFO
```

## CLI Commands

### Run Evaluation

```bash
python -m aeo_eval.cli run [OPTIONS]

Options:
  --engine {mock,random-mock,claude,openai}    Answer engine to use
  --limit N                                     Only run N prompts
  --topic "Oracle CDC"                         Filter by topic
  --persona "Data Architect"                   Filter by persona
  --priority {High,Medium,Low}                 Filter by priority
  --dry-run                                    Estimate cost without running
  --cost-limit 50.0                            Override cost limit
  --db /path/to/eval_runs.db                   Override database path
  --notes "description"                        Add notes to run
  --log-level {DEBUG,INFO,WARNING,ERROR}       Logging verbosity
```

### Report

```bash
python -m aeo_eval.cli report RUN_ID [--db PATH]

Prints a plain-text summary (metrics by topic, gaps, approved recommendations) for one run.
```

### History and Scheduling

`python -m aeo_eval.cli history` and `python -m aeo_eval.cli schedule` are stubs that print "not yet implemented". Past runs are visible in the dashboard's run selector, and `aeo_eval/scheduler.py` contains an APScheduler wrapper that is not yet wired to the CLI.

## Key Features

### 1. Cost Tracking
- Real token counting from API responses
- Per-prompt and batch cost totals
- Cost limit enforcement with early stopping
- Dry-run mode to estimate cost before running

### 2. Retry & Rate Limiting
- Automatic retry on transient failures (timeout, rate-limit)
- Exponential backoff with jitter to prevent thundering herd
- Token-per-minute (TPM) and request-per-minute (RPM) limiting
- Per-provider configuration

### 3. Multi-Engine Support
- Claude (fully implemented; also the default analyzer for Module 3 and the recommendation engine)
- OpenAI (fully implemented)
- Gemini, Grok, Perplexity (config sections and API-key wiring only; no engine class yet)
- Mock engines for testing (`mock`, `random-mock`; no API calls)

### 4. Structured Output & Analysis
- LLM-powered extraction of brands, positions, claims, sentiment
- Confidence scores for uncertain extractions
- Rule-based and hybrid extraction approaches
- Fallback to rule-based when LLM extraction is unavailable

### 5. Website Accessibility
- robots.txt rule evaluation for multiple crawlers (fail-open when robots.txt is unreachable)
- HTTP status checks with redirect following, noindex and canonical detection
- Content extractability scoring (trafilatura word count and text-to-HTML ratio)
- Optional in the pipeline (`evaluation.run_website_accessibility_checks`) and runnable standalone from the dashboard
- Not yet implemented: sitemap membership, llms.txt detection, JS-render detection

### 6. Request-Log Analysis
- JSONL log parser with required-field validation and a 90-day window
- User-agent classification (AI crawlers, delegated agents, search crawlers, browsers, unknown)
- Edge-action mapping from status codes (allowed, blocked, rate-limited, error)
- Library only: no CLI flag or pipeline step ingests logs yet; the dashboard's Request Logs view shows rows written by the `random-mock` engine

### 7. Gap Detection
- **Visibility gaps** — Striim mention rate below the topic's priority threshold, or a competitor above 2× Striim
- **Citation gaps** — A topic with three or more competitor citations and none for Striim
- Each gap records the affected question ids, which the recommendation prompts use as evidence
- Specified but not implemented: content, technical, third-party authority, and agent-experience gaps

### 8. Recommendations System
- **Gap-to-action workflow** — Every detected gap fans out into evidence-backed recommendations
- **Two generation paths** — LLM-enhanced (Claude diagnosis + article + multi-platform social recs) and template fallback for when LLM is unavailable
- **Priority & confidence scoring** — Recommendations inherit gap-level confidence; priority ranges 1–10 based on gap severity and Striim visibility
- **Auto-approval logic** — High-confidence, high-priority recommendations (priority ≥8) auto-advance from draft to approved
- **Full audit trail** — All recommendations track approval status, reviewer, timestamp, and implementation steps
- **Platform-specific outputs** — Social media recommendations (Reddit, LinkedIn, Facebook) with engagement strategies; article recommendations with structured implementation steps
- **LLM cost tracking** — Every structured output call (diagnosis, article generation, social generation) tracked and folded into run totals

For full technical details on architecture, LLM integration, RAG system, database schema, and known issues, see [docs/recommendations-architecture.md](docs/recommendations-architecture.md).

### 9. Dashboard
- Visibility metrics strip and by-topic breakdown, 30-day visibility and cost trends
- Gaps & Recommendations, Citation Analysis, Run Comparison, and Trends tabs per run
- Recommendations Management tab: edit, approve, or reject with a reason
- Cost Analysis page with daily budget status and editable cost limits
- Module 6 Checks page for running and reviewing website accessibility checks
- Configure & Run panel that launches a pipeline run in the background with live progress

## Data Flow (Modules 2–9)

```
Buyer Questions & Competitor List
           ↓
Module 2: Run Engine
  - Load prompts
  - Execute through answer engine (with retry/rate-limit)
  - Track cost and latency
           ↓
Module 3: Response Analysis
  - Extract Striim mentions and positions
  - Extract competitor mentions
  - Extract claims, sentiment, citations
           ↓
Module 4: Visibility Metrics
  - Calculate mention rate, citation rate, top-3 placement
  - Visibility by topic, persona, engine, time
           ↓
Module 5: Citation Intelligence
  - Normalize URLs
  - Classify sources (Striim-owned, competitor, third-party, etc.)
  - Deduplicate and count citations
           ↓
Module 6: Website Accessibility (optional, config-gated)
  - Check robots.txt rules per crawler
  - Check HTTP status, redirects, noindex, canonical
  - Check content extractability
           ↓
Module 8: Gap Detection
  - Visibility gaps from by-topic metrics
  - Citation gaps from run-scoped citation occurrences
  - Record affected question ids as evidence
           ↓
Module 9: Recommendations
  - Diagnose each gap and draft an article brief + social plans (Claude), within a cost budget
  - Template fallback when no LLM is available or the budget is spent
  - Auto-approve high-confidence, high-priority ones
  - Store for dashboard and reporting

(Module 7, request-log analysis, is library code not yet run by the pipeline.)
           ↓
Dashboard & Historical Comparison
  - Display findings
  - Compare across multiple runs
```

## Testing

The project includes comprehensive tests covering:
- Configuration validation
- Retry logic and exponential backoff
- Rate-limit enforcement (TPM/RPM)
- Cost calculation accuracy
- Claude API integration (mocked)
- Brand extraction and claim detection
- URL normalization and deduplication
- Database schema and queries
- Gap detection thresholds
- Recommendation generation

Run all tests:
```bash
pytest tests/ -v
```

Run specific test file:
```bash
pytest tests/test_config.py -v
```

Run with coverage:
```bash
pytest tests/ --cov=aeo_eval --cov-report=html
```

## Common Tasks

### Run a Limited Set of Questions

```bash
python -m aeo_eval.cli run --engine claude --limit 10
```

### Run Only High-Priority Questions

```bash
python -m aeo_eval.cli run --engine claude --priority High --limit 20
```

### Run Oracle CDC Topic Only

```bash
python -m aeo_eval.cli run --engine claude --topic "Oracle CDC"
```

### Estimate Cost Without Running

```bash
python -m aeo_eval.cli run --engine claude --dry-run --limit 50
```

### Print a Report for a Run

```bash
python -m aeo_eval.cli report <run_id>
```

## Troubleshooting

### "Claude engine not available"
```bash
pip install -e .[dev]
```

### "Cost limit exceeded"
- Increase `cost_limit_per_run` in config.yaml or use `--cost-limit 50` in CLI
- Use `--dry-run` first to estimate cost

### "Rate limited"
- The engine will automatically retry with exponential backoff
- Check `rate_limit_tpm` and `rate_limit_rpm` in config.yaml for your provider
- Adjust rate limits if needed

### "Tests failing"
```bash
pytest tests/ -vv
```
- Some tests mock the Anthropic API; no real API calls should be made
- Check that test database (`data/eval_runs.db`) has write permissions

### "Database locked"
- SQLite is in use by another process
- Check if dashboard is running in another terminal
- The database is designed for single-writer (evaluator) + multiple readers (dashboard)

### "Dashboard won't start"
```bash
streamlit run streamlit_app.py --logger.level=debug
```

## Architecture Decisions

- **SQLite** — Simple, deployable, perfect for 240 evals/year with 1-year retention
- **Pydantic** — Type-safe config with validation and helpful errors
- **Structured LLM Output** — JSON mode ensures parseable extraction, fallback to rules
- **Rule-Based for Technical** — robots.txt, HTTP checks, extractability don't need LLM
- **LLM for Content** — Claims, sentiment, content gaps benefit from LLM reasoning
- **Evidence-Based** — All gaps and recommendations tied to specific evidence IDs

## Future Work

- **API Server** — FastAPI wrapper for programmatic access
- **Multi-Run Comparison** — Trend analysis and confidence bands
- **Claim Verification** — Cross-reference with Striim docs
- **Content Generation** — Auto-draft content briefs from gaps
- **IP/DNS Verification** — Verify crawler identity from logs
- **Referral Traffic** — Track AI-driven traffic from specific engines
- **Slack/Email Summaries** — Automated reporting
- **UI Polish** — Streamlit dashboard enhancements
