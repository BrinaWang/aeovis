# AEO Visibility Platform — Project Writeup and Handoff

*State as of 2026-09-16. Repository: `aeovis` (branch `main`). Tests: 278 passing.*

This is the single document to read when taking over the project. It covers why the project exists, what it is made of (data, corpus, code), how the implementation works, how to operate it, what is done, what is not, and what to watch out for. Where a topic needs code-level depth, it points to `architecture.md`, which is the line-by-line technical reference; this document does not repeat that detail but is complete enough to run and change the system without it.

Companion documents in the repository:

| File | What it is |
|---|---|
| `README.md` | Quick start, CLI reference, configuration overview |
| `architecture.md` | Implementation-level reference: control flow per stage, formulas, schema, engine layer, design decisions, sharp edges, extension recipes |
| `docs/recommendations-architecture.md` | Older deep-dive on Module 9 persistence and status workflow; partly superseded, annotated to say where |
| `docs/dashboard-guide.md` | End-user guide to the Streamlit dashboard |
| `spec.md` | The original product specification (what the platform *should* do; broader than what is built) |
| `docs/superpowers/specs/`, `docs/superpowers/plans/` | Design spec and implementation plans from August 2026, kept as history |
| `considerations.txt` | Working notes: stakeholder asks, ICP notes, TODO list |
| `methods.txt` | The AEO methodology corpus that grounds recommendation prompts |
| `skills/striim-aeo/` | A portable Claude skill that approximates the platform without the code |

---

## 1. Background

### 1.1 The problem

Buyers increasingly ask AI answer engines (ChatGPT, Claude, Perplexity, Gemini, Google AI Overviews) questions like "what are the best Oracle CDC tools?" instead of running a web search. Those engines answer with a short list of vendors and a handful of cited pages. If Striim is not named, or is named below competitors, or its pages are never cited, Striim is invisible at the top of the funnel regardless of how well it ranks in classic search.

This discipline is called **Answer Engine Optimization (AEO)**. It differs from SEO in ways that matter for how the platform is built: retrieval is passage-level rather than page-level, citation and ranking are only loosely correlated, answers vary from run to run for the same prompt, and much of a brand's citability comes from third-party sources rather than its own site. `methods.txt` §1–6 summarises the methodology the team collected; it is worth reading in full (it is about seven kilobytes).

### 1.2 What the platform is for

The platform is an **internal measurement and recommendation tool for Striim's marketing and content teams**. It answers six questions on a repeatable basis:

1. How often does Striim appear for important buyer questions?
2. Which competitors appear more frequently?
3. Which webpages and domains get cited?
4. Can AI crawlers discover and access Striim's important pages?
5. Why might Striim be missing or misrepresented?
6. What should Striim do next?

It is explicitly *not* a tool that promises a mention or a citation. Every recommendation is framed as an evidence-backed hypothesis with a measurement plan, and the methodology notes are blunt that single before/after comparisons are not trustworthy because answer engines are non-deterministic.

### 1.3 Who it is for and who the buyer is

- **Users of the platform:** Striim's content/marketing team (recommendations are owned by "Content Team", "Marketing Team", "Product Manager" or "Engineering"), plus whoever operates the runs.
- **Striim's ideal customer profile** (from `considerations.txt`): enterprises with large budgets, deals in the $100k–$250k range and sometimes $1M, not startups or ten-person companies. This is why the question panel is written in the voice of senior buyers (CTO, CDO, VP of AI, CISO) and why "enterprise" appears in so many prompts.
- **Stakeholder asks captured in notes:** swap questions periodically to follow monthly trends; add G2, GigaOm and TrustRadius as third-party sources to watch; investigate "agent experience" (how AI agents experience a website); investigate Cloudflare blocking of AI crawlers; surface the top five high-priority recommendations as warnings; consider Reddit strategy; keep questions and personas reviewed with Simon.

### 1.4 Timeline

