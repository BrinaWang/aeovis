# AEO Visibility Platform — Implementation Architecture

*Reflects the code on `main` as of 2026-09-16, after the bug-fix pass described in §19. Test suite: 278 passing.*

This document is the implementation-level companion to `README.md`. The README tells you *what* the platform does; this tells you *how every part of it works*, which decisions shaped it, and where the sharp edges are. It is written so that someone who has read the README and nothing else can open any file in `aeo_eval/` and already know what they will find, why it is there, and what depends on it.

Conventions used below:

- `path/to/file.py:name` names a symbol. Line numbers are avoided because they rot.
- "Module N" refers to the numbered modules from `spec.md` (Module 2 = answer-engine runner, 3 = response analysis, 4 = metrics, 5 = citations, 6 = website accessibility, 7 = request logs, 8 = gaps, 9 = recommendations). The package layout mirrors these numbers.
- A **run** is one execution of the pipeline over a batch of prompts. Its identifier is `evaluation_runs.run_id`, generated as a UUID4 by `Evaluator` (`run_batch_id`). Everything downstream is keyed by it.

---

## Table of contents

1. [Runtime topology and entry points](#1-runtime-topology-and-entry-points)
2. [Repository layout](#2-repository-layout)
3. [Configuration system](#3-configuration-system)
4. [Data model](#4-data-model)
5. [The pipeline, stage by stage](#5-the-pipeline-stage-by-stage)
6. [Engine layer](#6-engine-layer)
7. [Module 3: response analysis](#7-module-3-response-analysis)
8. [Module 4: visibility metrics](#8-module-4-visibility-metrics)
9. [Module 5: citation intelligence](#9-module-5-citation-intelligence)
10. [Module 8: gap detection](#10-module-8-gap-detection)
11. [Module 9: recommendations](#11-module-9-recommendations)
12. [Module 6: website and crawler accessibility](#12-module-6-website-and-crawler-accessibility)
13. [Module 7: request-log analysis](#13-module-7-request-log-analysis)
14. [Storage layer](#14-storage-layer)
15. [Dashboard](#15-dashboard)
16. [CLI and scheduler](#16-cli-and-scheduler)
17. [Testing](#17-testing)
18. [Key design decisions and their consequences](#18-key-design-decisions-and-their-consequences)
19. [Known sharp edges and inconsistencies](#19-known-sharp-edges-and-inconsistencies)
20. [Extension recipes](#20-extension-recipes)
21. [Glossary](#21-glossary)

---

## 1. Runtime topology and entry points

There is no server. The platform is a Python package (`aeo_eval`) plus a SQLite file, driven by one of three front doors that all converge on the same object:

```
python -m aeo_eval.cli run ...      streamlit run streamlit_app.py       ScheduleManager (APScheduler)
        │                                    │                                   │
        │ cli.cmd_run                        │ dashboard.app.run_evaluation      │ scheduler._run_scheduled_job
        │                                    │ (daemon thread)                   │   └─ builds argparse.Namespace
        │                                    │                                   │      and calls cli.cmd_run
        ▼                                    ▼                                   ▼
             AEOPipelineOrchestrator(engine, {"db_path", "cost_limit_per_run"}).run_full_pipeline(prompts, RunOptions)
                                                      │
                                                      ▼
                                       SQLite file  data/eval_runs.db
                                                      ▲
                                                      │  read-only queries (one connection per call)
                                       Streamlit dashboard views
```

**Process model.** A CLI run is a single process. Inside it, `Evaluator.run_batch` fans prompts out over a `ThreadPoolExecutor(max_workers=min(4, n))`; everything after evaluation (metrics, citations, gaps, recommendations) is sequential on the main thread. The dashboard is one Streamlit process; when you press *Start Evaluation* it starts the same orchestrator on a `threading.Thread(daemon=True)` so the page keeps rendering, and polls the database every 4 seconds for progress. Nothing else is concurrent.

**Where state lives.** Everything durable is in the SQLite database at `config.general.output_db_path` (default `data/eval_runs.db`, git-ignored). In-memory state is limited to Streamlit `st.session_state` and the scheduler's job dict. There is no cache layer, no queue, no message bus.

**Network egress.** Only three kinds of outbound calls exist: answer-engine/analyzer API calls (Anthropic or OpenAI SDKs), Module 6 HTTP fetches of Striim pages and `robots.txt` (httpx + `urllib.robotparser`), and nothing else. Module 7 reads local files.

---

## 2. Repository layout

```
aeo_eval/
├── cli.py                      argparse front door: run | history | schedule | report
├── config.py                   Pydantic config + PROVIDERS registry + module-level `config` singleton
├── orchestrator.py             AEOPipelineOrchestrator.run_full_pipeline — the pipeline
├── scheduler.py                ScheduleManager (APScheduler wrapper, not wired to CLI yet)
├── models/                     dataclasses only; no logic
│   ├── prompt.py               Prompt (+ three legacy, unused shapes)
│   ├── result.py               RunResult (one answer), EvaluationRun (one batch)
│   └── analysis.py             ResponseAnalysisOutput, LLMExtractionOutput, Claim, BrandMention, StructuredCallResult
├── data/prompt_loader.py       question.json -> List[Prompt]
├── engine/                     Module 2 provider adapters
│   ├── base.py                 BaseEngine contract + cost/retry/rate-limit plumbing
│   ├── factory.py              create_engine(name) via PROVIDERS
│   ├── claude_engine.py        Anthropic Messages API (answers + json_schema structured output)
│   ├── openai_engine.py        OpenAI chat completions (answers + strict json_schema)
│   ├── mock_engine.py          MockEngine, RandomMockEngine (offline; also fabricates Module 6/7 rows)
│   ├── retry.py                RetryPolicy (classification + backoff math), RetryManager
│   └── rate_limiter.py         Dual token bucket (TPM + RPM)
├── runner/evaluator.py         Module 2+3 runner: CostTracker, RunOptions, Evaluator
├── analysis/                   Module 3
│   ├── extractor.py            extract_response (hybrid rules + LLM)
│   └── llm_extractor.py        EXTRACTION_SCHEMA, prompt builder, extract_with_claude
├── metrics/calculator.py       Module 4 MetricsCalculator (overall + by_topic)
├── citations/                  Module 5
│   ├── normalizer.py           normalize_url, extract_domain
│   ├── classifier.py           classify_source -> 9 categories
│   └── deduplicator.py         CitationDeduplicator.process_citations_from_run
├── website_accessibility/      Module 6
│   ├── robots_checker.py       urllib.robotparser with per-domain cache, fail-open
│   ├── http_checker.py         httpx GET, noindex/canonical parsing, per-domain 0.5 rps
│   ├── extractability.py       trafilatura text ratio + word count
│   └── checker.py              WebsiteAccessibilityChecker.check_pages + _classify_result
├── request_logs/               Module 7 (library only; not called by the pipeline)
│   ├── parser.py               JSONL -> normalized records, 90-day window
│   ├── classifier.py           user-agent -> {known_ai_crawler, delegated_agent, search_crawler, human_browser, unknown}
│   └── analyzer.py             records -> crawler_logs rows (edge_action mapping)
├── gaps/                       Module 8
│   ├── thresholds.py           should_flag_visibility_gap, calculate_gap_priority
│   └── detector.py             GapDetector (visibility + citation gaps)
├── recommendations/            Module 9
│   ├── generator.py            RecommendationGenerator: budget gate, evidence builder, 3 LLM prompts + schemas, templates
│   ├── rag.py                  MethodsRAG: methods.txt chunker + BM25 retrieval over method_sections
│   └── approval.py             should_auto_approve + pure-dict helpers
├── storage/
│   ├── sqlite_schema.sql       All DDL (IF NOT EXISTS) + retention policy seed rows
│   └── sqlite_store.py         SQLiteStore (connection-per-call DAO), resolve_sqlite_target, apply_retention
├── dashboard/
│   ├── app.py                  Streamlit app: fetch_* queries, render_* views, main()
│   ├── formatting.py           pure display helpers (effort/platform badges, paragraph splitting, step normalisation)
│   └── progress.py             fetch_run_progress / describe_progress for the background-run banner
└── demo/report.py              print_run_summary for `cli report`

streamlit_app.py                sys.path shim -> aeo_eval.dashboard.app.main
config.yaml                     live config (providers, limits, competitors, crawlers, pages)
question.json                   75 buyer questions; personas.json describes the 6 personas
methods.txt                     AEO methodology corpus consumed by the RAG layer
scripts/                        dashboard.sh, demo.sh, migrate_add_run_id.py (one-off migration)
tests/                          272 tests; layout mirrors aeo_eval/
docs/                           dashboard-guide.md, recommendations-architecture.md, superpowers/ (design + plan history)
skills/striim-aeo/              portable Claude skill built from this repo (not imported by the code)
```

---

## 3. Configuration system

`aeo_eval/config.py` builds one `Config` object at import time and every other module reads `from aeo_eval.config import config`. Because it is a module singleton, it is loaded exactly once per process and shared by the CLI, the orchestrator, the engines, and the dashboard.

### 3.1 Resolution order

1. If `CONFIG_PATH` is set, that file; otherwise `<repo>/config.yaml`.
2. If the file does not exist, `Config()` with pure Pydantic defaults.
3. If parsing or validation raises, a warning is printed and defaults are used (the process does **not** abort).
4. The `providers` field has a `mode="before"` validator, `inject_api_keys`, that overlays environment variables onto the raw dict before model construction:

   | provider key | env var |
   |---|---|
   | `claude` | `ANTHROPIC_API_KEY` |
   | `openai` | `OPENAI_API_KEY` |
   | `gemini` | `GOOGLE_API_KEY` |
   | `grok` | `GROK_API_KEY` |
   | `perplexity` | `PERPLEXITY_API_KEY` |

   The overlay only fires for providers that already have a section in the incoming dict, so an env var for a provider not listed in `config.yaml` (and not in the defaults) is silently ignored. `.env` is loaded by `python-dotenv` at the top of `cli.py` and again by the dashboard (which searches repo root, its parent, and CWD) **before** `aeo_eval.config` is imported, which is what makes the overlay see the keys.

`Config.from_env()` exists but nothing calls it. `QUESTION_PATH` and `OUTPUT_DB_PATH` are exported as module constants for legacy callers; they are just aliases of `config.general.*`.

### 3.2 The models and what actually reads them

| Section / field | Default | `config.yaml` value | Consumers |
|---|---|---|---|
| `providers.<name>.model_name` | `claude-opus-5` | claude: `claude-sonnet-5` | engine `__init__` |
| `providers.<name>.rate_limit_tpm` / `_rpm` | 150000 / 100 | 150000 / 100 | `BaseEngine.get_rate_limiter_config` |
| `providers.<name>.timeout_seconds` | 60 | claude: 300 | engine SDK calls |
| `providers.<name>.cost_per_1k_input_tokens` / `_output_tokens` | 0.003 / 0.015 | claude: 0.002 / 0.01 | `BaseEngine.get_token_costs` |
| `providers.<name>.max_tokens` | 8000 (min 1000) | claude: 8000 | `ClaudeEngine.run_with_structured_output` **only** (answers use a hardcoded 2000); also the recommendation budget estimator |
| `providers.<name>.max_retries` | None → 3 | unset | `BaseEngine.get_retry_policy` |
| `retry_policy.*` | 3 / 100ms / 2.0 / 30000ms | same | **not read by any code path** (see §19); `RetryPolicy` dataclass defaults happen to match |
| `general.cost_limit_per_run` | 35.0 | 5.0 | `Evaluator` (via pipeline config), orchestrator budget carry-over, dashboard |
| `general.cost_limit_per_day` | 100.0 | 7.0 | orchestrator daily check, dashboard budget card |
| `general.question_json_path` | `<repo>/question.json` | `question.json` | CLI, dashboard |
| `general.output_db_path` | `<repo>/data/eval_runs.db` | `data/eval_runs.db` | everywhere a DB path is defaulted |
| `evaluation.competitors` | 6 names | 6 names | Module 3 brand detection via `runner/evaluator.py:competitors_to_track()` (falls back to `DEFAULT_COMPETITORS` only if the list is empty) |
| `evaluation.important_striim_pages` | 3 URLs | 4 URLs | Module 6 in pipeline; dashboard Module 6 defaults |
| `evaluation.crawlers` | 5 UAs | 9 UAs | Module 6 in pipeline; dashboard Module 6 defaults |
| `evaluation.run_website_accessibility_checks` | False | unset → False | orchestrator step 2.5 gate |
| `evaluation.enabled_topics` / `enabled_personas` | None | unset | nothing |
| `scheduling.*` | US/Eastern, `0 9 * * MON` | same | nothing (scheduler is not wired) |

`Config` has `extra="allow"`, so unknown top-level YAML sections do not fail validation.

### 3.3 Mutability at runtime

The dashboard's Cost view writes `config.general.cost_limit_per_day/per_run` in memory **and** rewrites `config.yaml` via `yaml.dump` (which re-serialises the whole file, dropping comments). The CLI's `--cost-limit` flag overrides only the per-run value for that invocation by passing it in the pipeline config dict; it never touches the singleton.

---

## 4. Data model

### 4.1 In-memory models (`aeo_eval/models/`)

All are plain `@dataclass`es with no behaviour beyond two properties.

**`Prompt`** — one question. `id` is the join key to `prompts` and `raw_responses.prompt_id`; `topic` drives by-topic metrics and gaps; `priority` (lower-case in the dataset) drives gap thresholds.

**`RunResult`** — one answer to one prompt from one engine. Constructed by the engine with placeholder `prompt_id=""` and `run_batch_id=""`; the evaluator stamps `prompt_id`, `run_batch_id`, `run_type`, `engine_name`, `run_timestamp` before persisting. `status` is one of `success | failed | rate_limited | timeout | dry_run | cost_limit_exceeded`. `actual_cost` is computed from real token counts; `estimated_cost` is a deprecated field only populated for dry runs. The evaluator also sets a dynamic attribute `result.analysis` (the Module 3 dict) that is not declared on the dataclass. Only the columns of `raw_responses` are persisted; `run_type`, `engine_name`, `run_timestamp`, `estimated_cost` are in-memory only.

**`EvaluationRun`** — batch summary. `run_id == Evaluator.run_batch_id`. `total_cost` is `CostTracker.spent` (engine + analyzer spend). `filters_applied` is persisted as JSON in `evaluation_runs.filters`; `run_notes`, `run_type`, `total_input_tokens`, `total_output_tokens` are **not** persisted at batch level (token totals exist per response only).

**`ResponseAnalysisOutput`** — the row shape for `response_analysis`. `brands_found`, `claims`, `citations` are already-serialised JSON strings at this layer.

**`LLMExtractionOutput`** / `BrandMention` / `Claim` — the typed view of the Module 3 LLM response, built in `llm_extractor.extract_with_claude`.

**`StructuredCallResult`** — `{data, input_tokens, output_tokens, cost}` returned by every `run_with_structured_output`. When the engine could not parse JSON, `data == {"raw_response": <text>}`; callers check for that key.

`Citation`, `EngineResponse`, `ExtractionResult` in `prompt.py` are legacy and unused.

### 4.2 SQLite schema (`storage/sqlite_schema.sql`)

Thirteen tables. Foreign keys are declared and `PRAGMA foreign_keys = ON` is issued on every write connection, so parent rows must exist first and cannot be deleted while children remain.

```
prompts ──────────────┐ (prompt_id, no FK)
                      ▼
evaluation_runs ─1:N─ raw_responses ─1:1─ response_analysis ─1:N─ citation_occurrences ─N:1─ citations
      │                                                                                      (global, upsert by normalized_url)
      ├─1:N─ visibility_metrics   (dimension = overall | by_topic)
      ├─1:N─ gaps ─1:N─ recommendations
      ├─1:N─ website_checks       (Module 6; FK to evaluation_runs is enforced — see §19 for the standalone-dashboard consequence)
      └─1:N─ crawler_logs         (Module 7; only RandomMockEngine writes these today)

method_sections            RAG corpus derived from methods.txt (rebuilt every generator construction)
recommendation_templates   CRUD exists in SQLiteStore; no reader/writer in the pipeline
data_retention_policy      seed rows drive apply_retention()
```

Column-level notes that matter when writing queries:

| Table | Notes |
|---|---|
| `evaluation_runs` | `timestamp` is written twice with the same value: first by `save_run` (placeholder row, `RunResult.run_timestamp.isoformat()`, local time, `T`-separated), then by `save_evaluation_run`'s upsert. `status` ∈ `completed, partial_failure, failed, processing` plus, transiently, the first response's status. `cost` starts as the batch total and is incremented by `add_to_run_cost` for recommendation spend. `filters` is JSON. Rows with `engine = "module6"` are parents for standalone dashboard Module 6 runs and evaluate no prompts. |
| `raw_responses` | `id == RunResult.run_id` (a UUID from the engine, or a `cost-limit-…` / `error-…` / `<prompt>-<engine>-error-…` synthetic id). `cost` is per-answer engine cost only. All statuses are stored, including failures. |
| `response_analysis` | `id == "analysis-" + raw_response_id`, hence at most one analysis per response. `brands_found` is a JSON list of **names** (from substring match), not objects. `claims` is a JSON list of `[text, sentiment]` pairs. `citations` is a JSON list of URL strings. |
| `citations` | Global across runs. `normalized_url` is UNIQUE; `occurrence_count` accumulates; `first_observed` is preserved, `last_observed` refreshed. `page_title` is never written. `extraction_metadata` is never written. |
| `citation_occurrences` | The run-scoping table: (citation, response_analysis) pairs. Every run-scoped citation query joins through here. `claim_text` is never written. |
| `visibility_metrics` | One `overall` row and one `by_topic` row per topic per run. `competitor_mention_rates` is JSON `{brand: rate}`. |
| `gaps` | `gap_type` is `visibility` or `citation` in practice. For citation gaps `top_competitor_visibility` holds a **count**, not a rate, and `top_competitor_name` is the literal string `"Competitor"`. `affected_prompts` is a JSON list of prompt ids (visibility: questions where Striim was not mentioned, else all questions in the topic; citation: all answered questions in the topic). `evidence_ids` holds exactly one synthetic id. |
| `recommendations` | `platform` NULL for articles, else `reddit|linkedin|facebook`. `implementation_steps` is polymorphic JSON (list of objects for articles, list of strings for social). `status` has no CHECK constraint; values in use: `draft, pending_publish, edited, approved, rejected` (`pending_approval`, `implemented` are defined but never written). `review_notes` is JSON but encoded two different ways (§19). |
| `website_checks` | `in_sitemap` always NULL. `check_timestamp` is UTC with a trailing `Z`. |
| `crawler_logs` | `edge_action` ∈ `allowed, blocked, rate_limited, error, NULL`. |
| `prompts` | Upserted from the batch's prompt list on every pipeline run, so it reflects the most recent `question.json` contents for those ids. |

**Migrations.** All DDL is `IF NOT EXISTS`, so re-running the script is safe. `SQLiteStore.apply_schema_migrations` runs first and `ALTER TABLE recommendations ADD COLUMN` for `platform`, `implementation_steps`, `templates_applied` if the table pre-exists without them. `scripts/migrate_add_run_id.py` is a one-off that added `run_id` to `website_checks`/`crawler_logs` and purged orphan rows; it is not invoked automatically.

**Retention.** `data_retention_policy` is seeded with `INSERT OR IGNORE`: 365 days for `raw_responses`, `response_analysis`, `citations`, `website_checks`; 90 days for `crawler_logs`; NULL (keep forever) for `visibility_metrics`, `gaps`, `recommendations`, `method_sections`. `apply_retention()` runs at the start of **every** pipeline run and deletes children before parents (`citation_occurrences` → `response_analysis` → `crawler_logs` → `website_checks` → `citations` → `raw_responses`). `citations` are purged by `last_observed`, not `created_at`, because the upsert never refreshes `created_at`. Consequence: gaps and recommendations outlive the raw evidence they were derived from.

**`:memory:` handling.** `resolve_sqlite_target(":memory:")` returns the shared-cache URI `file::memory:?cache=shared` with `uri=True`. A plain `:memory:` would give every `sqlite3.connect` its own private database, and `SQLiteStore` opens a fresh connection per call, so nothing would persist between calls. The shared-cache database lives only while at least one connection is open; the orchestrator holds one for the whole pipeline for exactly this reason, and tests that use `:memory:` must do the same.

---

## 5. The pipeline, stage by stage

`AEOPipelineOrchestrator.run_full_pipeline(prompts, options)` is the only place the modules are composed. Reading it top to bottom is the fastest way to learn the system; this section annotates that read.

```
run_full_pipeline
 ├─ conn = self._connect()                      one long-lived connection (keeps :memory: alive; passed to Modules 4/5/8/9)
 ├─ store.init_db()                             migrations + schema script (idempotent)
 ├─ daily limit check                           store.get_today_cost() >= cost_limit_per_day → raise CostLimitExceeded
 ├─ store.apply_retention()                     purge expired rows
 ├─ Evaluator(engine, config).run_batch()       Module 2 + Module 3, threaded; writes raw_responses, response_analysis, evaluation_runs
 ├─ (status, spent) = get_run_status_and_cost   remember the evaluation verdict and its cost
 ├─ set_run_status(run_id, "processing")        hold the run in "processing" until the finally block
 ├─ if engine is random-mock: generate_test_data_for_run   fabricate website_checks + crawler_logs
 ├─ store.save_prompts(prompts)                 upsert prompt catalog so joins on topic work
 ├─ MetricsCalculator(conn)                     Module 4: overall + by_topic rows
 ├─ [if enabled] WebsiteAccessibilityChecker    Module 6: pages × crawlers → website_checks (errors logged, never fatal)
 ├─ CitationDeduplicator(conn)                  Module 5: response_analysis.citations → citations + citation_occurrences
 ├─ GapDetector(conn)                           Module 8: visibility gaps from metrics, citation gaps from occurrences
 ├─ resolve recommendation engine               reuse engine if it is Claude; else create_engine("claude"); else None
 ├─ recommendation_budget = run_limit - spent    cap on LLM spend for Module 9
 ├─ RecommendationGenerator(conn, engine, budget).generate_for_run(run_id)
 ├─ add_to_run_cost(run_id, recommendation_cost)
 ├─ for rec: save_recommendation; if should_auto_approve → update_recommendation_status("approved", "system")
 └─ finally: set_run_status(run_id, <evaluation verdict>); conn.close()
```

Returns `{"run_id", "num_prompts", "num_gaps", "num_recommendations", "num_auto_approved"}`.

### 5.1 Preconditions

- **Schema first.** `init_db` runs before the daily-limit query; on a fresh or `:memory:` database the query would otherwise fail with "no such table".
- **Daily limit** is a hard stop: `SUM(cost) FROM evaluation_runs WHERE DATE(timestamp) = today` (local date, despite the docstring saying UTC) compared to `cost_limit_per_day`. It is checked once, before the run; a run that starts under the limit is not interrupted when it crosses it.
- **Retention** runs before evaluation so it can never delete rows from the run in progress.

### 5.2 Module 2: `Evaluator.run_batch`

`Evaluator.__init__` does three things worth knowing:

1. Creates `run_batch_id = uuid4()` and `run_timestamp = now()`; these become the run's identity.
2. Creates a `CostTracker(cost_limit_per_run)` (default 35.0 if the key is absent from the pipeline config).
3. Chooses the **analyzer engine** for Module 3. Default is `"claude"` for real engines and the engine itself for `mock` / `random-mock` (`MOCK_ENGINE_NAMES`). Override with `config["analysis_provider"]`. If `create_engine(analyzer_name)` raises (typically no API key), it logs a warning and falls back to the engine under test. Consequence: an OpenAI run with no Anthropic key analyses its own answers with OpenAI's structured output.

`run_batch`:

1. `_filter_prompts` applies `RunOptions.topic/persona` by exact string equality and `priority` case-insensitively (the CLI offers `High`, the dataset stores `high`), and drops disabled prompts.
2. Logs a pre-run estimate: `n × engine.estimate_cost(1000, 1500)`. With the shipped Claude pricing that is `0.002 + 0.015 = $0.017` per prompt.
3. For each prompt, **before** submitting to the executor, `CostTracker.try_reserve_budget(prompt.id, estimate)` atomically adds the estimate to `spent`. If `spent + estimate > limit`, the prompt is not submitted; a synthetic `RunResult(status="cost_limit_exceeded")` is appended to `results` and counted as failed. This is what makes the per-run limit a real ceiling under concurrency: the check-and-reserve happens under one lock, on the main thread, in submission order.
4. `executor.submit(self.run_one, prompt, options, budget_reserved=True)` with `max_workers = min(4, len(prompts))`.
5. As futures complete (`as_completed`, so results are appended in completion order, not prompt order): if the result has `actual_cost`, `confirm_actual_cost(reservation_id, prompt.id, actual_cost)` swaps the estimate for the real number; successes accumulate token totals; `CostLimitExceeded` raised inside a worker becomes a `cost_limit_exceeded` result; any other exception becomes a `failed` result.
6. Builds `EvaluationRun` with `total_cost = cost_tracker.spent` (this includes analyzer spend, which is why it is not the sum of `raw_responses.cost`), and unless `dry_run`, `save_evaluation_run` upserts it. Status derivation lives in the store: `completed` if `prompts_failed == 0`, `failed` if `prompts_succeeded == 0`, else `partial_failure`.

`run_one` (per worker thread):

- **Dry run**: returns a `RunResult(status="dry_run", estimated_cost=…)` without calling the engine or the database.
- **Live**: if `budget_reserved` is False (direct call, not via `run_batch`), it enforces the limit itself with `can_afford`. Then `engine.run(prompt.prompt)`, stamps the result, and **persists it immediately** via `_save_result_best_effort` regardless of status. Only then, and only for `status == "success"` with text, does it run `_extract_and_store_analysis`. Any exception in the engine call path produces a `failed` result that is also persisted.

Ordering guarantee: a `raw_responses` row exists before any analysis is attempted, and a failed analysis never un-persists or fails the answer. Storage exceptions are swallowed with a warning.

`_extract_and_store_analysis`:

- Calls `extract_response(text, analyzer_engine, competitors_to_track())` (§7); the competitor list is read from config at call time.
- Adds `analysis_cost` to the **same** `CostTracker` under key `"<prompt_id>:analysis"`. If that pushes `spent` over the limit, `add` raises `CostLimitExceeded`; it is caught and logged, the analysis is still saved, and because `spent > limit` every subsequent `try_reserve_budget` fails, so remaining unsubmitted prompts are skipped. (Prompts already in flight complete.)
- Derives `striim_recommended = striim_mentioned and sentiment == "positive"` — "recommended" is not an LLM field.
- Writes `response_analysis` with `brands_found = json.dumps(list of names)`, `claims = json.dumps([[text, sentiment], …])`, `citations = json.dumps([url, …])`.

**`CostTracker` semantics in one table:**

| Operation | Effect on `spent` | Thread-safe |
|---|---|---|
| `try_reserve_budget(id, est)` | `+est` if it fits, else no-op and returns `(False, "")` | yes (lock) |
| `confirm_actual_cost(res_id, id, actual)` | `- est + actual` for that reservation | yes |
| `add(id, cost)` | `+cost`; raises if over limit **after** adding | yes |
| failed engine call | reservation stays (conservative; `actual_cost` is None) | — |

### 5.3 Status hold

After evaluation the store already says `completed`/`partial_failure`/`failed`. The orchestrator reads that verdict plus `cost`, sets `status = "processing"`, and restores the verdict in `finally`. This exists because the dashboard's progress banner and any human looking at the table would otherwise see "completed" while gaps and recommendations were still being generated. If the evaluator itself raises, `evaluation_status` is still `None` and nothing is restored (there is no run to restore).

### 5.4 Prompt catalog and metrics (Module 4)

`save_prompts` upserts every prompt in the batch so `MetricsCalculator.calculate_metrics_by_topic` and `GapDetector` can join `raw_responses.prompt_id → prompts.topic/priority`. Metrics formulas are in §8. Overall metrics are saved only if the calculator returned a non-empty dict (i.e., at least one `response_analysis` row exists for the run; a `mock` run yields none).

### 5.5 Module 6 (optional)

Gated by `config.evaluation.run_website_accessibility_checks` (default False). When on, `WebsiteAccessibilityChecker().check_pages(important_striim_pages, crawlers)` runs synchronously on the main thread, stamps `run_id`, and bulk-inserts. It is wrapped in a broad `except` so network failures never fail the run. Details in §12.

### 5.6 Modules 5, 8, 9 and auto-approval

Citations (§9) must run before gaps because citation gaps query `citation_occurrences`. Gaps (§10) must run before recommendations because the generator reads the `gaps` table for the run (not the in-memory list). Recommendations (§11) are saved one at a time and immediately auto-approved if `should_auto_approve` (`priority >= 7 and confidence == "high"`). Recommendation LLM cost is folded into `evaluation_runs.cost` via `add_to_run_cost`, so the run's stored cost is engine + analyzer + recommendation spend.

**Recommendation engine resolution** deserves emphasis: if the engine under test is Claude it is reused (same rate limiter, same client). Otherwise `create_engine("claude")` is attempted. That means a `random-mock` run on a machine with `ANTHROPIC_API_KEY` set **does** spend real money on recommendations, bounded by `recommendation_budget = cost_limit_per_run - spent_so_far` (and `spent_so_far` is 0 for mocks, so the whole per-run limit is available).

---

## 6. Engine layer

### 6.1 Contract (`engine/base.py`)

```python
class BaseEngine(ABC):
    name: str           # registry key; the evaluator/orchestrator branch on it
    model_name: str
    def run(self, prompt_text) -> RunResult                       # never raises for provider errors
    def run_with_structured_output(self, prompt_text, schema) -> StructuredCallResult   # may raise
    def estimate_cost(self, prompt_tokens, completion_tokens) -> float
    def get_token_costs(self) -> {"input": $/1k, "output": $/1k}
    def get_retry_policy(self) -> RetryPolicy        # lazily built from config["max_retries"]
    def get_rate_limiter(self) -> RateLimiter        # lazily built from config["rate_limit_tpm"/"rpm"]
```

`config` is a plain dict — `ProviderConfig.model_dump()` when built by the factory — so engines can also be constructed in tests with hand-written dicts. All defaults are defensive against `None` values (a past bug class: YAML `null` reaching arithmetic).

### 6.2 Factory and registry

`create_engine(name, config_dict=None)`:

1. Looks `name` up in `aeo_eval.config.PROVIDERS` (`{"mock", "random-mock", "claude", "openai"}`); unknown → `ValueError` listing available names.
2. `importlib.import_module` + `getattr` on the `"module:Class"` string. Import is lazy so a missing SDK only fails when that engine is requested.
3. If no `config_dict`, uses `app_config.providers[name].model_dump()` (empty dict if the provider has no config section). This is how API keys reach the engine: via the env-var overlay in §3.1.

`available_engines()` is `sorted(PROVIDERS)` and populates the CLI `--engine` choices and the dashboard radio.

### 6.3 `ClaudeEngine`

- Requires `api_key` in config; raises `ValueError` (with a hint about whether the env var is present) otherwise. Builds one `anthropic.Anthropic` client, a `RetryManager`, and materialises the rate limiter eagerly.
- **`run`** (answers): `messages.create(model, max_tokens=2000, system=<"include URLs and sources" instruction>, messages=[user], timeout)`. The system prompt exists because early runs returned no citations and Module 5 had nothing to work with. Response text is the first content block that has a `.text` attribute (skips thinking blocks). Cost is `estimate_cost(usage.input_tokens, usage.output_tokens)`. Exception → status mapping: `RateLimitError → rate_limited`, `APITimeoutError → timeout`, `APIError → failed`, anything else → `failed` with the exception type in `error`. Latency is wall-clock including rate-limit wait and retries.
- **`run_with_structured_output`**: same client, `max_tokens=self.max_tokens` (config, default 8000), no system prompt, and `output_config={"format": {"type": "json_schema", "schema": schema}}`. Two API constraints are baked into the schemas across the codebase: every object must declare `"additionalProperties": false`, and every property must be listed in `required` (nullable fields use `"type": ["integer", "null"]`). If `json.loads` fails, it logs — distinguishing `stop_reason == "max_tokens"` (truncation; the log names the config key to raise) from other parse failures — and returns `data={"raw_response": text}` rather than raising. Cost is still reported.
- Rate limiting is applied before every call with a fixed estimate of 100 prompt + 1000 completion tokens, regardless of actual prompt size.

### 6.4 `OpenAIEngine`

Structurally identical. Differences: `chat.completions.create` with `temperature=0`; structured output uses `response_format={"type": "json_schema", "json_schema": {"name", "schema", "strict": True}}` with `max_tokens=2000` (not the config `max_tokens`); default token costs differ (0.0025 / 0.010 per 1k). Its exception classes come from the `openai` SDK, but `retry.py` classifies using `anthropic`'s classes — see §6.6.

### 6.5 Mocks

`MockEngine` returns `"Mock answer for prompt: …"`, zero cost, and inherits the base `run_with_structured_output`, which raises `NotImplementedError`. Because the evaluator swallows analysis errors, a `mock` run produces `raw_responses` but no `response_analysis`, hence no metrics, gaps or recommendations. It is the cheapest way to exercise persistence.

`RandomMockEngine` picks uniformly from `RESPONSE_POOL` (10 hand-written CDC-market answers with URLs and a known brand order). Its `run_with_structured_output` **ignores the prompt** and picks another random pool entry, deriving `striim_position` from the pool's `positions`, `is_recommended = position <= 3`, sentiment `positive` if Striim is in the top 2, and a single claim if a striim.com URL is present. Token counts are synthesised from word count; cost is zero. So on random-mock runs the analysis does not describe the answer that was actually stored, but it is statistically similar and exercises every downstream path. `generate_test_data_for_run` writes 20 `crawler_logs` and 15 `website_checks` rows with realistic status distributions, opening its own `SQLiteStore` on the configured DB path.

### 6.6 Retry (`engine/retry.py`)

`RetryPolicy.should_retry(error)`:

1. Exact type in `non_retryable_exceptions` (`ValueError, KeyError, AttributeError, TypeError, AssertionError`) → False.
2. Exact type in `retryable_exceptions` (`anthropic.APITimeoutError, anthropic.RateLimitError, TimeoutError, ConnectionError, IOError`) → True.
3. `isinstance` checks against the same two sets, non-retryable first.
4. **Default: True.** Unknown exceptions are retried. This means an Anthropic 400 (`BadRequestError`, a subclass of `APIError`, which is in neither set) is retried three times before surfacing, and OpenAI's own `RateLimitError` (a different class) is retried by falling through to the default rather than by classification.

`get_delay_ms(attempt)` = `min(initial × factor^(attempt−1), max)` with ±10% uniform jitter, clamped to `[0, max]`. Defaults 100 ms / 2.0 / 30 s give 100, 200, 400 ms for the three retries (four attempts total). `RetryManager.retry(fn)` sleeps synchronously with `time.sleep`; `retry_async` mirrors it with `asyncio.sleep` but nothing calls it.

The policy is built from `config["max_retries"]` only; `initial_delay_ms`, `backoff_factor`, `max_delay_ms` always use the dataclass defaults regardless of `config.yaml`'s `retry_policy` section.

### 6.7 Rate limiter (`engine/rate_limiter.py`)

Two independent token buckets, refilled continuously:

```
refill: tokens = min(limit, tokens + elapsed_seconds × limit / 60)
admit:  tpm_tokens >= prompt + completion  AND  rpm_tokens >= 1
wait:   max(needed_tokens / tpm_limit × 60, needed_requests / rpm_limit × 60, 0.1s), sleeping ≤ 1 s per loop
```

Buckets start full, so a fresh process can burst up to `rpm_limit` requests. The limiter is **per engine instance** and has **no lock**; the evaluator calls it from up to four threads, so two threads can both observe enough tokens and both decrement, slightly over-admitting. When Claude is both answer engine and analyzer (the default for Claude runs), one instance and therefore one pair of buckets governs both call types. The recommendation stage reuses the same instance when the engine under test is Claude.

---

## 7. Module 3: response analysis

`analysis/extractor.py:extract_response(response_text, engine, competitors)`:

1. **Brands (deterministic).** `extract_brand_mentions(text, ["Striim"] + competitors)`: lower-case substring containment. `striim_mentioned` is decided here, not by the LLM. Note that `"Kafka"` matches inside "Confluent Kafka", and `"Oracle GoldenGate"` will not match "GoldenGate" alone (the mock pool includes such an answer).
2. **LLM extraction.** `llm_extractor.extract_with_claude(engine, text, competitors)` builds the prompt (`build_extraction_prompt`) and calls `engine.run_with_structured_output(prompt, EXTRACTION_SCHEMA)`. The schema:

   ```
   striim_position: int|null
   competitors: [{name, position: int|null, is_recommended: bool}]
   striim_claims: [{text, sentiment: positive|neutral|negative, confidence: number, supporting_citation_url: string|null}]
   general_sentiment_toward_striim: positive|neutral|negative
   extraction_confidence: number
   flagged_for_review: bool     # prompt asks for true when confidence < 0.65 or ambiguous
   ```

   Outcomes: (a) parsed → `LLMExtractionOutput` with `BrandMention.confidence` hardcoded to 1.0; (b) `{"raw_response": …}` (engine could not parse JSON) → an all-defaults output with `extraction_confidence=0.0, flagged_for_review=True`, cost still returned; (c) exception → `(None, 0.0)`.
3. **Citations.** `re.findall(r'https?://[^\s)]+', text)`, de-duplicated preserving order. Claim-level `supporting_citation_url`s are computed but the final list is simply all URLs in the answer. Trailing punctuation such as a period or comma stays attached to the URL; `normalize_url` does not strip it either, so `https://x.com/a.` and `https://x.com/a` are distinct citations.
4. **Fallback.** If (c), return brands-only with `sentiment="neutral"`, `confidence=0.0`, `flagged_for_review=True`, `analysis_cost=0.0`.

What reaches the database (via the evaluator): `striim_mentioned` (rules), `striim_recommended` (mentioned ∧ positive sentiment), `striim_position` (LLM), `brands_found` (rules, names only), `claims` (LLM `[text, sentiment]` pairs), `citations` (regex), `extraction_confidence`, `flagged_for_review`. The LLM's positioned competitor list is **not** persisted; only the flat brand names are, which is what `competitor_mention_rates` is later built from.

Competitor list: `runner/evaluator.py:competitors_to_track()` returns `config.evaluation.competitors` (shipped: Fivetran, Oracle GoldenGate, Qlik Replicate, Confluent, AWS DMS, Estuary), read at call time so dashboard/test edits to the config object apply immediately. `DEFAULT_COMPETITORS` (which includes `Kafka`) is used only when the configured list is empty. Because matching is substring-based, `"Estuary"` also matches "Estuary Flow".

---

## 8. Module 4: visibility metrics

`metrics/calculator.py:MetricsCalculator(conn)` reads `response_analysis ⋈ raw_responses` for the run. For a set of N analysed responses:

| Metric | Formula |
|---|---|
| `mention_rate` | `count(striim_mentioned) / N` |
| `recommendation_rate` | `count(striim_recommended) / N` |
| `top3_rate` | `count(striim_position ∈ {1,2,3}) / N` — denominator is all responses, not mentions |
| `avg_position` | mean of `striim_position` over responses where it is > 0; `None` if none |
| `citation_rate` | `count(responses whose citations list contains a URL with "striim.com") / N` (`has_striim_citation`) |
| `competitor_mention_rates` | for each name in `brands_found` other than `"Striim"`: `count / N` |
| `num_responses` | N |

`calculate_metrics_for_run` produces the `overall` row; `calculate_metrics_by_topic` repeats the computation per distinct `prompts.topic` joined through `raw_responses.prompt_id`, producing `by_topic` rows. `by_persona` / `by_engine` are named in the schema comment but not computed. Only successful responses have analysis rows, so failed prompts are excluded from N.

---

## 9. Module 5: citation intelligence

### 9.1 Normalisation (`citations/normalizer.py`)

`normalize_url` = `urlunparse((scheme.lower(), netloc.lower(), path.rstrip("/"), "", "", ""))`. Query string, params and fragment are dropped; trailing slash removed; scheme and host lower-cased. The path is **not** lower-cased and percent-encoding is **not** decoded (the docstring claims both). `http` and `https` remain distinct; `www.` is not stripped.

### 9.2 Classification (`citations/classifier.py`)

First match wins, in this order:

1. `striim.com` in domain → `striim_owned`
2. any of `fivetran.com, confluent.io, kafka.apache.org, oracle.com, qlik.com, estuary.dev, aws.amazon.com` in domain → `competitor` (so `docs.oracle.com` and `docs.aws.amazon.com` are competitor, not partner docs)
3. `docs.` or `documentation` in domain → `partner_docs`
4. `g2.com, capterra.com, gartner.com, forrester.com` → `review_platform`
5. `medium.com, dev.to, github.com, stackoverflow.com` → `technical_publication`
6. `reddit.com, slack.com, discord.com` → `community_content`
7. `gartner, forrester, analyst` → `analyst_research` (unreachable for the two named domains because step 4 catches them)
8. else `other`

`customer_content` is in the return type but never produced.

### 9.3 Deduplication and persistence

`CitationDeduplicator.process_citations_from_run(run_id)` reads every `response_analysis.citations` JSON list for the run and builds one dict per `normalized_url` with `original_url` (first seen), `domain`, `source_category`, `occurrence_count` (per URL mention, so one response citing the same URL twice counts twice), `first/last_observed = now()`, and `occurrences = [response_analysis.id, …]`.

`SQLiteStore.save_citations` upserts by `normalized_url`: on conflict it sets `last_observed` and adds to `occurrence_count`, preserving `id` and `first_observed`. It then inserts one `citation_occurrences` row per `(citation, analysis)` pair. Everything run-scoped in the dashboard and gap detector goes through `citation_occurrences`; the `citations` table alone is cross-run history.

---

## 10. Module 8: gap detection

`gaps/detector.py:GapDetector(conn).detect_all_gaps(run_id)` = visibility gaps + citation gaps. Content, technical, authority and agent-experience gaps from the spec are not implemented.

### 10.1 Visibility gaps

For each `by_topic` metrics row of the run with `num_responses >= 3`:

- `top_competitor_rate, top_competitor_name = max(competitor_mention_rates)`; `(0.0, "Unknown")` if empty.
- Topic tier = highest `priority` among that topic's `prompts` rows (case-insensitive ordering high < medium < low), default `"Medium"`; `should_flag_visibility_gap` capitalises it before lookup.
- Flag if `striim_rate < threshold[tier]` (High 0.15, Medium 0.05, Low 0.02) **or** (`striim_rate > 0 and competitor_rate > 0 and competitor_rate > 2.0 × striim_rate`). Because the relative branch requires `striim_rate > 0`, a topic at exactly 0% is caught only by the absolute branch.
- `priority = calculate_gap_priority`: `ratio = (competitor − striim) / max(striim, 0.01)`; `> 3.0 → high`, `> 1.5 → medium`, else `low`. At `striim = 0` the divisor floors at 0.01, so any competitor rate above 3% yields `high`.
- `confidence`: `num_responses >= 10 → high`, `>= 5 → medium`, else `low`.
- `evidence_ids = ["metrics-<run_id>-<topic>"]`.
- `affected_prompts` = `_topic_prompt_ids(run_id, topic, missed_only=True)`: distinct prompt ids of analysed responses in this run and topic with `striim_mentioned = 0`. If Striim was mentioned in every answer but still trails the competitor by more than 2×, the list falls back to every analysed prompt in the topic.

### 10.2 Citation gaps

One SQL group-by over `citation_occurrences ⋈ citations ⋈ response_analysis ⋈ raw_responses ⋈ prompts` for the run, per topic, counting `competitor` and `striim_owned` occurrences. Fire when `striim == 0 and competitor >= 3`. `priority` and `confidence` are both `high` if `competitor > 5` else `medium`. `striim_visibility = 0.0`, `top_competitor_visibility = float(competitor_count)` (a count stored in a rate column), `top_competitor_name = "Competitor"`. `affected_prompts` is every analysed prompt in the topic for this run, since the whole topic has zero Striim citations.

### 10.3 What is not done

No deduplication or merging across gap types on the same topic (the spec asks for it). A topic can therefore yield both a visibility and a citation gap, each fanning out into its own recommendations.

---

## 11. Module 9: recommendations

`docs/recommendations-architecture.md` covers the persistence model and status workflow in depth; this section documents the generator's control flow and the pieces added since that document (budget gate, evidence builder, BM25 retrieval).

### 11.1 Construction

`RecommendationGenerator(conn, engine=None, cost_budget=None)`:

- Loads `methods.txt` **relative to the current working directory** (`open("methods.txt")`), so running the CLI from anywhere but the repo root silently drops the methodology context.
- Builds `MethodsRAG(conn, engine)` and, if the text loaded, calls `initialize_methods`, which `DELETE`s and re-inserts all `method_sections` rows. This happens on every pipeline run.
- `cost_budget=None` means unlimited; the orchestrator always passes `max(0, cost_limit_per_run − spent_so_far)`.

### 11.2 Per-gap flow (`generate_for_gap`)

```
if engine and budget available:
    evidence        = _build_gap_evidence(gap)              # "" today, see 11.3
    methods_context = _get_methods_context_for_gap(gap)     # BM25 top-3 sections
    diagnosis       = _diagnose_gap_with_llm(gap, evidence, methods_context)        # call 1
    if diagnosis:
        article     = _generate_article_recommendation_with_llm(gap, diagnosis, …)  # call 2
priority   = 8 if gap.priority=="high" and striim_visibility<0.1 else 6 if high else 5 if medium else 3
will_auto_publish = confidence=="high" and priority>=8 ; status = "pending_publish" or "draft"
article rec  = LLM fields if (article and diagnosis) else template by gap_type (visibility | citation | other)
if article and diagnosis:
    for platform in (reddit, linkedin, facebook):                                    # calls 3-5
        social = _generate_social_media_recommendation_with_llm(gap, platform, diagnosis, evidence)
        if social: append social rec (priority-2 floored at 1, effort 1, status "draft", owner "Marketing Team")
```

Evidence and methods context are built once per gap and threaded through all five calls. A failed diagnosis or article call drops the whole gap to the template path (one article, no social). A failed social call skips that platform only. All LLM exceptions are caught and logged.

### 11.3 Evidence builder (`_build_gap_evidence`)

Grounds prompts in the run's actual data: the affected questions' text (first 8 of `gap["affected_prompts"]`, with persona and intent), what each engine answered (brands, up to 3 claims, a 400-char excerpt, for up to 5 responses in this run), and the top 12 cited URLs enriched from the `citations` catalog (title, category, cross-run count). Caps (`_EVIDENCE_MAX_*`) bound prompt size. It returns `""` only when there is no connection, no affected prompts, or a query fails; `GapDetector` now populates `affected_prompts` (§10), so real runs carry evidence. With evidence present the prompt's "Affected questions: N" line is accurate and the specificity rules have something concrete to bite on.

### 11.4 Budget gate

`_llm_budget_available()` is checked before each of the five calls: `spent + _estimated_call_cost() <= budget`, where `_estimated_call_cost = engine.estimate_cost(4000, engine.max_tokens)` — a deliberate over-estimate assuming a full-length completion. With the shipped pricing that is `4 × 0.002 + 8 × 0.01 = $0.088` per call, so a `$4` remaining budget allows ~45 calls ≈ 9 fully LLM-generated gaps. A budget of `<= 0` disables LLM calls entirely. Once the gate closes it stays closed for the run (spend only grows), later gaps get template recommendations, and one warning is logged. Actual spend is accumulated from `StructuredCallResult.cost` in `_track_cost` and returned by `generate_for_run` for the orchestrator to fold into the run.

### 11.5 RAG retrieval (`recommendations/rag.py`)

`chunk_methods_text` splits on `(?:\A|\n)(\d+\.\s+[^\n]+)` — numbered headings — and pairs heading *i* with the body that follows it (odd/even indices after `re.split` with a capturing group). Topic = text after the first colon in the heading, else the whole heading. The shipped `methods.txt` yields six sections.

Retrieval is lexical BM25 (`k1=1.5, b=0.75`), computed in Python over the tokenised corpus cached on the instance: tokens are `[a-z0-9]+` runs longer than two characters minus a small stopword list; IDF is `log(1 + (N − df + 0.5)/(df + 0.5))` floored at zero. The query is `"Gap type: {t}. Topic: {topic}. Visibility: {x}%."`, `top_k=3`, and sections with zero score are dropped. If nothing scores (no lexical overlap) or the table is empty, **all** sections are returned; if retrieval raises, the raw `methods.txt` text is used. The `embedding` column stays NULL and `embedding_model` is written as `"lexical-bm25"`; an earlier version called a non-existent Anthropic embeddings API, which is why the column exists.

### 11.6 Prompts and schemas

Three prompts, each ending in a "Return JSON with …" block that mirrors its schema. All schemas set `additionalProperties: false` at every object level and list every property as required:

- `GAP_DIAGNOSIS_SCHEMA`: `{diagnosis: str, root_causes: [str]}`
- `ARTICLE_RECOMMENDATION_SCHEMA`: `{article_suggestion: {title, recommended_sections[], how_it_improves_aeo, source_type ∈ guide|blog_post|tutorial}, recommended_action, evidence_summary, implementation_steps: [{step, effort ∈ Low|Medium|High, owner ∈ Content Team|Product Manager|Engineering, notes}]}` — `notes` is optional inside the step object (`required: [step, effort, owner]`).
- `SOCIAL_MEDIA_RECOMMENDATION_SCHEMA`: `{recommended_action, implementation_steps: [str], content_outline, hashtags: [str], frequency, evidence_summary}`

The article prompt prescribes the shape of `implementation_steps` (title/slug/competitor page to displace → one step per H2 → schema markup + internal links + review + publish → re-run questions). A shared `_SPECIFICITY_RULES` block is appended to the article and social prompts. Social prompts come from `PLATFORM_PROMPTS[platform].format(topic, gap_type, striim_vis, diagnosis)`; the evidence block is prepended by concatenation, not `.format`, because answer excerpts can contain braces.

### 11.7 Output dicts and what persists

Every recommendation carries `id (uuid4), gap_id, type ("article"|"social_media"), affected_pages (["https://striim.com/topic/<topic lower>"]), confidence (inherited from gap), created_timestamp, problem, evidence_summary, recommended_action, suggested_owner, priority, estimated_effort, measurement_plan, will_auto_publish, status, implementation_steps`; article recs on the LLM path add `diagnosis, root_causes, article_suggestion`; social recs add `platform, content_outline, hashtags, frequency`.

`_recommendation_row` persists: `id, gap_id, problem, evidence_summary, recommended_action, affected_pages, suggested_owner, priority, estimated_effort, measurement_plan, confidence, status, platform, implementation_steps, templates_applied (always None), created_timestamp`. Not persisted: `type, will_auto_publish, diagnosis, root_causes, article_suggestion, content_outline, hashtags, frequency`. The article title, section list and the whole social content plan therefore exist only in the returned dicts and the log.

### 11.8 Approval

Two thresholds coexist: the generator's `will_auto_publish` (`priority >= 8`) only chooses between `pending_publish` and `draft`; the orchestrator's `should_auto_approve` (`priority >= 7`) decides the actual `approved` transition. Since 7 is unreachable (priorities are 8, 6, 5, 3 for articles and 6, 4, 3, 1 for social), both select the same set today: high-priority gaps with Striim under 10% and `high` confidence. Auto-approval writes `approved_by="system"` and JSON-encodes the review note. Manual transitions happen in the dashboard (§15.4).

---

## 12. Module 6: website and crawler accessibility

`WebsiteAccessibilityChecker.check_pages(pages, crawlers)` is two passes:

**Pass 1, once per URL:** `HttpChecker.check_page` (httpx GET with UA `striim-aeo-monitor/1.0`, redirects followed, 15 s timeout; parses `<meta name=robots content=…noindex…>`, `X-Robots-Tag`, `<link rel=canonical>`, `Content-Location`) and `ExtractabilityChecker.check_extractability` (a **second** GET of the same URL, then `trafilatura.extract`; `poorly_extractable` if `word_count < 300 or extracted_chars / raw_html_bytes < 0.05`, `well_extractable` otherwise, `fetch_failed` on any error). Each checker has its own per-domain limiter of 0.5 requests/s, so a page costs two requests spaced by at least 2 s each within its checker.

**Pass 2, per (URL, crawler):** `RobotsChecker.is_allowed(url, crawler)` using `urllib.robotparser` with the parser cached per `scheme://host`. `robots.txt` is fetched with urllib's default UA and **no timeout**. Any failure (missing file, network error, exception) is fail-open: allowed. Then `_classify_result` in this order:

```
fetch_error set?          → fetch_failed | http_error_4xx | http_error_5xx | http_error
not robots_allowed        → blocked_by_robots
noindex                   → noindex_set
status None               → fetch_failed
status != 200             → http_error_4xx | http_error_5xx | http_status_<n>
extract == fetch_failed   → fetch_failed
extract == poorly_extractable → poorly_extractable
else                      → publicly_accessible
```

Each pair produces one `website_checks` row (`in_sitemap` always None; `check_timestamp` UTC + `Z`). Exceptions inside the pair loop produce a `check_failed` row instead of aborting. With the shipped config (4 pages × 9 crawlers) a pipeline run adds 36 rows.

Not implemented despite README/spec mentions: sitemap membership, `llms.txt` detection, JS-render detection (`requires_js_render` is always False), crawler UA simulation on the page fetch itself (the page is fetched once with the monitor UA; only `robots.txt` evaluation is per-crawler).

The dashboard also offers a standalone Module 6 run (`run_module6_standalone`). It generates `run_id = "module6-<hex>"`, first inserts a parent row via `SQLiteStore.create_run_record(run_id, engine="module6", num_prompts=0)` (required because `website_checks.run_id` has an enforced foreign key), then stores the checks. Those parent rows are excluded from the dashboard's run selector and comparison views by `fetch_all_runs` (`WHERE engine != 'module6'`); the Module 6 view reads `website_checks` directly and shows them.

---

## 13. Module 7: request-log analysis

Three classes, used together as `RequestLogAnalyzer().analyze(RequestLogParser().parse_file(path))` → rows for `SQLiteStore.store_crawler_logs`. **No entry point calls this chain**; the only writer of `crawler_logs` today is `RandomMockEngine`. The classes are complete and tested, so wiring a `--logs <path>` option is a small change (§20).

- `RequestLogParser.parse_json_line`: JSONL, required keys `timestamp, host, path, status_code, user_agent`; adds `id (uuid4)` and `normalized_path` (query string stripped). `parse_file` skips blank/malformed lines, drops records older than `days_back=90` (parsing `Z` as `+00:00`), and never raises on I/O problems.
- `CrawlerClassifier.classify(ua)`: ordered checks — substring in `KNOWN_AI_CRAWLERS` (`oai-searchbot, gptbot, perplexitybot, claude-searchbot, claudebot`) → `known_ai_crawler`; regex in `DELEGATED_AGENT_PATTERNS` (`agent-\w+`, `chatgpt-user`, `perplexity-user`) → `delegated_agent` with `tool_name`; substring in `SEARCH_CRAWLERS` → `search_crawler`; browser tokens (`mozilla, chrome, …`) → `human_browser`; else `unknown`. `model_hint` extracts `claude-*`/`gpt-*` tokens. Note most real crawler UAs contain `Mozilla/5.0`, which is why the browser heuristic is checked last.
- `RequestLogAnalyzer._normalize_record`: `crawler` = matched pattern (AI/search) or tool name (delegated) or None; `edge_action` = `allowed` (2xx), `blocked` (403), `rate_limited` (429), `error` (other ≥ 400), else None; `log_source="request_log"`; the full `ua_classification` dict is attached but not stored.

---

## 14. Storage layer

`SQLiteStore` is a connection-per-call DAO (module docstring in `sqlite_store.py` has the summary). Points not covered elsewhere:

- **Write-path invariants.** `save_run` first does `INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp=<run_timestamp ISO>, engine, model, num_prompts=1, status=<result status>)` so the `raw_responses` FK is satisfiable from the first response, then inserts the response. The timestamp is written in Python ISO form (not SQLite `datetime('now')`) so string comparisons against other ISO timestamps, such as the dashboard's progress poll, behave. `create_run_record` is the analogous parent-row insert for flows that evaluate no prompts. `save_evaluation_run` upserts the real totals with `ON CONFLICT(run_id) DO UPDATE`. So a crash mid-batch leaves a placeholder row with `num_prompts=1` and a per-response status.
- **`update_recommendation`** is the allow-listed generic updater (`problem, recommended_action, priority, estimated_effort, status, review_notes, suggested_owner, measurement_plan, confidence, affected_pages`), built with string-formatted column names from that allow-list and parameterised values. The dashboard's Edit form does not use it (§19).
- **Cost queries.** `get_cost_by_topic` allocates each run's non-engine cost (run total − Σ `raw_responses.cost`) to topics proportionally by prompt count. The dashboard has its own simpler `fetch_cost_by_topic` that sums `evaluation_runs.cost` once per `(run, topic)` metrics row, which over-counts multi-topic runs; the two are not consistent.
- **Templates.** `save_/get_recommendation_template(s)` are complete CRUD over `recommendation_templates`; nothing calls them.
- **Threading.** Each call opens and closes its own `sqlite3.Connection`, so the object can be shared across threads. SQLite's default journal mode (not WAL) means a writer briefly blocks other writers; with four evaluator threads plus the dashboard reading, "database is locked" is possible under load and surfaces as a swallowed warning on the write path.

---

## 15. Dashboard

### 15.1 Boot

`streamlit_app.py` inserts the repo root into `sys.path` and calls `aeo_eval.dashboard.app.main`. `app.py` loads `.env` (searching repo root, its parent, and CWD) before importing `aeo_eval.config`, then imports the pipeline pieces it needs to launch runs. `.streamlit/config.toml` sets the dark theme; `main()` additionally injects a ~500-line CSS block that restyles Streamlit primitives (metric cards, tabs, buttons, radio/slider accents to `#1e40af`, hides the sidebar).

### 15.2 Page flow (`main`)

1. `fetch_all_runs()`; if empty, error + `st.stop()`.
2. Navigation buttons set `session_state.view_mode` ∈ `Dashboard | Cost | Module 6 Checks` and `st.rerun()`. Cost and Module 6 views return early.
3. Dashboard view: optional **Configure & Run** panel (run selector that also sets `selected_run_idx`; engine radio from `available_engines()`; prompt count slider 1–240; topic and priority selects; *Start Evaluation*).
4. Background-run banner (below).
5. KPI strip from the `overall` metrics row: mention rate, top-3 rate with average position, citation rate with recommendation rate, top competitor.
6. Five tabs: Gaps & Recommendations, Citation Analysis, Run Comparison, Trends & Details, Recommendations Management.

### 15.3 Background evaluation

*Start Evaluation* builds a `job` dict, starts `threading.Thread(target=run_evaluation, daemon=True)`, stores the dict (with the thread) in `session_state.eval_job`, and reruns. `run_evaluation` selects prompts with `select_prompts(load_prompts(...), topic, priority, limit)` (filter first, then prefix slice; note the persona argument is accepted but ignored by `select_prompts`, and the Evaluator filters again anyway), creates the engine, and runs the orchestrator with `run_type="dashboard"`. While `thread.is_alive()`, each render calls `fetch_run_progress(conn, job["started"])`, shows `describe_progress`, sleeps 4 s and reruns. When the thread finishes, the result or error is shown once and the job is deleted from session state. The button is disabled while a job is alive. Progress is derived purely from DB rows: newest `evaluation_runs` row with `timestamp >= started` (both ISO strings; `save_run` writes the placeholder row in ISO form for exactly this comparison), plus counts of responses, analyses, gaps and recommendations; `done` when status ∈ `{completed, partial_failure, failed}`.

### 15.4 Views and their writes

| View | Reads | Writes |
|---|---|---|
| Gaps & Recommendations | `gaps`, `recommendations ⋈ gaps`, bulk evidence join | none |
| Citation Analysis | `citation_occurrences ⋈ citations ⋈ … WHERE run_id` grouped by domain (top 20) | none |
| Run Comparison | `overall` metrics for every run | none |
| Trends & Details | `by_topic` metrics; 30-day `overall` trend; 30-day cost trend | none |
| Recommendations Management | recs with status ∈ `draft, pending_approval, pending_publish, edited` | **Approve** → `SQLiteStore.update_recommendation_status(id, "approved", approved_by="dashboard_user")`; **Reject** → same method with `"rejected"` and the reason as `review_notes` (JSON-encoded string); **Edit** → raw `UPDATE … SET problem, recommended_action, priority, estimated_effort, status='edited'` on a direct `sqlite3` connection |
| Cost Analysis | daily budget, all runs, per-engine and per-topic aggregates, 30-day trend | **Save Limits** → mutates `config.general.*` and rewrites `config.yaml` |
| Module 6 Checks | all `website_checks` (500 newest), per-crawler breakdown | **Run Module 6 Checks** → `run_module6_standalone` creates an `evaluation_runs` parent row (`engine="module6"`) and stores the checks under it |

`formatting.py` holds the pure helpers used by renderers and is unit-tested: effort code/label/colour mapping, platform badge HTML, `split_into_paragraphs` (sentence-boundary regrouping to ≤350 chars), `normalize_implementation_step` (dict-or-string → uniform dict). `render_implementation_steps` and `render_long_text` HTML-escape all user/LLM text before `unsafe_allow_html=True`.

`delete_run` exists but no button calls it; it also omits `website_checks`/`crawler_logs`, so with foreign keys on it would fail for runs that have those rows.

---

## 16. CLI and scheduler

`python -m aeo_eval.cli <command>`:

- **`run`** — the only fully implemented command. Loads prompts, applies `--limit` as a prefix slice **before** filtering (so `--limit 5 --topic X` may yield fewer than 5), builds the engine via the factory, and calls the orchestrator with `{"db_path": --db or config, "cost_limit_per_run": --cost-limit or config}`. Prints a summary block. Exit code 1 on any exception, 0 on Ctrl-C. `--priority` choices are `High|Medium|Low`; the evaluator compares priority case-insensitively so they match the dataset's lower-case values. `--verbose` is parsed but unused.
- **`report <run_id>`** — `demo/report.py:print_run_summary`: run header, up to 5 by-topic metric lines, all gaps, up to 5 approved recommendations. Used by `scripts/demo.sh`.
- **`history`**, **`schedule`** — print "not yet implemented".

`scheduler.py:ScheduleManager` wraps `BackgroundScheduler` with cron triggers (`misfire_grace_time=60`, `coalesce=True`). Jobs and their configs are in memory only. `_run_scheduled_job` re-enters `cli.cmd_run` with a synthetic `argparse.Namespace` (engine, topic, persona, notes `"Scheduled run: <name>"`), so scheduled runs have `run_type="manual"` in memory (the CLI hardcodes it) and share every CLI behaviour. Nothing instantiates the manager.

---

## 17. Testing

`pytest` from the repo root (`pythonpath = ["."]`, `testpaths = ["tests"]` in `pyproject.toml`). 272 tests, ~100 s, no network: Anthropic/OpenAI clients are mocked with `pytest-mock`, Module 6 fetches are patched, and `RandomMockEngine` drives integration tests.

`tests/conftest.py` has one autouse fixture that (a) points `config.general.output_db_path` at a per-test temp file so no code path that defaults to the configured DB can touch `data/`, (b) clears the Claude provider's `api_key`, and (c) removes `ANTHROPIC_API_KEY` from the environment. Consequence: any test that wants a Claude engine must inject a fake key explicitly, and analyzer fallback paths are exercised by default.

Test layout mirrors the package. The most load-bearing invariants, each with a dedicated file:

| Invariant | Test file |
|---|---|
| Every engine result, including failures, is persisted | `tests/test_run_persistence.py` |
| Batch totals (including analyzer spend) land in `evaluation_runs` | `tests/test_evaluation_run_totals.py`, `tests/test_analyzer_engine.py` |
| Budget reservation never exceeds the per-run limit under concurrency | `tests/test_evaluator_cost.py` |
| Structured output is schema-enforced, rate-limited, reports usage | `tests/engine/test_structured_output.py` |
| Retention deletes expired rows FK-safely and by `last_observed` for citations | `tests/test_retention.py` |
| Citation history survives across runs; occurrences are written | `tests/citations/test_citation_store.py` |
| Dashboard citation counts are run-scoped | `tests/dashboard/test_citation_query.py` |
| Gap thresholds use the topic's real priority, any case | `tests/gaps/test_topic_priority.py` |
| Citation gaps are run-scoped and topic-based | `tests/gaps/test_citation_gaps.py` |
| Recommendation generation: LLM path, template fallback, budget gate, evidence, social recs | `tests/recommendations/test_generator.py` |
| BM25 chunking and retrieval | `tests/recommendations/test_rag.py` |
| `:memory:` shared-cache resolution and default DB path | `tests/test_db_path.py` |
| Full pipeline on `random-mock` end to end | `tests/integration/test_full_pipeline.py` |
| Priority filter is case-insensitive | `tests/test_prompt_filters.py` |
| Configured competitors reach Module 3 | `tests/test_competitor_config.py` |
| Placeholder run row is visible to the progress poll | `tests/dashboard/test_run_progress.py` |
| Gaps carry `affected_prompts` | `tests/gaps/test_detector.py` |
| Standalone Module 6 runs persist | `tests/dashboard/test_module6_standalone.py` |

Useful invocations: `pytest tests/ -q`, `pytest tests/recommendations -q`, `pytest -k budget -q`, `pytest tests/ --cov=aeo_eval`.

---

## 18. Key design decisions and their consequences

1. **Module decoupling through the database, not through return values.** Each stage reads its inputs from SQLite and writes its outputs back (metrics read `response_analysis`, gaps read `visibility_metrics` and `citation_occurrences`, recommendations read `gaps`). The orchestrator passes only `run_id` and a connection. *Consequence:* any stage can be re-run in isolation against a stored run, and the dashboard sees intermediate results while a run is in flight; the price is more SQL and the need for the `prompts` catalog table and the `processing` status hold.

2. **SQLite, one file, connection per call.** Chosen for the scale (hundreds of evaluations a year, one-year retention) and zero-ops deployment. *Consequence:* the `:memory:` shared-cache special case, `PRAGMA foreign_keys` on every connection, delete-children-first everywhere, and possible lock contention with four writer threads plus the dashboard.

3. **Persist first, analyse second, never fail the run for analysis.** Raw answers are the expensive, irreproducible artefact; extraction can be re-run. *Consequence:* `response_analysis` may be missing for some responses; metrics compute over analysed responses only.

4. **Budget as a reservation, not a post-hoc check.** Estimated cost is reserved under a lock before a prompt is submitted and replaced by actual cost on completion. *Consequence:* the limit is a hard ceiling even with concurrency, at the cost of some under-utilisation (failed calls keep their estimate; the estimate is fixed regardless of prompt length).

5. **Hybrid extraction: rules decide presence, the LLM decides nuance.** Brand mention is a substring match; position, claims, sentiment and confidence are LLM-extracted with a JSON schema. *Consequence:* mention rate is deterministic and cheap to audit; the LLM cannot "miss" Striim, but the persisted competitor data is name-only.

6. **Schema-constrained structured output everywhere an LLM returns data.** Anthropic `output_config.format=json_schema` / OpenAI strict `json_schema`. *Consequence:* no free-text parsing, but every schema must be fully required + `additionalProperties:false`, and truncation at `max_tokens` is the dominant failure mode (handled by returning `raw_response` and logging the config key).

7. **Mock engines analyse themselves.** A mock run should be free and instant. *Consequence:* mock analyses do not describe the stored answer, and mock runs can still spend real money in Module 9 if an Anthropic key is present.

8. **Recommendation LLM spend is capped by what evaluation left over.** Module 9 makes up to five calls per gap and could easily outspend evaluation. *Consequence:* later gaps degrade to template recommendations rather than being dropped, and the run's stored cost includes recommendation spend.

9. **Lexical BM25 instead of embeddings for methods retrieval.** The corpus is six short sections; a vector store and an embeddings provider would add a dependency and a network call per gap for no measurable gain. *Consequence:* no extra provider, deterministic retrieval, and the `embedding` column is dormant.

10. **Two auto-approval thresholds that happen to agree.** The generator's `>= 8` sets `pending_publish`; the orchestrator's `>= 7` approves. *Consequence:* `pending_publish` is transient on the orchestrator path, and changing one threshold without the other would silently split behaviour.

11. **Fail-open accessibility checks.** Unreachable `robots.txt` counts as allowed; every network exception yields a row rather than an abort. *Consequence:* Module 6 can under-report blocking; treat `fetch_failed`/`check_failed` counts as a data-quality signal.

12. **Dashboard runs the pipeline in-process on a thread and reads progress from the DB.** No job queue, no IPC. *Consequence:* one run at a time per dashboard process, and the run row's timestamp must be written in the same ISO form the poll compares against (it is; see §14).

---

## 19. Known sharp edges and inconsistencies

Verified against the code on 2026-09-16. None are hidden; all are documented here so nobody rediscovers them the hard way.

**Fixed on 2026-09-16** (kept here so the history of the behaviour is findable; each has a regression test, see §17):

- *CLI `--priority` never matched* — `Evaluator._filter_prompts` now compares priority case-insensitively.
- *Configured competitors were ignored* — Module 3 now reads `config.evaluation.competitors` via `competitors_to_track()`; the hardcoded list is a fallback for an empty config only. Note this changes which brands appear in `competitor_mention_rates` for new runs (Qlik Replicate and Estuary appear; Kafka no longer does unless added to config), so trend charts spanning the change will shift.
- *Recommendation evidence never fired* — `GapDetector` now populates `affected_prompts` (§10), which activates `_build_gap_evidence` and makes recommendation prompts materially longer (more input tokens per Module 9 call; the budget gate's fixed 4000-token estimate still bounds spend).
- *Dashboard progress banner lagged a whole stage* — `save_run` writes the placeholder run timestamp in ISO form.
- *Standalone Module 6 button failed on the FK* — `run_module6_standalone` creates a parent `evaluation_runs` row (`engine="module6"`) first; `fetch_all_runs` hides those rows from the run selector.

**Correctness**

1. **Dashboard cost-by-topic over-counts.** `fetch_cost_by_topic` sums the run's total cost once per topic row; `SQLiteStore.get_cost_by_topic` (proportional allocation) is the correct one and is unused by the UI.
2. **Citation-gap "percentages" are counts.** `top_competitor_visibility` holds a count for citation gaps and is formatted with `:.0%` in recommendation text and the dashboard (6 citations → "600%").
3. **`methods.txt` is CWD-relative.** Running the CLI from another directory silently drops methodology context from all recommendation prompts.
4. **Retry classifies with Anthropic exception types for every engine** and retries unknown exceptions by default, so Anthropic 4xx errors (other than rate limit) are retried three times, and OpenAI errors are retried only by falling through the default.

**Persistence**

5. Not persisted anywhere: `RunResult.run_type/engine_name/run_timestamp` (the last is used for the run row's timestamp but not stored per response), `EvaluationRun.run_notes/run_type/total_*_tokens`, recommendation `type/will_auto_publish/diagnosis/root_causes/article_suggestion/content_outline/hashtags/frequency`, LLM competitor positions from Module 3, `citations.page_title/extraction_metadata`, `citation_occurrences.claim_text`.
6. `review_notes` is JSON-encoded two ways: `{"reason": …}` by `reject_recommendation`, a bare JSON string by `update_recommendation_status` (which the dashboard uses). Readers must accept both.
7. The dashboard Edit form issues raw SQL instead of `update_recommendation`, bypassing the allow-list and error handling.
8. `delete_run` (unused) omits `website_checks`/`crawler_logs` and would hit an FK error for runs that have them.
9. `recommendation_templates` has CRUD and an index but no producer or consumer; `templates_applied` is always NULL.
10. Standalone Module 6 parent rows (`engine="module6"`, `num_prompts=0`, `cost=0`) live in `evaluation_runs`. The dashboard's `fetch_all_runs` filters them out, but `SQLiteStore.get_cost_by_engine`/`get_all_runs_cost_detail` and `cli history` (when implemented) will list them.

**Concurrency and limits**

11. `RateLimiter` has no lock and is called from four threads.
12. `retry_policy.*` in `config.yaml` is not read; only `providers.<name>.max_retries` reaches the policy.
13. `ClaudeEngine.run` answers with a hardcoded `max_tokens=2000`; the configurable `max_tokens` applies to structured output only. `OpenAIEngine` uses 2000 for both.
14. `get_today_cost` uses the local date; its docstring says UTC. The daily limit resets at local midnight.
15. `urllib.robotparser.read()` has no timeout; a hanging `robots.txt` fetch stalls Module 6.

**Documentation elsewhere in the repo**

16. `README.md` and `docs/dashboard-guide.md` were trimmed on 2026-09-16 to remove claims about features that do not exist (`llms.txt` and sitemap checks, by-persona/by-engine metrics, six gap types, `history`/`schedule` CLI commands). `docs/recommendations-architecture.md` §5 describes the pre-BM25 embedding path and has been annotated to point here.

---

## 20. Extension recipes

**Add an answer engine (e.g. Perplexity).**
1. Create `aeo_eval/engine/perplexity_engine.py` subclassing `BaseEngine`; set `name = "perplexity"`; implement `run` returning `RunResult` for every outcome and `run_with_structured_output` if the provider supports JSON schema (otherwise leave the base `NotImplementedError` and set `analysis_provider` to Claude).
2. Register `"perplexity": "aeo_eval.engine.perplexity_engine:PerplexityEngine"` in `config.PROVIDERS`. The CLI choices and dashboard radio update automatically.
3. The `providers.perplexity` config section and `PERPLEXITY_API_KEY` overlay already exist.
4. Add exception classes to `RetryPolicy` sets if you want classification rather than default-retry.

**Change what counts as an "affected prompt".**
`GapDetector._topic_prompt_ids(run_id, topic, missed_only)` is the single query behind `affected_prompts` for both gap types. Tightening it (for example, only prompts where a competitor was mentioned and Striim was not) changes the evidence block in every recommendation prompt; keep `_EVIDENCE_MAX_QUESTIONS` in `generator.py` in mind, since only the first 8 ids are used.

**Add a gap type.**
Add a `detect_<type>_gaps(run_id)` method returning dicts with the same keys as the existing ones, extend `detect_all_gaps`, and add a branch in `RecommendationGenerator.generate_for_gap`'s template `elif` chain (otherwise it falls into the generic "Investigate" template). The dashboard filter list in `render_gaps_recommendations_view` is a hardcoded list to extend.

**Add a metrics dimension (by persona).**
Mirror `calculate_metrics_by_topic` joining `prompts.persona`, emit `dimension="by_persona"`, and call it from the orchestrator. `visibility_metrics` already has the columns; `fetch_metrics_for_run` in the dashboard filters `dimension IN ('overall','by_topic')` and would need the new value.

**Wire Module 7 into the CLI.**
Add `--logs PATH` to `cmd_run`, and after evaluation: `records = RequestLogAnalyzer().analyze(RequestLogParser().parse_file(path)); for r in records: r["run_id"] = run_id; store.store_crawler_logs(records)`. The Request Logs dashboard view already reads the table.

**Add a column.**
Add it to `sqlite_schema.sql` (for new databases) **and** to `apply_schema_migrations` (for existing ones), then to the relevant `_row`/INSERT and the read-side `_parse_json_field` list if it is JSON.

**Add a dashboard view.**
Write `fetch_*` functions returning `sqlite3.Row`s, a `render_*_view(run)` function, and add a tab or a `view_mode` branch in `main`. Keep pure formatting in `formatting.py` so it stays unit-testable without Streamlit.

---

## 21. Glossary

- **AEO** — Answer Engine Optimization: being the passage an AI answer engine extracts or cites, as opposed to ranking on a results page.
- **Answer engine** — the LLM product being evaluated (Claude, OpenAI); in code, an `engine` with `run()`.
- **Analyzer engine** — the engine used for Module 3 structured extraction; Claude by default, the engine itself for mocks.
- **Run / batch** — one `Evaluator` execution; `run_id == run_batch_id == evaluation_runs.run_id`.
- **Mention rate / recommendation rate / top-3 rate / citation rate** — see §8 formulas.
- **Citation occurrence** — one (citation, response analysis) pair; the unit of run-scoped citation counting.
- **Visibility gap / citation gap** — the two implemented gap types; §10.
- **Article recommendation / social recommendation** — the two recommendation types; one article per gap always, three social per gap on the LLM path.
- **Template path / LLM path** — recommendation generation without / with Claude; §11.
- **Budget gate** — the pre-call check that keeps Module 9 LLM spend within `cost_limit_per_run − evaluation spend`.
- **Methods corpus** — `methods.txt`, chunked into `method_sections` and retrieved with BM25 for recommendation prompts.
- **Fail-open** — Module 6's policy of treating unknown accessibility as allowed.
