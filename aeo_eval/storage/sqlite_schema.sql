-- AEO Visibility Platform SQLite Schema
-- Modules 3-10 Database Schema
-- SQLite 3.38+ with JSON1 extension

PRAGMA foreign_keys = ON;

-- Core evaluation run metadata
CREATE TABLE IF NOT EXISTS evaluation_runs (
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
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_timestamp ON evaluation_runs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_engine ON evaluation_runs(engine);

-- Immutable raw responses from Module 2
CREATE TABLE IF NOT EXISTS raw_responses (
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
CREATE INDEX IF NOT EXISTS idx_raw_responses_run_prompt_engine ON raw_responses(run_id, prompt_id, engine);
CREATE INDEX IF NOT EXISTS idx_raw_responses_created_at ON raw_responses(created_at DESC);

-- Module 3: Response Analysis output
CREATE TABLE IF NOT EXISTS response_analysis (
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
CREATE INDEX IF NOT EXISTS idx_response_analysis_raw_response_id ON response_analysis(raw_response_id);
CREATE INDEX IF NOT EXISTS idx_response_analysis_flagged ON response_analysis(flagged_for_review);

-- Module 5: Deduplicated citations
CREATE TABLE IF NOT EXISTS citations (
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
CREATE INDEX IF NOT EXISTS idx_citations_normalized_url ON citations(normalized_url);
CREATE INDEX IF NOT EXISTS idx_citations_domain ON citations(domain);
CREATE INDEX IF NOT EXISTS idx_citations_source_category ON citations(source_category);

-- Module 5: Citation-to-claim mappings
CREATE TABLE IF NOT EXISTS citation_occurrences (
    id TEXT PRIMARY KEY,
    citation_id TEXT NOT NULL,
    response_analysis_id TEXT NOT NULL,
    claim_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (citation_id) REFERENCES citations(id),
    FOREIGN KEY (response_analysis_id) REFERENCES response_analysis(id)
);
CREATE INDEX IF NOT EXISTS idx_citation_occurrences_citation_id ON citation_occurrences(citation_id);
CREATE INDEX IF NOT EXISTS idx_citation_occurrences_analysis_id ON citation_occurrences(response_analysis_id);

-- Module 6: Website accessibility checks
CREATE TABLE IF NOT EXISTS website_checks (
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
CREATE INDEX IF NOT EXISTS idx_website_checks_striim_url_crawler ON website_checks(striim_url, crawler);
CREATE INDEX IF NOT EXISTS idx_website_checks_check_timestamp ON website_checks(check_timestamp DESC);

-- Module 7: AI crawler activity from request logs
CREATE TABLE IF NOT EXISTS crawler_logs (
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
CREATE INDEX IF NOT EXISTS idx_crawler_logs_timestamp_crawler_host ON crawler_logs(timestamp DESC, crawler, host);
CREATE INDEX IF NOT EXISTS idx_crawler_logs_host_path_crawler ON crawler_logs(host, path, crawler);
CREATE INDEX IF NOT EXISTS idx_crawler_logs_http_status ON crawler_logs(http_status);

-- Module 4: Visibility metrics
CREATE TABLE IF NOT EXISTS visibility_metrics (
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
CREATE INDEX IF NOT EXISTS idx_visibility_metrics_run_dimension ON visibility_metrics(run_id, dimension);
CREATE INDEX IF NOT EXISTS idx_visibility_metrics_dimension_value ON visibility_metrics(dimension_value);

-- Module 8: Detected gaps
CREATE TABLE IF NOT EXISTS gaps (
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
CREATE INDEX IF NOT EXISTS idx_gaps_topic_gap_type ON gaps(topic, gap_type);
CREATE INDEX IF NOT EXISTS idx_gaps_priority ON gaps(priority);
CREATE INDEX IF NOT EXISTS idx_gaps_run_id_created_timestamp ON gaps(run_id, created_timestamp);

-- Module 9: Recommendations with approval workflow
CREATE TABLE IF NOT EXISTS recommendations (
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
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations(status);
CREATE INDEX IF NOT EXISTS idx_recommendations_gap_id ON recommendations(gap_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_priority_status ON recommendations(priority DESC, status);

-- Prompt catalog, persisted so run-scoped queries (e.g. Module 4's
-- by-topic metrics breakdown) can join raw_responses.prompt_id against
-- topic/persona/priority metadata without a separate prompt store.
CREATE TABLE IF NOT EXISTS prompts (
    id TEXT PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    topic TEXT,
    persona TEXT,
    intent TEXT,
    priority TEXT,
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prompts_topic ON prompts(topic);

-- Data retention policy tracking
CREATE TABLE IF NOT EXISTS data_retention_policy (
    table_name TEXT PRIMARY KEY,
    retention_days INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO data_retention_policy (table_name, retention_days) VALUES
    ('raw_responses', 365),
    ('response_analysis', 365),
    ('citations', 365),
    ('website_checks', 365),
    ('crawler_logs', 90),
    ('visibility_metrics', NULL),
    ('gaps', NULL),
    ('recommendations', NULL);