| Date | Milestone |
|---|---|
| 2026-08-12 | Question panel v1.0 created (75 questions, 8 topics, 6 personas) |
| 2026-08-14 | Design spec for Modules 3–10 written (`docs/superpowers/specs/`) |
| 2026-08-17 | Modules 3, 4, 5, 8, 9 implemented; a fourteen-bug correctness batch fixed |
| 2026-08-19 | First commit to GitHub ("Local Overhaul to Github") |
| 2026-08-25/26 | Modules 6 and 7 implemented; README revised; ready for API-key testing |
| 2026-08-28 | Large bug-fix day: `.env` loading, None-handling in token/cost paths, mock run-id isolation, dashboard fixes |
| 2026-09-03 | System prompt added so Claude includes URLs in answers (citations were empty before) |
| 2026-09-08 | Concurrent prompt execution (4 workers), thread-safe cost tracking, strict budget reservation |
| 2026-09-14/15 | Recommendation system overhaul: BM25 retrieval, evidence builder, cost budget, dashboard approval UI polish; portable `striim-aeo` skill built |
| 2026-09-16 | Full documentation pass (`architecture.md`, docstrings); five bugs fixed with regression tests; README trimmed to match reality |

All 42 commits are by one author. There is no CI, no deployment target, and no shared database; the platform has only ever run on a laptop.

---

## 2. Content: the inputs the platform reasons over

The code is generic; the value is in these curated inputs. Anyone changing them changes what the platform measures.

### 2.1 Buyer question panel (`question.json`)

75 questions, all enabled, version 1.0, created 2026-08-12. Each has `id`, `prompt`, `topic`, `persona`, `intent` (`commercial` 42 / `educational` 33), `priority` (`high` 42 / `medium` 32 / `low` 1), optional `variant_of` and `tags`.

Topics and counts:

| Topic | Questions | Example |
|---|---|---|
| AI Data Infrastructure | 24 | "Best tools for real-time AI monitoring for enterprise businesses?" |
| Data Governance & Compliance | 16 | "We have data in Snowflake, Oracle, and our data lake—how do we govern all of it without building separate pipelines?" |
| Real-Time Data Integration | 12 | "Best enterprise data integration tools that support real-time data and batch processing" |
| Data Replication | 8 | "Best solution to replicate data to multiple destinations at once for enterprise businesses?" |
| CDC Tools & Platforms | 5 | "Best change data capture tools for PostgreSQL" |
| Cloud Data Warehouse Integration | 4 | "Best real-time data pipeline tools for Snowflake or BigQuery" |
| Comparisons & Alternatives | 3 | "best confluent alternatives for enterprise businesses?" |
| Oracle CDC | 3 | "What tools support real-time CDC for Oracle?" |

Things a handler should know about the panel:

- The `id` is the join key across runs. Renaming ids breaks trend continuity; retire a question by setting `enabled: false` rather than deleting it.
- Topics with fewer than three answered questions can never produce a visibility gap (the detector requires `num_responses >= 3`). Three topics are at or near that floor.
- `priority` drives the visibility threshold per topic (high 15%, medium 5%, low 2%). The highest priority among a topic's questions is used for the whole topic.
- The stakeholder intent is to refresh questions monthly to follow trends. Nothing automates that yet; `considerations.txt` floats using Claude to draft new questions plus a text extractor.

### 2.2 Personas (`personas.json`)

Six profiles: Head of Data / CDO, VP of AI, VP of Engineering / CTO, Data Scientist, AI Product Manager, CISO. Each has title, description, company sizes, industries, key concerns, risk tolerance, ROI focus, decision timeline, evaluation criteria and a one-line core need. The pipeline stores persona per prompt and can filter on it, but no metric is computed by persona yet. The personas are mainly used by humans (and by the portable skill) to interpret why a question is asked.

### 2.3 Competitors, pages, crawlers (`config.yaml → evaluation`)

- **Competitors tracked:** Fivetran, Oracle GoldenGate, Qlik Replicate, Confluent, AWS DMS, Estuary. Brand detection is case-insensitive substring matching, so "Estuary Flow" matches "Estuary" and "Confluent Kafka" matches "Confluent". Brands not in the list (Debezium, Airbyte, Informatica, Talend) are not counted even if answers name them.
- **Important Striim pages:** `/product/`, `/solutions/`, `/docs/`, `/customers/` on `www.striim.com`. These are the pages Module 6 checks for crawler accessibility.
- **Crawlers:** OAI-SearchBot, PerplexityBot, Claude-SearchBot, ClaudeBot, Googlebot, Bingbot, GPTBot, ChatGPT-User, Perplexity-User. Used for `robots.txt` evaluation.

