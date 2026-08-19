# AEO Visibility and Citation Intelligence Platform

## Overview

The goal of this project is to build an internal platform that measures how Striim appears in AI-generated answers, identifies the sources influencing those answers, detects website-access problems, and recommends specific actions that may improve visibility.

The platform should answer:

1. How often does Striim appear for important buyer questions?
2. Which competitors appear more frequently?
3. Which webpages and domains are cited?
4. Can AI crawlers discover and access relevant Striim pages?
5. Why might Striim be missing or represented incorrectly?
6. What action should Striim take next?

The system should support repeatable measurement. It should not claim that any technical or content change will guarantee an AI mention or citation.

## Project Objectives

The system should:

- Run 40 to 60 buyer questions across two selected AI answer engines. (user questions, cron? find relatively open source AI answer engines).
- Store complete answers, citations, model information, cost, and latency.
- Extract Striim mentions, competitor mentions, positions, and claims.
- Calculate visibility and citation metrics.
- Analyze the webpages and domains cited by answer engines.
- Compare frequently cited content with relevant Striim content.
- Check whether important Striim pages are accessible to AI crawlers.
- Analyze sanitized crawler request logs when available.
- Identify content, technical, citation, third-party authority, and agent-experience gaps.
- Generate evidence-backed recommendations.
- Display findings in a simple dashboard.
- Track changes across repeated evaluation runs.

## Project Boundaries

### Required Scope

The first version should include:

| Area | Required scope |
|---|---|
| Buyer questions | 40 to 60 configured questions |
| Answer engines | Two approved integrations |
| Competitors | Configurable competitor list |
| Answer analysis | Brand, position, claim, sentiment, and citation extraction |
| Citation analysis | URL normalization, domain ranking, source classification |
| Website checks | `robots.txt`, sitemap, HTTP status, redirects, canonical, noindex, `llms.txt`, content extractability |
| Logs | One synthetic, sanitized, or production request-log format |
| Recommendations | Evidence-backed gap-to-action workflow |
| Interface | Simple internal dashboard |
| Evaluation | Small labeled test set and one case study |

### Stretch Goals

These should only be added after the required system works:

- Claim verification using approved Striim documentation.
- Detailed comparison of Striim and competitor page content.
- Natural-language questions over dashboard data.
- Generated content briefs.
- IP or DNS verification of crawler identity.
- AI referral-traffic analysis.
- Slack or email summaries.

## Inputs

### 1. Buyer Question Dataset

Examples:

```
What are the best Oracle CDC tools?

How do I replicate Oracle data to Snowflake?

Striim vs Fivetran for real-time replication

Which CDC tools support schema evolution?
```

Each question should include metadata:

```json
{
  "prompt_id": "oracle-cdc-001",
  "prompt": "What are the best Oracle CDC tools?",
  "topic": "Oracle CDC",
  "persona": "Data Architect",
  "intent": "Commercial",
  "priority": "High",
  "enabled": true
}
```

### 2. Competitor List

Examples may include:

```
Oracle GoldenGate
Fivetran
Qlik Replicate
Confluent
AWS DMS
Estuary
```

### 3. Important Striim Pages

Examples include:

- Product pages.
- Integration pages.
- Documentation.
- Architecture guides.
- Comparison pages.
- Customer stories.
- Technical blog posts.

### 4. AI Answer-Engine Data

For each question run, collect:

```json
{
  "prompt_id": "oracle-cdc-001",
  "engine": "selected-engine",
  "model": "selected-model",
  "response": "Complete answer text",
  "citations": [
    "https://example.com/oracle-cdc"
  ],
  "run_time": "2026-08-04T18:00:00Z",
  "latency_ms": 7200,
  "estimated_cost": 0.02,
  "status": "success"
}
```

### 5. Optional Request Logs

When available, sanitized records may contain:

```json
{
  "timestamp": "2026-08-04T18:42:12Z",
  "host": "www.striim.com",
  "path": "/product/oracle-cdc/",
  "method": "GET",
  "status_code": 403,
  "user_agent": "OAI-SearchBot/1.0",
  "response_time_ms": 24,
  "edge_action": "blocked"
}
```

## Outputs

The system should produce:

