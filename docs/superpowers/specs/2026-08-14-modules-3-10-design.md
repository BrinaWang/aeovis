# AEO Visibility Platform — Modules 3-10 Design Specification

**Date:** 2026-08-14  
**Author:** Design Review  
**Status:** Ready for Review  
**Scope:** Modules 3 (Response Analysis) through 10 (Dashboard), including complete async job architecture, database schema, and test strategy.

---

## Executive Summary

This specification describes the architecture for **Option B: Decoupled Analysis Modules** — a production-ready system that:

- **Processes 240 evaluations per run** (60 questions × 4 engines) with reliable async job orchestration
- **Maintains 1-year historical data** with SQLite (scalable to PostgreSQL)
- **Supports concurrent runs** without blocking or data conflicts
- **Implements approval workflows** for recommendations with status tracking
- **Ensures accuracy** through 70/20/10 unit/integration/E2E test pyramid and data validation at module boundaries
- **Scales horizontally** with Celery + Redis job queue (2-3 workers per queue type)

**Key Design Decision:** Modules decouple via database — each reads previous module's outputs, performs its analysis, and persists results. Failures in one module don't block others; failed analyses can be rerun independently.

---

## 1. Database Schema

### 1.1 SQLite Schema

All tables use SQLite 3.38+ JSON1 extension for complex data types. Schema file: `aeo_eval/storage/sqlite_schema.sql`

#### Core Tables

**evaluation_runs**
```sql
CREATE TABLE evaluation_runs (
    run_id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    engine TEXT NOT NULL,
    model TEXT NOT NULL,
    num_prompts INTEGER NOT NULL,
    filters TEXT,  -- JSON: {topic, persona, priority}
    status TEXT,   -- "completed", "partial_failure", "failed"
    cost REAL NOT NULL DEFAULT 0.0,
    duration_seconds INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INDEX: (timestamp DESC), (engine)
```
Tracks metadata for each evaluation batch (Module 2 output).

**raw_responses**
```sql
CREATE TABLE raw_responses (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    response_text TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost REAL DEFAULT 0.0,
    latency_ms INTEGER,
    status TEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
INDEX: (run_id, prompt_id, engine), (created_at DESC)
```
Immutable responses from Module 2. Never deleted during 1-year retention.

**response_analysis**
```sql
CREATE TABLE response_analysis (
    id TEXT PRIMARY KEY,
    raw_response_id TEXT NOT NULL,
    striim_mentioned INTEGER,
    striim_recommended INTEGER,
    striim_position INTEGER,
    brands_found TEXT,        -- JSON: [{name, position, is_recommended}, ...]
    claims TEXT,              -- JSON: [{text, sentiment, confidence, supporting_citation}, ...]
    citations TEXT,           -- JSON: ["https://...", ...]
    extraction_confidence REAL,
    flagged_for_review INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_response_id) REFERENCES raw_responses(id)
);
INDEX: (raw_response_id), (flagged_for_review)
```
Module 3 output. Extracted structured data from responses.

**citations**
```sql
CREATE TABLE citations (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    normalized_url TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,
    page_title TEXT,
    source_category TEXT,     -- "striim_owned", "competitor", "partner_docs", "review_platform", etc.
    first_observed DATETIME NOT NULL,
    last_observed DATETIME NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    extraction_metadata TEXT,  -- JSON: {engine, topics}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INDEX: (normalized_url), (domain), (source_category)
```
Module 5 output. Deduplicated, normalized citations.

**citation_occurrences**
```sql
CREATE TABLE citation_occurrences (
    id TEXT PRIMARY KEY,
    citation_id TEXT NOT NULL,
    response_analysis_id TEXT NOT NULL,
    claim_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (citation_id) REFERENCES citations(id),
    FOREIGN KEY (response_analysis_id) REFERENCES response_analysis(id)
);
INDEX: (citation_id), (response_analysis_id)
```
Maps citations to specific claims in responses. Links Module 3 and 5.

**website_checks**
```sql
CREATE TABLE website_checks (
    id TEXT PRIMARY KEY,
    striim_url TEXT NOT NULL,
    crawler TEXT NOT NULL,
    robots_allowed INTEGER,
    in_sitemap INTEGER,
    http_status INTEGER,
    response_time_ms INTEGER,
    noindex INTEGER,
    canonical_url TEXT,
    result TEXT,              -- "publicly_accessible", "blocked_by_robots", "http_error_4xx", etc.
    check_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INDEX: (striim_url, crawler), (check_timestamp DESC)
```
Module 6 output. Website accessibility for each (page, crawler) pair.

**crawler_logs**
```sql
CREATE TABLE crawler_logs (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    crawler TEXT,
    http_status INTEGER,
    response_time_ms INTEGER,
    edge_action TEXT,        -- "blocked", "allowed"
    log_source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INDEX: (timestamp DESC, crawler, host), (host, path, crawler), (http_status)
```
Module 7 output. AI crawler activity from request logs.