### 2.4 Methodology corpus (`methods.txt`)

Six numbered sections: the SEO-vs-AEO shift, page organisation (answer-first, question-phrased headings, chunking, specificity, E-E-A-T, recency, `llms.txt`/`sitemap.xml`), opportunity-vs-age prioritisation, off-site methods (third-party mentions, Reddit, paid placement, entity consistency), measuring efficacy (three stages: crawler access, citability, follow-through; panel-based measurement; query failures; attribution), and visibility targets. It is chunked into a small retrieval corpus and the three most relevant sections are injected into every recommendation prompt. Edit it freely; it is re-indexed on every run. Keep the `N. Heading` numbering format, which the chunker depends on.

### 2.5 The portable skill (`skills/striim-aeo/`)

A Claude skill built on 2026-09-15 that lets an analyst reproduce the platform's method without the code: the same 75 questions, competitor set, thresholds, recommendation contract and methodology, plus a "gold example" (a real recommendation the team approved) as the quality bar. Copies live at `~/.claude/skills/striim-aeo/` and in a zip for claude.ai upload. It is a snapshot; if the panel, thresholds or recommendation rules change in the code, regenerate the skill's `data/` and `references/` files from the source.

---

## 3. What the platform produces

One **run** evaluates a batch of questions against one answer engine and writes:

- **Raw answers** with tokens, cost, latency and status (every attempt, including failures).
- **Per-answer analysis**: whether Striim was mentioned and recommended, its list position, brands found, claims about Striim with sentiment, all cited URLs, extraction confidence, and a review flag.
- **Visibility metrics**, overall and per topic: mention rate, recommendation rate, top-3 rate, average position, citation rate, competitor mention rates.
- **Citations**: a cross-run catalogue of unique URLs with source category (Striim-owned, competitor, partner docs, review platform, technical publication, community, other) and per-run occurrences.
- **Website accessibility checks** (optional): per page × crawler, robots.txt allowed, HTTP status, noindex, canonical, extractability, one classification string.
- **Gaps**: visibility gaps and citation gaps per topic with priority, confidence and the affected question ids.
- **Recommendations**: per gap, one article recommendation (title, target URL, the competitor page to displace, one step per H2 naming the verbatim questions it answers, schema markup, internal links, review, re-measure) plus Reddit, LinkedIn and Facebook social plans; each with priority 1–10, effort 1–3, owner, measurement plan and an approval status.
- **Run-level cost**, folded from engine, analyzer and recommendation spend.

The dashboard shows all of this per run, compares runs over time, hosts the approve/edit/reject workflow, and can launch runs. A plain-text report is available from the CLI.

What a "good" recommendation looks like is defined by the gold example in `skills/striim-aeo/references/gold-example.md`: an "AI Data Infrastructure" article brief whose every step names exact URLs, exact H2 headings, verbatim panel questions, a done-test, effort and owner. Prompts enforce this with explicit specificity rules; any sentence that would survive with the topic swapped out is considered a failure.

---

## 4. Technical implementation

### 4.1 Shape of the system

A Python 3.9+ package (`aeo_eval`) plus a SQLite file. No server, no queue, no cloud resources. Three front doors converge on one class:

```
CLI  (python -m aeo_eval.cli run …)        Streamlit dashboard (background thread)        Scheduler (APScheduler, not wired)
                        └────────────────────────────┬────────────────────────────────────┘
                                   AEOPipelineOrchestrator.run_full_pipeline(prompts, options)
                                                     │
                                          SQLite  data/eval_runs.db
```

Dependencies (from `pyproject.toml`): `anthropic`, `openai`, `pydantic`, `pyyaml`, `apscheduler`, `httpx`, `beautifulsoup4`, `trafilatura`, `streamlit`, `plotly`, `pandas`; dev: `pytest`, `pytest-asyncio`, `pytest-mock`, `freezegun`. `python-dotenv` is imported by the CLI and dashboard for `.env` loading.