- Striim visibility metrics.
- Competitor visibility comparisons.
- Most-cited domains and pages.
- Sources that mention competitors but not Striim.
- Claims made about Striim.
- Bot-specific website-access results.
- Agent-context and extractability results.
- Actual crawler activity when logs are available.
- Content, technical, and third-party gaps.
- Ranked recommended actions.
- Historical comparisons.
- One final AEO case study.

## System Flow

```
Buyer questions and competitor list
                ↓
Run questions across two answer engines
                ↓
Store answers, citations, metadata, cost, and latency
                ↓
Extract brands, positions, claims, sentiment, and citations
                ↓
Calculate visibility metrics
        │
        ├────────────────────────────────┐
        │                                │
        ▼                                ▼
Analyze cited sources            Analyze Striim pages
and competitor content           and crawler accessibility
        │                                │
        └───────────────┬────────────────┘
                        ▼
        Identify gaps and likely causes
                        ↓
        Generate evidence-backed actions
                        ↓
          Display results in dashboard
                        ↓
           Repeat and compare results
```

The cited-source and website-access modules run in parallel. Website access is one possible cause of weak visibility, not a required step for every gap.

## Core Modules

### 1. Buyer Question Repository

Maintain 40 to 60 questions grouped by:

- Topic.
- Persona.
- Intent.
- Priority.

The system should support adding, editing, disabling, and selecting questions for an evaluation run.

#### Specifics & Considerations

- Topics: AI Data Infrastructure, CDC Tools & Platforms, Cloud Data Warehouse Integration, Comparisons & Alternatives, Data Governance & Compliance, Data Replication, Oracle CDC, Real-Time Data Integration
- Personas: Head of Data / CDO, VP of AI, VP of Engineering / CTO, Data Scientist, AI Product Manager, CISO
- Similar questions can be stored as variants. However, they will be run separately.
- In the future: To keep up w/ trends, some questions will be kept static and others will be swapped out for generated questions

### 2. Answer-Engine Evaluation Runner

Run enabled questions against two selected answer engines.

The runner should support:

- Manual and scheduled runs.
- One-question, one-topic, and full-dataset runs.
- Retry handling.
- Rate-limit handling.
- Partial failures.
- Cost limits.
- Historical storage.
- Model and engine version tracking.

A failure for one prompt should not cause the entire evaluation run to fail.

**Estimated annual costs**

*Claude + OpenAI + Grok + Perplexity — 4 engines, 240 API calls/month — $26–39/year*

| Model | Per-call cost | Per run (60q) | Annual (12 runs) |
|---|---|---|---|
| Claude Sonnet 5 | ~$0.012 | $0.75 | $9.00 |
| OpenAI GPT-4o | ~$0.0085 | $0.51 | $6.12 |
| Grok 4.3 | ~$0.0022 | $0.13 | $1.57 |
| Perplexity Sonar Pro | ~$0.012 | $0.75 | $9.00 |

**Total per run:** ~$2.14 | **Annual:** ~$26–39

#### Specifics & Considerations

- Answer Engines: Claude, Open AI, Grok, Perplexity. Gemini if budget/space allows.
- Evaluations are run monthly, but can be run manually if new sudden trends appear.
- Questions will be asked once per answer engine. If budget allows, asking each engine a set of questions 2-3 times will allow for higher accuracy.
- API spending can be configured in settings. (Can set a max spending limit, etc.)
- Future Reference: Provider-specific adapters:
  - Abstraction layer + engine-specific hooks. Base AnswerEngineRunner class; subclass for OpenAI and Claude. Hooks for structured output

### 3. Response Analysis

For every answer, identify:

- Whether Striim is mentioned.
- Whether Striim is recommended.
- Striim's position when applicable.
- Competitors mentioned.
- Competitor positions.
- Claims made about Striim.
- Sentiment toward Striim.
- Citations included in the answer.
- Which citation may support each claim.

Example:

```json
{
  "striim_mentioned": true,
  "striim_recommended": true,
  "striim_position": 3,
  "competitors": [
    {
      "name": "Fivetran",
      "position": 1
    }
  ],
  "striim_claims": [
    {
      "claim": "Striim supports real-time CDC",
      "sentiment": "positive",
      "citation_url": "https://example.com/article"
    }
  ]
}
```