**visibility_metrics**
```sql
CREATE TABLE visibility_metrics (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    dimension TEXT NOT NULL, -- "overall", "by_topic", "by_persona", "by_engine"
    dimension_value TEXT,
    striim_mention_rate REAL,
    striim_recommendation_rate REAL,
    striim_top3_rate REAL,
    striim_avg_position REAL,
    striim_citation_rate REAL,
    competitor_mention_rates TEXT,  -- JSON: {Fivetran: 0.58, ...}
    num_responses INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
INDEX: (run_id, dimension), (dimension_value)
```
Module 4 output. Aggregated metrics across dimensions.

**gaps**
```sql
CREATE TABLE gaps (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    gap_type TEXT NOT NULL,  -- "visibility", "citation", "content", "technical", "authority"
    striim_visibility REAL,
    top_competitor_visibility REAL,
    top_competitor_name TEXT,
    affected_prompts TEXT,   -- JSON: ["oracle-cdc-001", ...]
    evidence_ids TEXT,       -- JSON: ["run-144", "citation-38", ...]
    priority TEXT,           -- "high", "medium", "low"
    confidence TEXT,         -- "high", "medium", "low"
    run_id TEXT NOT NULL,
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
INDEX: (topic, gap_type), (priority), (run_id, created_timestamp)
```
Module 8 output. Detected gaps with supporting evidence.

**recommendations**
```sql
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    gap_id TEXT NOT NULL,
    problem TEXT NOT NULL,
    evidence_summary TEXT,
    recommended_action TEXT NOT NULL,
    affected_pages TEXT,     -- JSON: ["https://...", ...]
    suggested_owner TEXT,
    priority INTEGER,        -- 1-10
    estimated_effort INTEGER, -- 1-3 (story points)
    measurement_plan TEXT,
    confidence TEXT,         -- "high", "medium", "low"
    status TEXT NOT NULL DEFAULT "draft", -- "draft", "pending_approval", "approved", "rejected", "implemented"
    created_by TEXT,
    approved_by TEXT,
    approval_timestamp DATETIME,
    review_notes TEXT,       -- JSON: {comment, reason}
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gap_id) REFERENCES gaps(id)
);
INDEX: (status), (gap_id), (priority DESC, status)
```
Module 9 output. Recommendations with approval workflow.

**data_retention_policy**
```sql
CREATE TABLE data_retention_policy (
    table_name TEXT PRIMARY KEY,
    retention_days INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO data_retention_policy VALUES
    ('raw_responses', 365),
    ('response_analysis', 365),
    ('citations', 365),
    ('website_checks', 365),
    ('crawler_logs', 90),
    ('visibility_metrics', NULL),  -- Keep all
    ('gaps', NULL),
    ('recommendations', NULL);
```
Tracks data cleanup schedules.

### 1.2 Schema Initialization

File: `aeo_eval/storage/sqlite_schema.sql`

```bash
# Initialize on first run
sqlite3 data/eval_runs.db < aeo_eval/storage/sqlite_schema.sql

# Enable foreign keys (per connection)
PRAGMA foreign_keys = ON;
```

### 1.3 Migration to PostgreSQL

**Trigger:** After 50+ runs or if `sqlite_query_time > 1 second` for frequently-accessed queries.

**Process:**
1. Dump SQLite schema and data
2. Adapt schema for PostgreSQL (JSON → JSONB, INTEGER booleans → BOOLEAN)
3. Create migration script
4. Run in parallel environment, validate
5. Switch connection string in config

Not required for MVP (< 12 months data, < 100 runs).

---

## 2. Async Job Architecture

### 2.1 Job Queue System

**Technology:** Celery + Redis

**Broker:** Redis (queue buffer)  
**Result Backend:** Redis (task results)  
**Workers:** 4-6 workers, split into two queues

```yaml
celery:
  broker_url: redis://localhost:6379/0
  result_backend: redis://localhost:6379/1
  
  queues:
    analysis:  # CPU/LLM-bound: Modules 3, 4, 5, 8, 9
      exchange: tasks
      routing_key: task.analysis
      priority: 10
    
    website:   # I/O-bound: Modules 6, 7
      exchange: tasks
      routing_key: task.website
      priority: 5
  
  task_routing:
    "tasks.extract_analysis": {queue: analysis}
    "tasks.aggregate_metrics": {queue: analysis}
    "tasks.analyze_citations": {queue: analysis}
    "tasks.check_website_access": {queue: website}
    "tasks.analyze_crawler_logs": {queue: website}
    "tasks.detect_gaps": {queue: analysis}
    "tasks.generate_recommendations": {queue: analysis}
    "tasks.update_dashboard": {queue: analysis}
  
  worker_config:
    prefetch_multiplier: 4
    max_tasks_per_child: 1000
    task_acks_late: true  # Only ack after completion
    task_track_started: true
    task_time_limit: 600  # 10 min hard limit
    task_soft_time_limit: 540  # 9 min soft limit
```

