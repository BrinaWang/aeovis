# AEO Visibility Platform — Answer Engine Evaluation Runner

A production-ready platform that evaluates how your company (Striim) appears in AI-generated answers, analyzes citations, detects website-access issues, and generates actionable recommendations to improve AI visibility and discoverability.

## What This Does

The AEO Visibility Platform answers six key questions:

1. **How often does Striim appear for important buyer questions?**
2. **Which competitors appear more frequently?**
3. **Which webpages and domains are cited?**
4. **Can AI crawlers discover and access relevant Striim pages?**
5. **Why might Striim be missing or represented incorrectly?**
6. **What action should Striim take next?**

### Core Capabilities

- **Answer Engine Evaluation** — Run buyer questions against Claude, OpenAI, Grok, and Perplexity with full cost tracking and retry/rate-limit handling
- **Response Analysis** — Extract brand mentions, positions, claims, sentiment, and citations using LLM-powered structured extraction
- **Visibility Metrics** — Calculate mention rate, recommendation rate, top-three placement, citation frequency, and competitive share of voice
- **Citation Intelligence** — Normalize URLs, classify source categories, identify most-cited pages, and detect gaps where competitors are cited but Striim isn't
- **Website Accessibility Checks** — Verify robots.txt rules, HTTP status, sitemaps, noindex directives, content extractability, and agent-context artifacts (llms.txt)
- **Request-Log Analysis** — Parse crawler activity logs, detect failures, classify user agents (crawlers vs. delegated agents), and surface access mismatches
- **Gap Detection** — Identify six types of gaps: visibility, citation, content, technical, third-party authority, and agent-experience gaps
- **Recommendations** — Generate evidence-backed, rule-based actions (technical/citation gaps) and LLM-drafted recommendations (content gaps) with priority scoring and effort estimates
- **Dashboard** — Interactive Streamlit dashboard for exploring results, running new evaluations, and tracking historical trends

## Technical Stack

**Backend**
- **Python 3.9+** — Core language
- **FastAPI** (future) — API framework
- **Pydantic** — Configuration validation and data models
- **SQLite** — Persistent storage for runs, results, gaps, and recommendations

**AI & Integration**
- **Anthropic Claude API** — Primary answer engine
- **OpenAI GPT** — Secondary engine (scaffolding)
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
  - `OPENAI_API_KEY` (OpenAI; optional)
  - `GROK_API_KEY` (xAI Grok; optional)
  - `PERPLEXITY_API_KEY` (Perplexity; optional)

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
│   ├── generator.py            # Gap-to-action workflow
│   └── approval.py             # Auto-approval scoring logic
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

### View History

```bash
python -m aeo_eval.cli history [OPTIONS]

Shows past evaluation runs with summaries.
```

### Scheduling

```bash
python -m aeo_eval.cli schedule [OPTIONS] COMMAND

Commands:
  add CRON_EXPR        Add a scheduled run (e.g., "0 9 * * MON")
  list                 Show all scheduled runs
  delete JOB_ID        Delete a scheduled run
  pause JOB_ID         Pause a scheduled run
  resume JOB_ID        Resume a paused run
```

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
- Claude (fully implemented)
- OpenAI (scaffolding ready)
- Grok (scaffolding ready)
- Perplexity (scaffolding ready)
- Mock engine for testing (no API calls)

### 4. Structured Output & Analysis
- LLM-powered extraction of brands, positions, claims, sentiment
- Confidence scores for uncertain extractions
- Rule-based and hybrid extraction approaches
- Fallback to rule-based when LLM extraction is unavailable

### 5. Website Accessibility
- robots.txt rule evaluation for multiple crawlers
- HTTP status checks and redirect tracking
- Content extractability scoring
- Agent-context artifact detection (llms.txt, markdown docs, MCP servers)
- Extractability comparison vs. cited-page benchmarks

### 6. Request-Log Analysis
- Support for multiple log formats (pluggable parsers)
- User-agent classification (AI crawlers, delegated agents, browsers, unknown)
- Failure detection (4xx, 5xx, timeouts)
- Activity aggregation by crawler and page

### 7. Gap Detection
- **Visibility gaps** — Striim mentions vs. competitors
- **Citation gaps** — Competitor pages cited, Striim pages not
- **Content gaps** — Frequently cited content more complete than Striim's
- **Technical gaps** — Striim pages blocked, missing from sitemap, noindex, errors
- **Third-party authority gaps** — External sources mention competitors but not Striim
- **Agent-experience gaps** — Extractability, gating, or llms.txt issues prevent AI discovery

### 8. Recommendations
- Rule-based actions for technical and agent-experience gaps
- LLM-drafted actions for content gaps (human approval required)
- Evidence-backed justification for every recommendation
- Priority (1-10) and effort (1-3 point) estimates
- Auto-approval for high-confidence, high-priority recommendations

### 9. Dashboard
- Visibility metrics view (mention rate, competitive share, trends)
- Prompt explorer (browse Q&A, claims, citations, gaps)
- Citation view (most-cited pages, source categories, content gaps)
- Website access view (crawler status matrix)
- Action queue (pending recommendations with status)

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
Module 6: Website Accessibility (parallel)
  - Check robots.txt rules
  - Check HTTP status, redirects, headers
  - Check content extractability
  - Check llms.txt coverage
           ↓
Module 7: Request-Log Analysis (parallel)
  - Parse logs
  - Classify crawlers
  - Detect failures
           ↓
Module 8: Gap Detection
  - Combine metrics, citations, website checks
  - Identify 6 types of gaps
  - Prioritize and deduplicate
           ↓
Module 9: Recommendations
  - Generate evidence-backed actions
  - Auto-approve high-confidence ones
  - Store for dashboard and reporting
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

### Schedule a Weekly Evaluation

```bash
python -m aeo_eval.cli schedule add "0 9 * * MON"
```

### View Past Evaluations

```bash
python -m aeo_eval.cli history
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

## Contributing

This project is in active development. Contributions welcome.

## Support

For questions, issues, or feedback:
- Check the spec.md for detailed module specifications
- Review test files for usage examples
- Open an issue on GitHub

---

**Built with Python, Pydantic, SQLite, Claude, and a passion for AI visibility.**