The implementation should combine deterministic rules with structured LLM extraction.

The complete raw answer must always remain available for review.

#### LLM Responsibilities

The LLM may:

- Interpret unstructured product lists.
- Extract claims.
- Classify sentiment.
- Match citations to claims.
- Mark ambiguous results.

The LLM should return validated structured output and include confidence where useful.

#### Specifics & Considerations

- Brand detection using regex or string matching
- Positions, claims, and sentiment will be detected w/ an LLM
- Unordered product lists are labelled unordered
- Uncertain position lists are handled through confidence score
- Future testing:
  - Confidence threshold for human review will be determined via initial tests/runs

### 4. Visibility Metrics

Calculate:

- Mention rate.
- Recommendation rate.
- Top-three placement rate.
- Average position.
- Citation rate.
- Competitive share of voice.
- Visibility by topic.
- Visibility by persona.
- Visibility by engine.
- Visibility over time.

Example:

```
Topic: Oracle CDC

Striim mention rate:             24%
Oracle GoldenGate mention rate:  66%
Fivetran mention rate:           38%

Striim top-three rate:           11%
Striim citation rate:             7%
```

The dashboard should show the number of responses behind each metric.

#### Specifics & Considerations

- Most useful metrics will be displayed and 'more metrics' will be included in a section below
- Latest run will be shown by default, along w/ a trend line and confidence band (if more than one run). Previous runs can be selected.
- Sample sizes displayed w/ metrics. Highlighted if n < 10.
- Answer volatility communicated via min/max range + average mention rate. Sparkline on hover.

### 5. Citation Intelligence

For every citation, store:

- Original URL.
- Normalized URL.
- Domain.
- Page title.
- Source category.
- Related question and topic.
- Answer engine.
- First and last observed date.
- Citation frequency.
- Brands mentioned on the cited page.

Possible source categories:

- Striim-owned.
- Competitor-owned.
- Partner documentation.
- Review platform.
- Technical publication.
- Customer content.
- Community content.
- Analyst or research source.
- Other third party.

The module should identify:

- Most-cited domains.
- Most-cited pages.
- Striim pages receiving citations.
- Competitor pages receiving citations.
- Third-party sources mentioning competitors but not Striim.
- Sources appearing across multiple engines.

#### Content Comparison

For selected high-priority questions, compare:

- Frequently cited pages.
- Relevant Striim pages.
- Topics covered.
- Technical details included.
- Evidence, examples, and statistics.
- Missing information.

Example output:

```json
{
  "prompt": "How do I replicate Oracle to Snowflake?",
  "cited_page_topics": [
    "initial load",
    "schema evolution",
    "failure recovery"
  ],
  "striim_page_topics": [
    "Oracle source support",
    "Snowflake target support"
  ],
  "missing_topics": [
    "complete workflow",
    "failure recovery"
  ]
}
```

#### Specifications & Considerations

- URLs normalized via simple canonicalization. Original URLs are stored.
  - Add www/non-www handling
- URLs are normalized for deduplication.
- For redirects: track original URL with "redirect_from" field. Show final URL with redirect chain visible on click.
- Cited-page's main content area is downloaded. Raw HTML is stored as backup.
  - Use Readability or Trafilatura?
  - Top 20 cited pages are fully compared. For the rest, topic detection for efficiency.
- Source classification: if domains are known, classify accordingly. Otherwise, ask LLM. Move frequent unknowns to rules.
- High priority questions or questions w/ >20% visibility gap will be fully compared.
  - Deep content comparison on questions where Striim is underperforming
- Fetcher identifies honestly (`striim-aeo-monitor/1.0` user agent) and respects robots.txt. Fetcher config in settings (see Module 6).
- Cited pages that block the fetcher are recorded as `declined_by_site` and excluded from comparison. No browser-UA retries.
- Extractability check (Module 6) is reused on downloaded cited pages to build per-topic benchmarks at near-zero marginal cost.

### 6. Website and Crawler Accessibility

For each important Striim page, check:

- Whether the path is allowed by Striim's `robots.txt`.
- Whether the page appears in a sitemap.
- HTTP response status.
- Redirect behavior.
- Canonical URL.
- `noindex` directives.
- Response time.
- Basic internal-link discovery.
- Whether the page is listed in `llms.txt` (when one exists).
- Content extractability (main content readable without JavaScript, not gated).