### 2.2 Task Definitions & Orchestration

File: `aeo_eval/tasks.py`

Each task:
- Has clear input/output contracts
- Retries on transient failures (max 3 retries with exponential backoff)
- Logs progress and errors
- Updates database on completion

```python
# Task 3: Response Analysis (bottleneck)
@app.task(name='tasks.extract_analysis', bind=True, max_retries=3)
def extract_analysis(self, run_batch_id: str):
    """Extract brands, positions, claims, citations."""
    try:
        analyzer = ResponseAnalyzer(config)
        results = analyzer.analyze_batch(run_batch_id)
        return {'run_batch_id': run_batch_id, 'analyzed_count': len(results)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

# Task 4: Visibility Metrics
@app.task(name='tasks.aggregate_metrics')
def aggregate_metrics(analysis_result: dict, run_batch_id: str):
    """Aggregate visibility metrics."""
    aggregator = MetricsAggregator(config)
    metrics = aggregator.calculate(run_batch_id)
    return {'run_batch_id': run_batch_id, 'metrics_count': len(metrics)}

# Task 5: Citation Intelligence
@app.task(name='tasks.analyze_citations', bind=True, max_retries=2)
def analyze_citations(self, analysis_result: dict, run_batch_id: str):
    """Normalize URLs, classify sources."""
    try:
        analyzer = CitationAnalyzer(config)
        citations = analyzer.process_batch(run_batch_id)
        return {'run_batch_id': run_batch_id, 'citations_count': len(citations)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)

# Task 6: Website Checks
@app.task(name='tasks.check_website_access', bind=True, max_retries=2)
def check_website_access(self, run_batch_id: str):
    """Check robots.txt, HTTP status, sitemap, canonical, noindex."""
    try:
        checker = WebsiteChecker(config)
        checks = checker.check_all_pages()
        return {'run_batch_id': run_batch_id, 'checks_count': len(checks)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)

# Task 7: Request Log Analysis (depends on Task 6)
@app.task(name='tasks.analyze_crawler_logs')
def analyze_crawler_logs(website_check_result: dict, run_batch_id: str):
    """Ingest logs, match to crawlers, detect failures."""
    analyzer = LogAnalyzer(config)
    logs = analyzer.process_new_logs()
    return {'run_batch_id': run_batch_id, 'logs_analyzed': len(logs)}

# Task 8: Gap Detection
@app.task(name='tasks.detect_gaps')
def detect_gaps(metrics_result, citations_result, website_result, logs_result, run_batch_id):
    """Identify visibility, citation, content, technical, authority gaps."""
    detector = GapDetector(config)
    gaps = detector.detect(run_batch_id)
    return {'run_batch_id': run_batch_id, 'gaps_found': len(gaps)}

# Task 9: Recommendations
@app.task(name='tasks.generate_recommendations')
def generate_recommendations(gaps_result: dict, run_batch_id: str):
    """Generate evidence-backed recommendations."""
    engine = RecommendationEngine(config)
    recs = engine.generate(run_batch_id)
    return {'run_batch_id': run_batch_id, 'recommendations': len(recs)}

# Task 10: Dashboard Aggregation
@app.task(name='tasks.update_dashboard')
def update_dashboard(recommendations_result: dict, run_batch_id: str):
    """Update dashboard views."""
    agg = DashboardAggregator(config)
    agg.update(run_batch_id)
    return {'run_batch_id': run_batch_id, 'dashboard_updated': True}
```

### 2.3 Pipeline Orchestration

```python
from celery import chain, group, chord

def orchestrate_evaluation_pipeline(run_batch_id: str):
    """Create complete pipeline signature."""
    return chain(
        # Task 3: Sequential bottleneck (LLM extraction)
        extract_analysis.s(run_batch_id),
        
        # Tasks 4, 5, 6: Parallel (using group + chord)
        chord(
            group(
                aggregate_metrics.s(run_batch_id),
                analyze_citations.s(run_batch_id),
                check_website_access.s(run_batch_id),
            ),
            # Task 7: Depends on Task 6 result
            analyze_crawler_logs.s(run_batch_id),
        ),
        
        # Task 8: Depends on all above (implicit)
        detect_gaps.s(run_batch_id),
        
        # Task 9: Depends on gaps
        generate_recommendations.s(run_batch_id),
        
        # Task 10: Final aggregation
        update_dashboard.s(run_batch_id),
    )

def trigger_analysis_pipeline(run_batch_id: str):
    """Queue pipeline after Module 2 completes."""
    pipeline = orchestrate_evaluation_pipeline(run_batch_id)
    result = pipeline.apply_async(
        task_id=f"pipeline-{run_batch_id}",
        priority=5,
        expires=86400,  # Expire after 24h if unprocessed
    )
    
    # Track in DB
    store.save_pipeline_task({
        'run_batch_id': run_batch_id,
        'task_id': result.id,
        'status': 'queued',
        'queued_at': datetime.now()
    })
    
    return result
```