### 4.2 The pipeline, in order

`aeo_eval/orchestrator.py` is the only place the stages are composed. Read it top to bottom once; `architecture.md` §5 annotates every line.

1. **Preconditions.** Create/migrate the schema. Refuse to start if today's total spend already meets `general.cost_limit_per_day`. Purge rows past their retention window.
2. **Module 2 — answer engine** (`runner/evaluator.py`). For each prompt: reserve an estimated budget slice under a lock, call the engine on one of up to four worker threads, persist the answer whatever its status. The per-run cost limit is a hard ceiling because the reservation happens before submission.
3. **Module 3 — response analysis** (`analysis/`), inline per successful answer. Brand presence by substring match against the configured competitor list; position, claims, sentiment and confidence by a JSON-schema-constrained call to the *analyzer* engine (Claude by default; the engine itself for mocks). Citations are all URLs in the text. Analyzer cost counts against the same run budget.
4. **Run status hold.** The run is marked `processing` until every later stage finishes, then restored to `completed` / `partial_failure` / `failed`.
5. **Module 4 — metrics** (`metrics/calculator.py`). Overall and per-topic rates from the analysis rows.
6. **Module 6 — website accessibility** (`website_accessibility/`), only if `evaluation.run_website_accessibility_checks` is true. Per page: one HTTP fetch for status/noindex/canonical and one for extractability (trafilatura word count and text ratio); per page × crawler: `robots.txt` evaluation, fail-open. One classification per pair.
7. **Module 5 — citations** (`citations/`). Normalise URLs (lower-case scheme/host, strip query/fragment/trailing slash), classify by domain, upsert into the cross-run catalogue, record per-answer occurrences.
8. **Module 8 — gaps** (`gaps/`). Visibility gap when a topic's Striim mention rate is under its priority threshold or a competitor exceeds 2× Striim; citation gap when a topic has three or more competitor citations and none for Striim. Priority from the gap ratio, confidence from sample size, affected question ids recorded.
9. **Module 9 — recommendations** (`recommendations/`). For each gap, up to five Claude calls: diagnosis, article brief, three social plans. Each prompt carries the run's evidence (question text, what engines answered, pages cited) and the three most relevant methodology sections (BM25). Spend is capped at whatever the per-run limit has left after evaluation; once the cap is hit, later gaps get free template recommendations. If no Claude key is available, everything takes the template path.
10. **Auto-approval.** Recommendations with priority ≥ 7 and high confidence are approved by `system`; the rest wait as drafts in the dashboard.

Module 7 (request logs: JSONL parser, user-agent classifier, normaliser) exists as library code with tests but is not called by any entry point.

### 4.3 Engines

`aeo_eval/engine/`. A `BaseEngine` contract with two methods: `run(prompt) -> RunResult` (never raises for provider errors; returns a status) and `run_with_structured_output(prompt, schema)` (JSON-schema-constrained; may raise). Implementations: `ClaudeEngine` (Anthropic Messages API, `output_config.format = json_schema` for structured calls), `OpenAIEngine` (chat completions, strict `json_schema`), `MockEngine` (canned answer, no structured output, so mock runs stop after persistence) and `RandomMockEngine` (realistic CDC-market answers with URLs, deterministic structured output, fabricates Module 6/7 rows; drives the full pipeline offline). A registry in `config.py` maps names to classes; `create_engine(name)` builds one from the matching provider config with the API key overlaid from the environment.

Cross-cutting: per-1k-token pricing from config, exponential-backoff retry (3 retries, 100 ms base, ×2, ±10% jitter; unknown exceptions are retried), and a dual token bucket rate limiter (TPM and RPM) per engine instance.

Gemini, Grok and Perplexity have config sections and API-key wiring but no engine class.

### 4.4 Storage

`aeo_eval/storage/`. Thirteen tables declared in `sqlite_schema.sql` (all `IF NOT EXISTS`), applied on every start; the one Python migration adds three columns to `recommendations` on old databases. `SQLiteStore` opens a fresh connection per call, so it is safe across threads; structured columns are JSON text. Retention: 365 days for raw answers, analyses, citations (by last observed) and website checks, 90 days for crawler logs, forever for metrics, gaps and recommendations, so recommendations outlive their raw evidence. `:memory:` is special-cased to a shared-cache database for tests.