Evaluate `robots.txt` rules for configured crawlers such as:

- `OAI-SearchBot`
- `GPTBot`
- `ChatGPT-User`
- `PerplexityBot`
- `Perplexity-User`
- `ClaudeBot`
- `Claude-SearchBot`
- `Googlebot`
- `Bingbot`

Example:

```json
{
  "url": "https://www.striim.com/product/oracle-cdc/",
  "crawler": "OAI-SearchBot",
  "robots_allowed": true,
  "in_sitemap": true,
  "status_code": 200,
  "noindex": false,
  "canonical_url": "https://www.striim.com/product/oracle-cdc/",
  "result": "publicly_accessible"
}
```

#### Agent Context Checks

Once per host per evaluation run, check whether the site publishes agent-oriented context artifacts:

```json
{
  "check_id": "site-ax-striim-2026-08",
  "host": "www.striim.com",
  "checked_at": "2026-08-17T18:00:00Z",
  "llms_txt": {
    "present": true,
    "url": "https://www.striim.com/llms.txt",
    "status_code": 200,
    "listed_urls": 41,
    "important_pages_listed": 14,
    "important_pages_total": 32,
    "coverage_pct": 0.44,
    "last_checked_hash": "sha256:ab12..."
  },
  "llms_full_txt": { "present": false },
  "markdown_doc_variants_present": false,
  "docs_mcp_server_present": false,
  "result": "partial_agent_context",
  "competitor_benchmark": [
    { "host": "www.fivetran.com", "llms_txt_present": true },
    { "host": "www.estuary.dev", "llms_txt_present": true }
  ]
}
```

Result values: `full_agent_context`, `partial_agent_context`, `no_agent_context`, `check_failed`.

#### Extractability Check

For each important Striim page (and reused on downloaded cited pages for benchmarking):

```json
{
  "url": "https://www.striim.com/product/oracle-cdc/",
  "checked_at": "2026-08-17T18:02:11Z",
  "fetch_user_agent": "striim-aeo-monitor/1.0",
  "raw_html_bytes": 148223,
  "extracted_text_chars": 5210,
  "extraction_tool": "trafilatura",
  "extractability_ratio": 0.035,
  "requires_js_render": true,
  "gating": {
    "is_gated": false,
    "gate_type": null
  },
  "structured_data": {
    "json_ld_present": true,
    "types": ["Organization", "FAQPage"]
  },
  "word_count_extracted": 890,
  "topic_benchmark": {
    "topic": "Oracle CDC",
    "median_cited_page_extractability": 0.21,
    "n_cited_pages": 18
  },
  "result": "poorly_extractable"
}
```

Result values: `well_extractable`, `poorly_extractable`, `js_dependent`, `gated`, `fetch_failed`. Gate types: `login_wall`, `form_gated_pdf`, `paywall`, `cookie_wall`, `geo_block`.

#### Fetcher Identity Config

The platform's own fetcher behaves as a transparent, well-behaved agent. Configured in settings alongside API spending limits:

```json
{
  "fetcher": {
    "default_user_agent": "striim-aeo-monitor/1.0 (internal AEO research)",
    "respect_robots_txt": true,
    "rate_limit_per_domain_rps": 0.5,
    "max_retries": 2,
    "timeout_seconds": 15,
    "simulation_agents": [
      "OAI-SearchBot",
      "GPTBot",
      "PerplexityBot",
      "Claude-SearchBot",
      "Googlebot",
      "Bingbot"
    ],
    "simulation_policy": "diagnostic_only",
    "on_blocked": "record_declined"
  }
}
```

The system must distinguish:

```
robots.txt:
What Striim tells the crawler it may access

Public HTTP check:
Whether the page appears reachable

Request logs:
What a real crawler requested and received

AI citation:
Whether the page appeared in an AI answer
```

#### Decisions to Make

- Important crawlers: OAI-SearchBot, PerplexityBot, Claude-SearchBot, GoogleBot, BingBot.
- How should robots.txt matching precedence be implemented?
  - urllib.robotparser (Python stdlib). Already tested; standard; no external dependency. Respects RFC; handles most crawlers correctly.