### 2.4 Monitoring & Error Handling

**Celery Flower** for monitoring:
```bash
celery -A aeo_eval.tasks flower --port=5555
```

**Status Endpoint** (FastAPI):
```python
@app.get("/api/pipeline/{run_batch_id}/status")
def get_pipeline_status(run_batch_id: str):
    """Check pipeline progress."""
    from celery.result import AsyncResult
    task = AsyncResult(f"pipeline-{run_batch_id}", app=celery_app)
    
    return {
        'run_batch_id': run_batch_id,
        'status': task.status,  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
        'progress': task.info.get('status') if task.info else None,
        'current_task': task.info.get('current_task') if task.info else None,
    }
```

**Dead Letter Queue:** Failed tasks after max retries go to DLQ for manual review.

---

## 3. Module Interfaces & Data Contracts

### 3.1 Module 3: Response Analysis

**Input:**
- `run_batch_id`: Batch identifier
- Query: All `raw_responses` where `run_id = run_batch_id`

**Output:**
- Insert rows into `response_analysis` table
- One row per response

**Key Types:**

```python
@dataclass
class BrandMention:
    name: str
    position: Optional[int]  # Position in list, or None if unordered
    is_recommended: bool = False

@dataclass
class Claim:
    text: str
    sentiment: str  # "positive", "negative", "neutral"
    confidence: Decimal  # 0.0-1.0
    supporting_citation: Optional[str] = None

@dataclass
class ResponseAnalysisOutput:
    raw_response_id: str
    striim_mentioned: bool
    striim_recommended: bool
    striim_position: Optional[int]
    brands_found: List[BrandMention]
    claims: List[Claim]
    citations: List[str]  # URLs
    extraction_confidence: Decimal
    flagged_for_review: bool
```

**Algorithm:**
1. **Brand Detection** (rules-based, deterministic):
   - Regex/string matching for brand names (case-insensitive)
   - Position extraction from ordered lists (numbered, bulleted)
   - Mark unordered lists as position=None
   
2. **Citation Extraction** (rules-based):
   - Regex for URLs: `https?://[^\s]+`
   - Basic validation (no incomplete URLs)
   
3. **LLM Extraction** (Module 3 → LLM):
   - Prompt LLM to extract claims about Striim
   - Classify sentiment (positive/negative/neutral)
   - Match claims to citations when possible
   - Return confidence score (0.0-1.0)
   
4. **Flagging**:
   - If confidence < 0.65, flag for human review
   - Flagged rows available in dashboard for QA

**Validation:**
- `striim_position` is None or >= 1
- `brands_found` includes all mentioned brands
- `extraction_confidence` is 0.0-1.0
- `citations` are valid URLs
- All text fields non-empty if present

**Error Handling:**
- Missing `response_text`: Skip and log error
- LLM API errors: Retry with exponential backoff (max 3 attempts)
- Malformed URLs: Filter out, continue

---

### 3.2 Module 4: Visibility Metrics

**Input:**
- `run_batch_id`
- All `response_analysis` rows for this batch
- Prompt metadata (topic, persona, engine)

**Output:**
- Insert rows into `visibility_metrics` table
- Dimensions: overall, by_topic, by_persona, by_engine

**Key Types:**

```python
@dataclass
class VisibilityMetrics:
    dimension: str
    dimension_value: Optional[str]
    striim_mention_rate: Decimal  # 0.0-1.0
    striim_recommendation_rate: Decimal
    striim_top3_rate: Decimal
    striim_avg_position: Decimal
    striim_citation_rate: Decimal
    competitor_mention_rates: Dict[str, Decimal]
    num_responses: int
```