Key relationships: `evaluation_runs → raw_responses → response_analysis → citation_occurrences → citations`; `evaluation_runs → visibility_metrics`, `→ gaps → recommendations`, `→ website_checks`, `→ crawler_logs`. `prompts` is upserted each run so topic joins work.

### 4.5 Dashboard

`aeo_eval/dashboard/app.py` (Streamlit, single file, three layers: `fetch_*` SQL readers, `render_*` views, `main`). Pages: Dashboard (KPI strip plus tabs for Gaps & Recommendations, Citation Analysis, Run Comparison, Trends & Details, Recommendations Management), Cost Analysis (daily budget, per-engine/topic costs, editable limits that also rewrite `config.yaml`), Module 6 Checks (run and review accessibility checks). "Configure & Run" launches a pipeline on a daemon thread and polls the database every four seconds for progress. Approve/Reject go through `SQLiteStore`; Edit issues a direct SQL update.

### 4.6 Configuration and secrets

`config.yaml` (committed) holds providers, limits, retry policy, competitors, pages, crawlers and scheduling defaults. `.env` (git-ignored; template in `.env.example`) holds API keys; they are overlaid onto the provider config at import time. Current live limits: **$5 per run, $7 per day**, Claude model `claude-sonnet-5` at $0.002/$0.01 per 1k tokens, 8000 max tokens for structured output, 300 s timeout. Anyone with `ANTHROPIC_API_KEY` set will spend real money on recommendation generation even on mock runs; see §7.

### 4.7 Testing

278 pytest tests, about 100 seconds, no network. `tests/conftest.py` redirects the database to a temp file and removes the Anthropic key for every test, so nothing can touch `data/` or the API by accident. Layout mirrors the package. The most load-bearing tests assert: every result is persisted, budgets are never exceeded under concurrency, structured output is schema-enforced, retention is FK-safe, citation history survives across runs, gaps and recommendations behave on the LLM and template paths, and the full pipeline runs end to end on `random-mock`.

---

## 5. Operating the platform

### 5.1 Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -e .[dev]
cp .env.example .env        # add ANTHROPIC_API_KEY (and OPENAI_API_KEY if wanted)
pytest tests/ -q            # expect 278 passed
```

Always run from the repository root: `methods.txt` is opened relative to the current directory.

### 5.2 Running

```bash
# Free, offline, exercises every stage:
python -m aeo_eval.cli run --engine random-mock --limit 30

# Real evaluation (analysis and recommendations also on Claude):
python -m aeo_eval.cli run --engine claude --limit 20 --notes "September baseline"

# Filters (topic exact-match, priority case-insensitive), cost cap, separate DB:
python -m aeo_eval.cli run --engine claude --topic "Oracle CDC" --priority High --cost-limit 3 --db data/oracle.db