- HTTP checks use honest monitor UA by default. Re-check w/ crawler-specific agent (diagnostic only) if status != 200.
- Show both "Sitemap Coverage %" and "Discoverable (in sitemap or linked from home)". Combine for internal dashboard scoring.
- `extractability_ratio` = extracted_text_chars / raw_html_bytes. Crude alone; meaningful vs. per-topic cited-page median.
- `requires_js_render` = true when static extraction yields <30% of rendered-fetch text. Rendered fetch only as second pass on anomalously low ratios.
- `poorly_extractable` threshold (tune after first run): ratio < 0.5x topic median, or <300 words on a page mapped to a High-priority question.
- `last_checked_hash` on llms.txt enables change detection across monthly runs (did they act on our recommendation?).
- Competitor llms.txt benchmark is optional and cheap (one GET per competitor); strengthens evidence lines.
- Priority tier:
  1. HTTP 4xx, 5xx and noindex
  2. robots.txt blocked but cited
  3. gated or JS-dependent page mapped to a High-priority question
  4. missing sitemap or no internal links
  5. important page absent from llms.txt when llms.txt exists
  6. \>2 second response time

### 7. Request-Log Analysis

Support one request-log format.

The pipeline should:

- Read new log records.
- Parse provider-specific fields.
- Normalize records.
- Remove unnecessary sensitive fields.
- Identify likely AI crawler traffic.
- Group activity by crawler and page.
- Detect failures.
- Avoid duplicate ingestion.
- Track first and last observed crawler visits.

Detect:

- HTTP `403`.
- HTTP `404`.
- HTTP `429`.
- HTTP `5xx`.
- Repeated failures.
- Slow responses.
- Important pages with no observed crawler activity.
- Suspected spoofed crawler requests.

Example finding:

```
Crawler: OAI-SearchBot
Page: /product/oracle-cdc/

robots.txt: Allowed
Public HTTP check: 200
Actual observed crawler result: 403

Likely issue:
The crawler is allowed by published policy but blocked by the
traffic or security layer.
```

If production logs are unavailable, synthetic or sanitized sample logs are sufficient to build and test this module.

Each parsed record includes a user-agent classification:

```json
{
  "ua_classification": {
    "class": "delegated_agent",
    "matched_pattern": "agent-*",
    "tool_name": "cursor",
    "model_hint": "claude-sonnet-4-6",
    "known_crawler": false
  }
}
```

Class values: `known_ai_crawler`, `delegated_agent`, `search_crawler`, `human_browser`, `unknown`, `suspected_spoof`.

#### Decisions to Make

- Required fields: timestamp, host, path, status, user-agent
- Optional fields: response_time, content_length, referrer
- IP addresses are hashed. Query parameter values are removed.
- Last 90 days processed by default, can be over-riden.
- If IP doesn't resolve or reverse-DNS doesn't match crawler name, check verification.
- Low crawler activity: zero requests in 90 days, <1 requests per week.
  - This is a pretty arbitrary measure, will adjust accordingly.
- Parse the emerging `agent-TOOL` User-Agent convention alongside known bot strings.
- Index crawlers (GPTBot, ClaudeBot) vs. delegated agents (ChatGPT-User, Perplexity-User, agent-*) reported separately: crawler hits signal indexing coverage; delegated-agent hits signal live retrieval for a user, feeding the AI referral-traffic stretch goal.

### 8. Gap Detection

The system should identify six types of gaps.

#### Visibility Gap

Striim is not mentioned or appears below competitors.

#### Citation Gap

Competitor or third-party pages are cited, while relevant Striim pages are not.

#### Content Gap

Frequently cited pages answer the buyer question more clearly or completely than Striim content.

#### Technical Gap

A Striim page is blocked, missing from the sitemap, marked `noindex`, returning errors, or failing for real crawler requests.

#### Third-Party Authority Gap

Frequently cited external sources mention competitors but not Striim.

#### Agent Experience Gap

Striim content exists, is accessible, and covers the topic, but is not packaged for agent consumption while cited competitor content is (e.g., gated, JS-dependent, missing from `llms.txt`, poorly extractable).

Each gap should include:

```json
{
  "gap_id": "gap-oracle-snowflake-001",
  "topic": "Oracle to Snowflake",
  "gap_type": "content_gap",
  "striim_visibility": 0.10,
  "top_competitor_visibility": 0.58,
  "affected_prompts": [
    "oracle-snowflake-001",
    "oracle-snowflake-002"
  ],
  "evidence_ids": [
    "run-144",
    "citation-38",
    "page-check-12"
  ],
  "priority": "high"
}
```

Agent experience gaps carry an additional `ax_evidence` block:

```json
{
  "gap_id": "gap-oracle-snowflake-ax-001",
  "topic": "Oracle to Snowflake",
  "gap_type": "agent_experience_gap",
  "striim_visibility": 0.10,
  "top_competitor_visibility": 0.58,
  "affected_prompts": [
    "oracle-snowflake-001",
    "oracle-snowflake-002"
  ],
  "evidence_ids": [
    "site-ax-striim-2026-08",
    "page-check-ax-44",
    "citation-38"
  ],
  "ax_evidence": {
    "striim_page_extractability": 0.035,
    "cited_page_extractability_median": 0.21,
    "striim_page_gated": false,
    "striim_page_js_dependent": true,
    "page_in_llms_txt": false,
    "llms_txt_present": true,
    "competitors_with_llms_txt": 4,
    "competitors_tracked": 6
  },
  "priority": "high",
  "confidence": "medium"
}
```

#### Specifications & Considerations

- Meaningful gap is constituted one of two ways:
  1. Competitor mentions is greater than 2x Striim's mentions.
  2. Striim < 15% on high priority questions.
- Thresholds differ by priority:
  - High priority topics > 10% mention rate.
  - Medium priority topics > 5% mention rate.
  - Low priority topics > 2% mention rate.
  - Can be over-ridden
- Duplicate gaps (same topic, type, questions) are merged.
- Confidence calculated via [low, medium, high]:
  - high = 3+ pieces of strong evidence
  - medium = 2-3 pieces of evidence
  - low = 1 piece of evidence
- Gaps affecting low confidence, high priority topics, affecting 3+ questions should be reviewed by humans.
- Agent experience gap fires only when a visibility or citation gap already exists on the same topic AND at least one AX signal fires (js_dependent, gated, missing from llms.txt, extractability < 0.5x topic median). It is a cause layer, not a standalone finding.
- AX gaps and technical gaps on the same page do NOT merge: different owners (web/content vs. infra) and different fixes.
- Each AX signal counts as one piece of evidence toward confidence; extractability benchmarks count as strong evidence only when n_cited_pages >= 10 for the topic (consistent w/ n < 10 highlighting).

### 9. Recommendation Engine

Each important gap should produce a specific action.

A recommendation should contain:

- Problem.
- Supporting evidence.
- Affected questions.
- Affected pages.
- Competitors benefiting from the gap.
- Likely cause.
- Recommended action.
- Suggested owner.
- Priority.
- Estimated effort.
- Measurement plan.
- Confidence and limitations.

Example:

```
Problem:
Striim appears in only 10% of Oracle-to-Snowflake answers.

Evidence:
- Fivetran appears in 58% of responses.
- Frequently cited pages explain the complete workflow.
- Striim has separate Oracle and Snowflake pages but no combined
guide.
- Existing Striim pages are publicly accessible.

Recommended action:
Create an Oracle-to-Snowflake implementation guide.

Suggested sections:
- Architecture
- Initial load
- Continuous CDC
- Schema evolution
- Failure recovery
- Security
- Performance methodology
- Product limitations

Measurement:
Run the same question group after the page is published and
discoverable.
```

Agent experience gaps map to rule-based action types (no LLM needed; auto-draftable from evidence):

```
publish_llms_txt
add_pages_to_llms_txt
provide_extractable_html_variant
ungate_content
reduce_js_dependency
add_structured_data
publish_markdown_doc_variants
```

Example generated AX recommendation:

```json
{
  "rec_id": "rec-ax-012",
  "gap_id": "gap-oracle-snowflake-ax-001",
  "action_type": "add_pages_to_llms_txt",
  "problem": "3 important Oracle CDC pages are absent from llms.txt while the file exists and lists 41 other URLs.",
  "recommended_action": "Add /product/oracle-cdc/, /docs/oracle-to-snowflake/, and /blog/oracle-cdc-guide/ to llms.txt.",
  "evidence_ids": ["site-ax-striim-2026-08", "page-check-ax-44"],
  "suggested_owner": "Web",
  "priority": 7,
  "effort": 1,
  "measurement_plan": "Re-run Oracle CDC question group in the next monthly evaluation; compare citation rate for affected pages.",
  "limitations": "llms.txt adoption by answer engines is unverified; treat as a low-cost hypothesis, not an established ranking factor."
}
```