**Calculations:**
- **Mention rate:** (# responses mentioning Striim) / (total responses)
- **Recommendation rate:** (# responses recommending Striim) / (total responses)
- **Top-3 rate:** (# responses with Striim in positions 1-3) / (total responses with position)
- **Avg position:** Mean of `striim_position` (excluding None)
- **Citation rate:** (# responses with citations) / (total responses)
- **Competitor rates:** Same calculation per competitor

**Validation:**
- All rates must be 0.0-1.0
- `num_responses` matches dataset size
- `avg_position` is > 0 or exactly 0

---

### 3.3 Module 5: Citation Intelligence

**Input:**
- `run_batch_id`
- All citations from `response_analysis.citations` (JSON arrays)

**Output:**
- Insert rows into `citations` table (deduplicated)
- Insert rows into `citation_occurrences` (map claims to URLs)

**Key Types:**

```python
@dataclass
class NormalizedCitation:
    id: str  # UUID
    original_url: str
    normalized_url: str  # Canonical form (unique)
    domain: str
    page_title: Optional[str]
    source_category: str
    first_observed: datetime
    last_observed: datetime
    occurrence_count: int
```

**Source Categories:**
- `striim_owned`: striim.com
- `competitor`: Known competitor domains
- `partner_docs`: Partner integrations/documentation
- `review_platform`: G2, Capterra, Gartner, Forrester
- `technical_publication`: Medium, Dev.to, GitHub
- `customer_content`: Customer blogs, case studies
- `community_content`: Reddit, StackOverflow, GitHub Discussions
- `analyst_research`: Analyst reports
- `other_third_party`: Everything else

**Algorithm:**
1. **URL Normalization:**
   - Remove query params and fragments
   - Canonicalize protocol and domain
   - Trim trailing slashes
   - Store original URL separately
   
2. **Deduplication:**
   - Unique constraint on `normalized_url`
   - Update `occurrence_count` on duplicate
   - Track `last_observed` timestamp
   
3. **Content Fetch:**
   - HTTP GET with timeout (10s)
   - Extract page title from `<title>` or meta
   - Cache content for analysis
   
4. **Source Classification:**
   - Rules first (fastest)
   - LLM fallback for ambiguous sources
   - Store category with confidence

**Validation:**
- `normalized_url` is unique across all citations
- `domain` extracted correctly
- `source_category` is one of the 9 categories
- `occurrence_count` >= 1

---

### 3.4 Module 6: Website Accessibility Checks

**Input:**
- Config: `important_striim_pages` (list of URLs)
- Config: `crawlers` (list of user agents)

**Output:**
- Insert rows into `website_checks` table
- One row per (page, crawler) pair

**Key Types:**

```python
@dataclass
class WebsiteCheck:
    id: str
    striim_url: str
    crawler: str
    robots_allowed: Optional[bool]
    in_sitemap: Optional[bool]
    http_status: Optional[int]
    response_time_ms: Optional[int]
    noindex: Optional[bool]
    canonical_url: Optional[str]
    result: str  # Status
    check_timestamp: datetime
```

**Result Values:**
- `publicly_accessible`: HTTP 200, robots.txt allows, no noindex
- `blocked_by_robots`: robots.txt denies access
- `noindex`: Page has noindex directive
- `http_error_4xx`: HTTP 400-499
- `http_error_5xx`: HTTP 500+
- `unknown`: Unable to determine

**Checks Performed:**
1. **robots.txt:** Use `urllib.robotparser` to test each crawler
2. **HTTP Status:** HEAD request with crawler User-Agent, follow redirects
3. **noindex:** Check `x-robots-tag` header and meta robots tag
4. **Sitemap:** Parse `/sitemap.xml`, check if URL is present
5. **Canonical:** Extract from `Link: <...>; rel="canonical"` header

**Parallelization:**
- 20-30 Striim pages × 5 crawlers = 100-150 checks
- HTTP requests parallelized with 10 concurrent threads
- Est. time: 60-120 seconds

**Validation:**
- `result` is one of the defined values
- `http_status` is None or valid (100-599)
- `response_time_ms` > 0 when present

---

### 3.5 Module 7: Request Log Analysis

**Input:**
- New log entries from request log files (sanitized)
- Config: Known AI crawler User-Agents

**Output:**
- Insert rows into `crawler_logs` table
- Detect failure patterns

**Key Types:**

```python
@dataclass
class CrawlerLogEvent:
    timestamp: datetime
    host: str
    path: str
    crawler: str  # Identified from User-Agent
    http_status: int
    response_time_ms: int
    edge_action: str  # "blocked", "allowed"
```

**Crawler Identification:**
- Match User-Agent against known patterns
- Top 5: OAI-SearchBot, PerplexityBot, ClaudeBot, Googlebot, Bingbot

**Failure Detection:**
- HTTP 403 (blocked by security layer)
- HTTP 404 (page missing or deleted)
- HTTP 429 (rate limited)
- HTTP 5xx (server error)
- Repeated failures (same page, same crawler)

**Deduplication:**
- Skip duplicate log entries (same timestamp, host, path, crawler)
- Track `log_source` to identify which file ingested entry

**Validation:**
- `http_status` is valid (100-599)
- `response_time_ms` >= 0
- `crawler` is from known list

---

### 3.6 Module 8: Gap Detection

**Input:**
- `run_batch_id`
- `visibility_metrics` for this batch
- `citations` and `citation_occurrences`
- `website_checks`
- `crawler_logs`

**Output:**
- Insert rows into `gaps` table

**Gap Types:**

1. **Visibility Gap:**
   - Striim mention rate < 15% on High-priority questions
   - OR Competitor mention rate > 2× Striim
   - Evidence: Metric IDs, prompt IDs

2. **Citation Gap:**
   - Competitor pages cited, Striim pages not
   - Frequently cited pages omit Striim references
   - Evidence: Citation IDs, page URLs

3. **Content Gap:**
   - Cited pages more complete than Striim pages
   - Topics covered by competitors missing from Striim
   - Evidence: Content comparison results

4. **Technical Gap:**
   - Page blocked by robots.txt but cited
   - Page returns HTTP error but mentioned
   - Page missing from sitemap
   - Page marked noindex
   - Crawler detected failure but public check passes
   - Evidence: Website check IDs, log entries

5. **Third-Party Authority Gap:**
   - Review platforms mention competitors but not Striim
   - Analyst reports cite competitors
   - Evidence: Citation IDs

**Deduplication:**
- Exact match on (topic, gap_type, affected_prompts set)
- Merge duplicate gaps, combine evidence IDs

**Priority Assignment:**
- **High:** Affects > 3 High-priority prompts OR visibility gap > 30%
- **Medium:** Affects 1-3 prompts OR visibility gap 15-30%
- **Low:** Affects < 1 prompt OR visibility gap < 15%

**Confidence:**
- **High:** 3+ pieces of evidence OR gap > 30%
- **Medium:** 2 pieces of evidence OR gap 10-30%
- **Low:** 1 piece of evidence OR gap < 10%

**Validation:**
- `gap_type` is one of the 5 types
- `priority` is "high", "medium", or "low"
- `confidence` is "high", "medium", or "low"
- `affected_prompts` is non-empty

---

### 3.7 Module 9: Recommendations

**Input:**
- `run_batch_id`
- All `gaps` for this batch
- Supporting evidence (metrics, citations, checks, logs)

**Output:**
- Insert rows into `recommendations` table
- Each recommendation ready for approval workflow

**Key Types:**

```python
@dataclass
class Recommendation:
    id: str
    gap_id: str
    problem: str  # 1-2 sentence summary
    evidence_summary: str  # Bullet points of evidence
    recommended_action: str  # Specific action to take
    affected_pages: List[str]  # URLs to create/update
    suggested_owner: str  # Team/person
    priority: int  # 1-10
    estimated_effort: int  # 1-3 (story points)
    measurement_plan: str  # How to measure success
    confidence: str  # "high", "medium", "low"
    status: str  # "draft", "pending_approval", "approved", "rejected", "implemented"
```

**Approval Workflow:**
- Status progression: draft → pending_approval → approved → implemented
- `approved_by`: Name of approver
- `approval_timestamp`: When approved
- `review_notes`: Approval/rejection reason (JSON)

**Auto-Approval:** High-confidence + High-priority recommendations auto-approve.

**Generation Rules:**
- **Visibility Gap →** Create content (blog, guide, product page)
- **Citation Gap →** Audit and update cited pages for Striim mentions
- **Content Gap →** Create comprehensive guide covering cited topics
- **Technical Gap →** Fix robots.txt, add to sitemap, remove noindex
- **Authority Gap →** Pitch Striim to analyst, reach out to reviewers

**Validation:**
- `priority` is 1-10
- `estimated_effort` is 1-3
- `status` is one of the workflow states
- All text fields non-empty

---

### 3.8 Module 10: Dashboard Aggregation

**Input:**
- All previous module outputs for `run_batch_id`
- Historical data (previous runs for comparison)

**Output:**
- Cached views (pre-aggregated data for fast dashboard rendering)
- No new database tables (uses existing ones)

**Views Produced:**

1. **Visibility View:**
   - Current run: Striim & competitor mention rates, recommendations rates
   - Historical: Trend line (last 6 runs)
   - By topic, persona, engine

2. **Citation View:**
   - Most-cited domains (top 20)
   - Most-cited pages (top 20)
   - Striim pages receiving citations
   - Competitor pages receiving citations
   - Sources mentioning competitors but not Striim

3. **Website Access View:**
   - Table: (Page, Crawler, Robots, HTTP, Actual Crawl, Result)
   - Failures highlighted
   - Trends over time

4. **Action Queue:**
   - All recommendations sorted by (status, priority)
   - Draft → pending → approved → implemented
   - Estimated effort and owner

---

## 4. Testing Strategy

### 4.1 Test Pyramid

**Target:** 70% unit, 20% integration, 10% E2E

**Coverage:** 80%+ line coverage for modules 3-10

### 4.2 Unit Tests

Each module tested independently with mocked dependencies.

**File:** `tests/test_response_analyzer.py` (and similar for each module)

**Test Patterns:**
- Brand detection: All brands found, positions correct
- Citation extraction: All URLs found and valid
- Metrics calculation: Rates 0.0-1.0, counts correct
- URL normalization: Consistency across variants
- Source classification: All categories recognized
- Website checks: Status codes mapped correctly
- Log parsing: Crawler identification accurate
- Gap detection: Thresholds applied correctly
- Recommendations: Logic sound and complete

**Accuracy Benchmarks:**
- Brand detection: ≥ 95% precision & recall
- Position extraction: ≥ 90% accuracy
- Citation extraction: ≥ 98% (mostly rule-based)
- Source classification: ≥ 85% for ambiguous sources
- Website checks: 100% (deterministic)

### 4.3 Integration Tests

Test module interactions through the database.

**File:** `tests/test_integration_pipeline.py`

**Patterns:**
- Module 2 → 3: Raw responses correctly analyzed
- Module 3 → 4: Analyses correctly aggregated to metrics
- Module 3 → 5: Citations correctly normalized
- Full pipeline: All outputs persist and validate

### 4.4 End-to-End Tests

Complete pipeline with mocked API calls.

**File:** `tests/test_e2e.py`

**Patterns:**
- Load 5-10 prompts
- Run Module 2 with mock engine
- Trigger full pipeline
- Verify all tables populated
- Verify no data loss
- Verify metrics reasonable

**Excluded:** Real API calls (cost, latency)

### 4.5 Performance Tests

Verify scalability targets.

**File:** `tests/test_performance.py`

**Benchmarks:**

| Module | Target | Measurement |
|--------|--------|-------------|
| 3 | 60 responses in < 120s | LLM extraction throughput |
| 4 | Aggregate 60 in < 5s | In-memory calculation |
| 5 | Normalize 100 URLs in < 60s | URL processing + fetch |
| 6 | Check 100 pages in < 120s | Parallel HTTP requests |
| 7 | Parse 10k logs in < 30s | Log ingestion rate |
| 8 | Detect gaps in < 20s | Comparison logic |
| 9 | Generate recs in < 30s | LLM drafting |
| 10 | Aggregate views in < 10s | Dashboard prep |

### 4.6 Data Validation Tests

Ensure data contracts at module boundaries.

**File:** `tests/test_data_validation.py`

**Patterns:**
- ResponseAnalysisOutput validation (types, ranges)
- VisibilityMetrics validation (rates 0.0-1.0)
- NormalizedCitation validation (unique URLs)
- WebsiteCheck validation (result codes)
- Gaps validation (gap types, thresholds)
- Recommendations validation (status workflow)

---

## 5. Scaling Considerations

### 5.1 Timeline

**For 240 evaluations/run (60 questions × 4 engines):**

| Stage | Duration | Notes |
|-------|----------|-------|
| Module 2 (Eval) | 10-20 min | 4 engines in parallel |
| Module 3 (Analysis) | 2-3 min | Batch LLM extraction, ~60 calls |
| Module 4 (Metrics) | 10 sec | In-memory aggregation |
| Module 5 (Citations) | 1-2 min | 10 concurrent HTTP fetches |
| Module 6 (Website) | 2-3 min | 20 concurrent HTTP checks |
| Module 7 (Logs) | 30 sec | Streaming parse |
| Module 8 (Gaps) | 20 sec | Dedup and comparison |
| Module 9 (Recs) | 30 sec | LLM drafting |
| Module 10 (Dashboard) | 10 sec | View aggregation |
| **Total Pipeline** | **25-35 min** | Sequential bottleneck: Module 3 |

### 5.2 Worker Scaling

**Setup:**
- 2-3 workers on `analysis` queue (CPU/LLM bound)
- 2-3 workers on `website` queue (I/O bound)
- Each worker = 4 concurrent tasks

**For 1 run/month:**
- Small setup sufficient (single machine, 4 workers)

**For weekly runs:**
- Scale to 6 workers (3 analysis, 3 website)
- Consider dedicated machine for workers

**For daily runs:**
- Migrate to Kubernetes or cloud job system
- Auto-scale based on queue depth

### 5.3 Database Scalability

**SQLite:**
- Suitable for < 100 runs (< 36 months of data)
- Single-file simplicity, no server overhead
- Concurrent reads OK, concurrent writes contended

**Migration Trigger:** PostgreSQL recommended after:
- 50+ runs AND
- Visibility queries taking > 1 second, OR
- Concurrent analysis runs (>1 simultaneously)

**PostgreSQL Migration (no code changes):**
1. Update connection string in config
2. Run migration script
3. Warm caches

### 5.4 Cost Estimate

**Per Run (60 questions × 4 engines):**
- Module 3 LLM extraction: ~60 requests × ~1500 tokens = ~$0.05 (Claude Opus 5 input/output)
- Module 5 Source classification: ~20 requests × ~200 tokens = ~$0.01
- Module 9 Recommendation drafting: ~10 requests × ~500 tokens = ~$0.01
- **Subtotal:** ~$0.07/run

**Monthly (1 run):** ~$0.07  
**Yearly:** ~$0.84

*Note: Module 2 (evaluator) cost separate; see Module 2 spec.*

### 5.5 Bottleneck Analysis

**Sequential bottleneck:** Module 3 (Response Analysis)
- 60 responses × ~10-20 seconds per LLM call = 100-200 seconds
- Optimization: Batch LLM calls in groups of 5-10 using Claude's batch API (if available)
- Estimated speedup: 2-3×

**Parallelization gains:**
- Modules 4-6 run in parallel saves ~180 seconds
- Modules 7-9 run sequentially adds ~60 seconds
- Total pipeline: 120s (Module 3) + 30s (Module 4-6 slowest) + 60s (7-9) = **210 seconds ≈ 3.5 minutes**

**Critical path:** Module 3 → (4||5||6) → 7 → 8 → 9 → 10

---

## 6. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
- [ ] Create SQLite schema and initialization
- [ ] Implement Module 3 (ResponseAnalyzer, full LLM extraction)
- [ ] Implement Module 4 (MetricsAggregator)
- [ ] Unit tests for 3-4
- [ ] Integration tests for 3-4 pipeline

### Phase 2: Data Collection (Weeks 3-4)
- [ ] Implement Module 5 (CitationAnalyzer)
- [ ] Implement Module 6 (WebsiteChecker)
- [ ] Unit tests for 5-6
- [ ] Integration tests for 5-6

### Phase 3: Analysis & Insights (Weeks 5-6)
- [ ] Implement Module 7 (LogAnalyzer)
- [ ] Implement Module 8 (GapDetector)
- [ ] Unit tests for 7-8
- [ ] Integration tests for 7-8

### Phase 4: Actions & Dashboard (Weeks 7-8)
- [ ] Implement Module 9 (RecommendationEngine)
- [ ] Implement Module 10 (DashboardAggregator)
- [ ] Implement approval workflow
- [ ] FastAPI endpoints for dashboard
- [ ] E2E tests
- [ ] Performance benchmarks

### Phase 5: Polish & Deploy (Weeks 9-10)
- [ ] Error handling and logging
- [ ] Monitoring and alerting
- [ ] Documentation
- [ ] Celery + Redis setup
- [ ] Docker containerization
- [ ] Staging deployment

---

## 7. Known Constraints & Assumptions

**Constraints:**
- SQLite for first 12 months; PostgreSQL migration available if needed
- Max 240 evaluations per run (60 questions × 4 engines)
- Request logs mandatory (no skipping Module 7)
- Approval workflow required (no auto-publishing all recommendations)

**Assumptions:**
- Claude API available and stable (primary LLM for Modules 3, 5, 9)
- Request logs in sanitized JSON format (IP hashed, query params removed)
- Striim's robots.txt and sitemap maintained
- Competitor list stable (Fivetran, Oracle GoldenGate, etc.)

**Future Work:**
- Claim verification using approved Striim documentation
- Content brief generation
- Natural-language Q&A over dashboard data
- AI referral traffic analysis
- Batch API for Module 3 (when available)

---

## 8. Trade-offs & Rationale

| Decision | Alternative | Rationale |
|----------|-----------|-----------|
| Celery + Redis | APScheduler only | Celery enables horizontal scaling, better error handling |
| SQLite → PostgreSQL | Always PostgreSQL | SQLite simpler for MVP, migration path clear |
| Rules first, LLM fallback | LLM for all extraction | Rules deterministic, fast, cheaper; LLM for ambiguous cases |
| JSON for complex data | Separate tables | JSON more flexible, easier schema evolution; SQLite supports JSON1 |
| 1-year retention | All data forever | Balances historical trending with storage/query costs |
| Module decoupling via DB | Tightly coupled code | Enables rerun single module, testability, parallelization |

---

## 9. Success Criteria

**Functional:**
- [ ] All 8 modules (3-10) implement correctly
- [ ] Data contracts validated at module boundaries
- [ ] Approval workflow for recommendations working
- [ ] Dashboard displays all required views

**Performance:**
- [ ] Pipeline completes in < 35 minutes for 240 evaluations
- [ ] Database queries < 1 second (SQLite)
- [ ] Workers scale to 6+ without bottlenecks

**Accuracy:**
- [ ] Brand detection: ≥ 95% precision
- [ ] Position extraction: ≥ 90% accuracy
- [ ] Metrics reproducible across runs

**Reliability:**
- [ ] 99% task success rate (after retries)
- [ ] 1-year data retention without corruption
- [ ] Graceful failure handling (one failed module doesn't block pipeline)

---

## 10. Next Steps

1. **User Review:** Review this spec and request changes
2. **Design Approval:** Confirm all sections align with requirements
3. **Implementation Planning:** Invoke `writing-plans` skill to create detailed implementation plan
4. **Execution:** Phase 1 begins with Module 3 implementation

---

**Document Status:** Ready for Review  
**Last Updated:** 2026-08-14  
**Next Review:** After user approval, before implementation begins