# Cost estimate only (no calls): --dry-run
# Plain-text report:            python -m aeo_eval.cli report <run_id>
# Dashboard:                    streamlit run streamlit_app.py   (or bash scripts/dashboard.sh)
```

`--limit` is applied before the topic/priority filters, so `--limit 30 --priority High` may run fewer than 30. The CLI summary's "Prompts" line shows the pre-filter count.

### 5.3 Cost expectations

Reservation estimate per prompt is fixed at 1000 input + 1500 output tokens ($0.017 at current Claude pricing); real answers with the "include URLs" system prompt and analyzer calls land in the same range. Recommendation generation is the expensive stage: up to five calls per gap, each budgeted at roughly $0.09, so a run with ten gaps can spend about $4 on recommendations alone. That is why the per-run limit is $5 and recommendations are capped at what evaluation leaves over. Raise limits in `config.yaml` (or the dashboard Cost page) deliberately.

### 5.4 Data and backups

Everything is in `data/eval_runs.db` (git-ignored). Back it up by copying the file when no run is in progress. `scripts/migrate_add_run_id.py` shows the pattern used for a past manual migration (copy to `.db.backup`, alter, commit). There is no export beyond `sqlite3` queries and the dashboard tables.

### 5.5 Scheduling

Not operational. `aeo_eval/scheduler.py` wraps APScheduler with in-memory job storage and re-enters the CLI; nothing constructs it and the `schedule` subcommand is a stub. For a recurring monthly run today, use cron or a CI schedule to invoke the CLI.

---

## 6. Status: implemented versus specified

`spec.md` is more ambitious than the code. The honest map:

| Area | Specified | Built | Notes |
|---|---|---|---|
| Question panel | 40–60 questions | 75 | Manual refresh |
| Answer engines | Two approved integrations | Claude, OpenAI, two mocks | Gemini/Grok/Perplexity config only |
| Response analysis | Brand, position, claim, sentiment, citation | Yes | Brands by rules, rest by LLM; competitor positions from the LLM are not persisted |
| Metrics | By topic, persona, engine, time | Overall + by topic; trends across runs | By persona / by engine not computed |
| Citation intelligence | Normalise, rank, classify | Yes | `page_title` never populated; no content comparison |
| Website checks | robots, sitemap, HTTP, redirects, canonical, noindex, llms.txt, extractability | robots, HTTP, redirects, canonical, noindex, extractability | Sitemap, llms.txt, JS-render detection missing; optional in pipeline |
| Request logs | One format ingested | Parser/classifier as library | Not wired to any entry point |
| Gap types | Six | Two (visibility, citation) | Content, technical, authority, agent-experience not built; no cross-type merging |
| Recommendations | Evidence-backed gap-to-action | Yes, LLM + template, budgeted | Article title/sections and social plans exist only in memory after the run |
| Approval workflow | Yes | Yes (dashboard) | `implemented` status defined, never set |
| Dashboard | Visibility, prompt explorer, citation, website access, action queue | Visibility, citations, gaps/recs, run comparison, approval, cost, Module 6 | No per-prompt explorer with raw answers |
| Evaluation dataset | Labeled test set + case study | Neither | Accuracy of extraction has not been measured against labels |
| Scheduling | Cron | Library only | |
| Deployment | Docker, FastAPI | Neither | Laptop only |

---

## 7. Things a handler must know (risks and sharp edges)

The full list with code references is `architecture.md` §19. The ones that bite operationally:

1. **Mock runs can cost money.** If `ANTHROPIC_API_KEY` is set, a `random-mock` run still builds a Claude engine for recommendations and spends up to the whole per-run limit. Unset the key (or set it empty) for free demo runs.
2. **Recommendation prompts got longer on 2026-09-16.** Gaps now carry affected question ids, so evidence is injected into every Module 9 prompt. Input tokens per call went up; the fixed per-call budget estimate still caps total spend but fewer gaps may get the LLM path under a tight limit.
3. **Competitor detection changed on 2026-09-16.** It now follows `config.yaml`, so Qlik Replicate and Estuary appear and Kafka does not (add it to the config if wanted). Trend charts spanning that date will show a shift that is measurement, not market movement.
4. **`methods.txt` is loaded relative to the working directory.** Run from the repo root or recommendations silently lose their methodology context.
5. **Answer-engine non-determinism.** Identical runs produce different citation sets. Do not read a single run-over-run delta as a result; the methodology notes call for a repeated panel and a site-wide control.
6. **Retry treats unknown errors as retryable**, and classifies with Anthropic exception types even for OpenAI. A malformed request is retried three times before failing.
7. **The rate limiter is not thread-safe** and uses a fixed token estimate; with four workers it can over-admit slightly. Provider-side 429s are handled by retry.
8. **Dashboard cost-by-topic over-counts** multi-topic runs (`SQLiteStore.get_cost_by_topic` has the correct proportional allocation and is unused by the UI).
9. **Citation-gap "percentages" are counts** (a citation gap's competitor figure is a count stored in a rate column and formatted as a percentage).
10. **Recommendations outlive their evidence** (365-day retention on raw answers, none on recommendations).
11. **`config.yaml` is rewritten by the dashboard** when limits are saved; comments in the file are lost.
12. **`robots.txt` fetches have no timeout**; a hanging fetch stalls Module 6.
13. **Single-author, single-machine history.** No CI, no code review trail beyond commit messages and the plan documents.

---

## 8. Decisions worth knowing before changing things

Full rationale in `architecture.md` §18. In brief:

- **Modules decouple through the database.** Each stage reads the previous stage's tables and writes its own, keyed by `run_id`. You can re-run one stage against a stored run. The cost is more SQL and the `processing` status hold so the dashboard does not show a half-finished run as complete.
- **SQLite, one file, connection per call.** Right for the scale and for zero ops. Do not move to a server database without need; the `:memory:` handling and FK ordering are the only complications.
- **Persist first, analyse second, never fail the run for analysis.** Raw answers are the irreplaceable artefact.
- **Budget by reservation, not post-hoc check.** Cost limits are real ceilings under concurrency.
- **Rules decide brand presence; the LLM decides nuance.** Mention rate is deterministic and auditable.
- **Structured output everywhere an LLM returns data.** No free-text parsing. Every schema must be fully `required` with `additionalProperties: false`; truncation at `max_tokens` is the failure mode to watch.
- **Mocks analyse themselves** so demo runs are free and instant.
- **Recommendation spend is bounded by what evaluation leaves over**, degrading to templates rather than dropping gaps.
- **BM25 over embeddings for a six-section corpus.** No extra provider, deterministic.
- **Fail-open accessibility checks.** Unknown is treated as allowed; read `fetch_failed` counts as a data-quality signal.

---

## 9. Open work and suggested next steps

From `considerations.txt`, `spec.md`, and the gaps above, roughly in order of value:

1. **Run the real baseline and keep it.** There is no committed labeled dataset or case study. Run the full panel on Claude and OpenAI monthly, keep the database, and start the site-wide control the methodology calls for.
2. **Question refresh process.** Decide cadence and ownership; add questions with new ids and disable old ones rather than editing text, so trends remain comparable.
3. **Persist the rest of the recommendation.** Article title/sections, diagnosis, root causes and social plans are lost after the run. Add columns (schema + migration + `_recommendation_row`) or a JSON `details` column.
4. **Wire Module 7.** A `--logs PATH` flag plus three lines in the CLI would populate the Request Logs view from real (sanitised) logs; that is the only way to validate Module 6 against actual crawler behaviour and to investigate the Cloudflare-blocking question.
5. **Third-party authority tracking.** G2, GigaOm, TrustRadius, Reddit: extend the citation classifier and add an authority gap type (sources citing competitors but not Striim). The classifier already has `review_platform` and `community_content` buckets.
6. **Agent-experience checks.** `llms.txt` presence and coverage, sitemap membership, JS-render dependence; these complete Module 6 as specified and feed an agent-experience gap type.
7. **Dashboard: top-five high-priority warnings** on the landing page (a stakeholder ask), a per-prompt explorer showing raw answers, and using `get_cost_by_topic` instead of the over-counting query.
8. **Operational hardening if it leaves the laptop.** Cron-driven runs, a backup of `eval_runs.db`, a lock on the rate limiter, timeouts on `robots.txt`, and CI running `pytest`.
9. **Labeled evaluation set.** A small set of answers with known brands/positions/citations to measure extraction precision and recall, as `spec.md` §Evaluation asks.

---

## 10. How to get oriented in the first hour

1. Read `README.md` for the quick start, then this document, then skim `architecture.md` §5 (the pipeline) with `aeo_eval/orchestrator.py` open beside it.
2. Run `pytest tests/ -q` and a `random-mock` run with no API key; open the dashboard against the resulting `data/eval_runs.db`.
3. Read `methods.txt` and the gold example in `skills/striim-aeo/references/gold-example.md` to internalise what a good recommendation is; that is the bar the prompts in `aeo_eval/recommendations/generator.py` enforce.
4. Read `question.json` and `personas.json`; they are the product.
5. Check `considerations.txt` for the stakeholder asks and TODOs that are not in any ticket system.
6. Before the first real run, confirm the limits in `config.yaml`, confirm you are in the repo root, and note the run id printed at the end; everything in the dashboard is keyed by it.