LLMs may help summarize the evidence and draft recommendations, but they must only use supplied evidence.

Every recommendation should include evidence identifiers.

#### Specifications & Considerations

- Rule-based recommendations:
  - Technical/citation gaps such as robots.txt blocks/missing from sitemap
  - Agent experience gaps: llms.txt, extractability, gating, and structured-data actions
- LLM-based recommendations:
  - Content gaps: what to write, topics to touch on, etc.
  - Human verified before publication
- Flow: (Gap, Evidence) → LLM summarizes → LLM suggests action → Human approves/rewrites
- Duplicate recommendations are merged if the recommended action and affected page is the same.
  - EX: "Create Oracle-to-Snowflake guide" for topics A, B, C is equal to 1 recommendation that affects 7 prompts across 2 topics.
- High-confidence & high-priority recommendations are auto-published. All else requires approval.
- Priority calculated on a 1-10 scale. Visibility gap x business tier.
- Effort calculated using a 1-3 point estimate.
  - 1: 1 day
  - 2: 1-5 days
  - 3: 1 week or more
- All AX recommendations require a `limitations` field stating that agent-context conventions (llms.txt, etc.) are early-stage and unproven for the engines tested. Repeat-run design is what tests the hypothesis empirically.
- AX recommendations are never auto-published regardless of confidence (unproven ranking factors).

## Dashboard

A simple dashboard is sufficient.

### Visibility View

- Striim and competitor visibility.
- Recommendation and citation rates.
- Topic and engine filters.
- Historical comparisons.

### Prompt Explorer

- Buyer question.
- Raw answers.
- Brands and positions.
- Claims.
- Citations.
- Detected gaps.
- Recommendations.

### Citation View

- Most-cited domains.
- Most-cited pages.
- Source categories.
- Sources mentioning competitors but not Striim.
- Content-comparison findings.

### Website Access View

| Page | Crawler | Robots | HTTP | Actual crawl | Result |
|---|---|---|---|---|---|
| Oracle CDC | OAI-SearchBot | Allowed | 200 | Observed | 200 |
| Oracle CDC | PerplexityBot | Allowed | 200 | Not observed | Unknown |
| Oracle CDC | ClaudeBot | Allowed | 200 | Observed | 403 |

### Action Queue

- Gap.
- Evidence.
- Recommended action.
- Priority.
- Suggested owner.
- Effort.
- Status.
- Measurement plan.

## Evaluation

Create a small labeled dataset containing:

- Answers with and without Striim.
- Ordered and unordered product lists.
- Answers with and without citations.
- Accurate and inaccurate claims.
- Known robots.txt results.
- Known request-log errors.
- Useful and unsupported recommendations.

Measure:

| Component | Evaluation |
|---|---|
| Prompt runner | Completion rate, retries, cost, latency |
| Brand extraction | Precision, recall |
| Position extraction | Accuracy |
| Citation extraction | Accuracy |
| URL normalization | Accuracy |
| Source classification | Accuracy |
| Website checks | Correct status, robots, sitemap, canonical, noindex |
| Log parser | Parsing success and duplicate rate |
| Crawler classification | Accuracy, incl. `agent-*` patterns and delegated agents |
| llms.txt parser | Parse success on real-world samples, coverage accuracy |
| Extractability check | JS-dependency detection precision on a labeled 20-page set |
| AX gap trigger | False-positive rate (page cited by engines despite low extractability) |
| Recommendations | Human rating for evidence, specificity, and usefulness |

## Current Technical Stack

```
Backend:          Python + FastAPI
Validation:       Pydantic
Database:         SQLite
Scheduling:       APScheduler or Cron
Web processing:   httpx + Beautiful Soup
LLM integration:  Direct model SDK with structured output
Dashboard:        Streamlit
Testing:          pytest
Deployment:       Docker
```
