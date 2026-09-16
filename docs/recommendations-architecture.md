# AEO Visibility Platform: Recommendations Technical Architecture

*Reflects code as of 2026-09-14 (branch `main`, working tree).*

## 1. Recommendation Generation

Recommendations are generated from detected gaps. Each gap fans out into **multiple** recommendations: one article recommendation plus up to three platform-specific social media recommendations (Reddit, LinkedIn, Facebook). Two paths exist — LLM-enhanced (when an engine is available and both LLM stages succeed) and template-based (fallback).

**Key point:** the social media recommendations only exist on the LLM path. The template fallback produces an article recommendation and nothing else.

### Entry Point

```
RecommendationGenerator(db_conn, engine=None)
  ↓
  generate_for_run(run_id, use_llm=True) -> (list[dict], float)
     ↓
     Reset self._recommendation_cost = 0.0
     ↓
     If use_llm is False: self.engine = None  (disables LLM for the rest of the instance's life)
     ↓
     SELECT gaps WHERE run_id = ?  (parses affected_prompts / evidence_ids JSON)
     ↓
     For each gap: recommendations.extend(generate_for_gap(gap))
        ↓
        Path A: LLM-enhanced (requires self.engine AND diagnosis AND article rec)
        │  ↓
        │  Stage 1: _diagnose_gap_with_llm()
        │  │  ↓
        │  │  RAG-retrieve top-3 methods sections for the gap
        │  │  ↓
        │  │  run_with_structured_output(prompt, GAP_DIAGNOSIS_SCHEMA)
        │  │  ↓
        │  │  Return {diagnosis, root_causes[]} or None on failure
        │  ↓
        │  Stage 2: _generate_article_recommendation_with_llm(gap, diagnosis)
        │  │  ↓
        │  │  RAG-retrieve top-3 methods sections again
        │  │  ↓
        │  │  run_with_structured_output(prompt, ARTICLE_RECOMMENDATION_SCHEMA)
        │  │  ↓
        │  │  Return {article_suggestion, recommended_action, evidence_summary,
        │  │           implementation_steps[]} or None on failure
        │  ↓
        │  Stage 3: for platform in [reddit, linkedin, facebook]:
        │     ↓
        │     _generate_social_media_recommendation_with_llm(gap, platform, diagnosis)
        │        ↓
        │        Platform-specific prompt from PLATFORM_PROMPTS
        │        ↓
        │        run_with_structured_output(prompt, SOCIAL_MEDIA_RECOMMENDATION_SCHEMA)
        │        ↓
        │        Appended only if the call succeeds (failures are skipped silently)
        ↓
        Path B: Template-based fallback (article only)
```

Returns a **tuple** of `(flattened list of recommendation dicts, total LLM cost in dollars)`.

### Path A Gating

Path A requires *both* LLM stages to succeed:

```python
if self.engine:
    diagnosis = self._diagnose_gap_with_llm(gap)
    if diagnosis:
        llm_recommendation = self._generate_article_recommendation_with_llm(gap, diagnosis)

if llm_recommendation and diagnosis:   # Path A
    ...
else:                                   # Path B
    ...
```

A failed diagnosis drops the gap all the way back to the template path — there is no "continue with article generation using gap context alone" fallback.

### Article Recommendation Shape (Path A)

```python
{
  "id": uuid4,
  "gap_id": gap["id"],
  "type": "article",
  "problem": "Striim appears in only {x}% of answers for '{topic}', while {competitor} "
             "appears in {y}%. Root cause: {diagnosis}",
  "evidence_summary": <LLM> or "{n} evidence sources",
  "recommended_action": <LLM>,
  "affected_pages": ["https://striim.com/topic/{topic.lower()}"],
  "suggested_owner": "Content Team",
  "priority": 3 | 5 | 6 | 8,
  "estimated_effort": 2,
  "measurement_plan": "Re-run '{topic}' questions after implementation and compare visibility metrics.",
  "confidence": gap["confidence"],
  "will_auto_publish": bool,
  "status": "pending_publish" | "draft",
  "created_timestamp": iso8601,
  "diagnosis": str,                    # LLM
  "root_causes": [str],                # LLM
  "article_suggestion": {...},         # LLM
  "implementation_steps": [{step, effort, owner, notes?}],
}
```

### Social Media Recommendation Shape (Path A)

```python
{
  "id": uuid4,
  "gap_id": gap["id"],
  "type": "social_media",
  "platform": "reddit" | "linkedin" | "facebook",
  "problem": <same problem string as the article rec>,
  "evidence_summary": <LLM>,
  "recommended_action": <LLM>,
  "affected_pages": ["https://striim.com/topic/{topic.lower()}"],
  "suggested_owner": "Marketing Team",
  "priority": max(1, article_priority - 2),
  "estimated_effort": 1,
  "measurement_plan": "Track engagement metrics on {platform} posts related to '{topic}'.",
  "confidence": gap["confidence"],
  "will_auto_publish": False,          # social recs never auto-publish
  "status": "draft",
  "implementation_steps": [str],       # NOTE: flat strings, not step objects
  "content_outline": str,
  "hashtags": [str],
  "frequency": str,
}
```

`implementation_steps` is a list of **objects** on article recs and a list of **plain strings** on social recs. Both go into the same `recommendations.implementation_steps` JSON column, so any consumer has to handle both shapes. The dashboard renderer does; other consumers should be checked.

### Template Generation (Path B)

Fires when no engine is configured, or when either LLM stage fails. Produces exactly one article recommendation.

**Visibility gaps:**
```python
problem = ("Striim appears in only {x}% of answers for '{topic}', "
           "while {competitor} appears in {y}%.")
recommended_action = ("Create a comprehensive '{topic}' implementation guide covering: "
                      "architecture, initial load, continuous CDC, schema evolution, "
                      "failure recovery, security, performance methodology, and product limitations.")
suggested_owner = "Content Team"
estimated_effort = 2
implementation_steps = _get_fallback_implementation_steps_for_visibility()   # 7 steps
```

**Citation gaps:**
```python
problem = "On '{topic}' questions, {competitor} pages are cited while relevant Striim content is not."
recommended_action = ("Create or update Striim pages for '{topic}' with detailed examples, "
                      "comparison to competitors, and discoverable content.")
suggested_owner = "Content Team"
estimated_effort = 2
implementation_steps = _get_fallback_implementation_steps_for_citation()     # 5 steps
```

**Any other gap type:**
```python
problem = "Gap detected: {gap_type}"
recommended_action = "Investigate {gap_type} gap for '{topic}'"
suggested_owner = "Product Manager"
estimated_effort = 1
implementation_steps = [{"step": "Investigate ...", "effort": "Medium", "owner": "Product Manager"}]
```

The hardcoded fallback step lists (`_get_fallback_implementation_steps_for_visibility` / `_for_citation`) are also used on Path A whenever the LLM omits `implementation_steps`, even though the schema marks that field required.

---

## 2. Priority & Confidence Scoring

Scoring happens at two levels: gap-level (Module 8 gap detection) and recommendation-level (Module 9 generation).

### Gap Priority Calculation

`aeo_eval/gaps/thresholds.py::calculate_gap_priority` — visibility gaps only:

```python
gap_ratio = (competitor_visibility - striim_visibility) / max(striim_visibility, 0.01)

if gap_ratio > 3.0:    return "high"      # competitor >4x Striim
elif gap_ratio > 1.5:  return "medium"
else:                  return "low"
```

Citation gaps skip this entirely and use a citation-count rule instead (below).

**Thresholds for flagging visibility gaps (`should_flag_visibility_gap`):**

| Topic tier | Absolute threshold | Relative threshold |
|---|---|---|
| High | Striim < 15% | OR competitor > 2.0× Striim |
| Medium (default) | Striim < 5% | OR competitor > 2.0× Striim |
| Low | Striim < 2% | OR competitor > 2.0× Striim |

Topic tier comes from the highest `priority` among that topic's rows in the `prompts` table, defaulting to `Medium`. The relative branch additionally requires `striim_mention_rate > 0` and `top_competitor_mention_rate > 0`, so a topic where Striim scores 0% is caught by the absolute branch, not the relative one. Topics with fewer than 3 responses are skipped.

**Citation gap rule (`detect_citation_gaps`):** run-scoped; a topic fires a gap when it has **zero** Striim-owned citations and **≥ 3** competitor-owned citations in this run.

```python
priority   = "high" if competitor_citations > 5 else "medium"
confidence = "high" if competitor_citations > 5 else "medium"
```

For citation gaps `striim_visibility` is stored as `0.0` and `top_competitor_visibility` holds a raw **count**, not a rate — the `:.0%` formatting in recommendation text renders that count as a percentage (6 citations → "600%"). Known cosmetic defect.

### Confidence Scoring (visibility gaps)

```python
if num_responses >= 10:  confidence = "high"
elif num_responses >= 5: confidence = "medium"
else:                    confidence = "low"
```

Stored on the gap; inherited verbatim by every recommendation generated from it.

### Recommendation Priority (1–10 scale)

```python
if gap["priority"] == "high":
    priority = 8 if gap["striim_visibility"] < 0.1 else 6
elif gap["priority"] == "medium":
    priority = 5
else:
    priority = 3
```

Social recommendations then take `max(1, priority - 2)`.

**Reachable values:**

| Value | Meaning | Applies to |
|---|---|---|
| 8 | High gap + Striim visibility < 10% | article |
| 6 | High gap + Striim visibility ≥ 10%, or social rec derived from priority 8 | article, social |
| 5 | Medium gap | article |
| 4 | Social rec from a priority-6 article | social |
| 3 | Low gap, or social rec from a priority-5 article | article, social |
| 1 | Social rec from a priority-3 article | social |

Because citation gaps always carry `striim_visibility = 0.0`, every high-priority citation gap lands at priority 8.

---

## 3. Auto-Publish / Auto-Approval Logic

There are **two** thresholds in the codebase, applied at different points.

### In the Generator (`generate_for_gap`)

```python
will_auto_publish = confidence == "high" and priority >= 8
status = "pending_publish" if will_auto_publish else "draft"
```

### In the Orchestrator (`recommendations/approval.py::should_auto_approve`)

```python
def should_auto_approve(recommendation: dict) -> bool:
    is_high_priority   = recommendation.get("priority", 0) >= 7
    is_high_confidence = recommendation.get("confidence") == "high"
    return is_high_priority and is_high_confidence
```

**These two rules coincide in practice** — no recommendation ever has priority 7, so `>= 7` and `>= 8` select the same set. The duplication is a latent hazard: changing one threshold without the other would silently split the behavior.

### Net Effect in the Pipeline

```
generator sets status = "pending_publish"
  ↓
  orchestrator saves it
     ↓
     should_auto_approve(rec) is True (same criteria)
        ↓
        update_recommendation_status(id, "approved", approved_by="system",
                                    review_notes="Auto-approved: high priority + high confidence")
```

So `pending_publish` is a **transient** state on the orchestrator path — it is written and immediately overwritten with `approved`. It is only observable for recommendations persisted outside the orchestrator (e.g. `save_recommendations()` called directly). The dashboard's approval view still offers a `pending_publish` filter, which will normally be empty after a full pipeline run.

Social media recommendations never auto-approve: their max priority is 6.

**`will_auto_publish` is not persisted.** There is no such column, and `save_recommendation` reads `recommendation["status"]` directly despite its docstring claiming it derives status from `will_auto_publish`. The flag exists only in memory.

---

## 4. LLM Integration (Claude)

### Engine Resolution (Orchestrator)

```python
if self.engine.name == "claude":
    recommendation_engine = self.engine
else:
    try:
        recommendation_engine = create_engine("claude")   # via factory, so it gets provider config + API key
    except Exception:
        recommendation_engine = None                      # falls through to template path

generator = RecommendationGenerator(conn, engine=recommendation_engine)
recommendations, recommendation_cost = generator.generate_for_run(run_id)
```

Going through `create_engine` rather than constructing `ClaudeEngine()` directly matters: the pipeline's config dict does not carry provider credentials.

**Model:** whatever `providers.claude.model_name` is in `config.yaml` — currently `claude-opus-5`. Not hardcoded in the recommendation code.

### Structured Output

All three LLM calls use `engine.run_with_structured_output(prompt, schema)`, which drives the Messages API `output_config.format = {"type": "json_schema", "schema": ...}`.

Two constraints worth knowing:

1. **Every object in a schema must set `"additionalProperties": false` explicitly** or the API rejects the request with a 400. All three recommendation schemas do.
2. **Truncation is a silent data loss.** If the response hits `max_tokens` mid-document the JSON fails to parse and `run_with_structured_output` returns `{"raw_response": ...}`; the caller then falls back to empty/default fields. The engine logs a warning naming `providers.<name>.max_tokens`. That knob is now a config field (`ProviderConfig.max_tokens`, default 8000, min 1000). Article recommendations with seven implementation steps are the largest documents the pipeline generates and the most likely to hit it.

### Cost Tracking

Each successful structured call adds `call.cost` to `self._recommendation_cost`. `generate_for_run` returns the accumulated total, and the orchestrator folds it into the run's cost:

```python
if recommendation_cost > 0:
    current_cost = SELECT cost FROM evaluation_runs WHERE run_id = ?
    UPDATE evaluation_runs SET cost = current_cost + recommendation_cost WHERE run_id = ?
```

Note: cost is accumulated on `self`, so a single generator instance reused across runs without calling `generate_for_run` (which resets the counter) would double-count. Mock engines report zero cost — they make no API calls.

### Schemas

**`GAP_DIAGNOSIS_SCHEMA`**
```json
{"diagnosis": "string", "root_causes": ["string"]}
```

**`ARTICLE_RECOMMENDATION_SCHEMA`**
```json
{
  "article_suggestion": {
    "title": "string",
    "recommended_sections": ["string"],
    "how_it_improves_aeo": "string",
    "source_type": "guide | blog_post | tutorial"
  },
  "recommended_action": "string",
  "evidence_summary": "string",
  "implementation_steps": [
    {
      "step": "string",
      "effort": "Low | Medium | High",
      "owner": "Content Team | Product Manager | Engineering",
      "notes": "string (optional)"
    }
  ]
}
```
All four top-level fields are required.

**`SOCIAL_MEDIA_RECOMMENDATION_SCHEMA`**
```json
{
  "recommended_action": "string",
  "implementation_steps": ["string"],
  "content_outline": "string",
  "hashtags": ["string"],
  "frequency": "string",
  "evidence_summary": "string"
}
```
All six fields required.

### Platform Prompts

`PLATFORM_PROMPTS` holds one template per platform, each with tailored focus areas:

- **Reddit** — subreddit identification, discussion-thread ideas, posting times, engagement strategy for technical communities.
- **LinkedIn** — thought leadership pieces, professional groups, influencer engagement, authority building.
- **Facebook** — groups/communities, recurring series, discussion prompts, algorithmic reach.

Each is formatted with `{topic}`, `{gap_type}`, `{striim_vis:.1%}`, and `{diagnosis}`.

### Error Handling

| Failure | Behavior |
|---|---|
| Diagnosis call fails | Warning logged; whole gap falls back to the template path |
| Article call fails | Warning logged; whole gap falls back to the template path |
| Social call fails | Warning logged; that platform is skipped, others continue |
| Unknown platform | Returns `None` immediately (no engine call) |
| JSON truncated at `max_tokens` | Engine logs which config key to raise; caller sees defaults |

---

## 5. RAG System for Methods Context

### Data Flow

```
methods.txt (repo root, ~7 KB)
  ↓
  RecommendationGenerator.__init__ → _load_methods_context()
  ↓
  MethodsRAG.initialize_methods(text)      [called once per generator, failures logged not raised]
    ↓
    chunk_methods_text(): split on r'\n(\d+\.\s+[^\n]+)' — numbered section headings
    ↓
    topic = text after ":" in the heading, else the whole heading
    ↓
    INSERT OR REPLACE INTO method_sections (embedding may be NULL)

Per LLM call (diagnosis and article generation each do this separately)
  ↓
  _get_methods_context_for_gap(gap)
    ↓
    context = "Gap type: {t}. Topic: {topic}. Visibility: {x}%."
    ↓
    rag.retrieve_relevant_sections(context, top_k=3)
    ↓
    "\n\n".join(sections), or full methods.txt on exception
```

### Embedding Details (as Designed)

| Property | Value |
|---|---|
| Model | `claude-3-5-sonnet-20241022` via `client.messages.embed(...)` |
| Dimensions | 1536 float32 |
| Storage | `struct.pack`'d blob in `method_sections.embedding` |
| Similarity | Cosine, computed in Python over all rows |
| Retrieval | Top-K, K=3 (hardcoded default) |

### ⚠️ Current Behavior: Retrieval Always Falls Back

`MethodsRAG._embed_text` calls `client.messages.embed(...)`. **The Anthropic Messages API has no `embed` method** — Anthropic does not ship a first-party embeddings endpoint. That call raises, is caught, and returns `None`. Consequences:

- `method_sections.embedding` is always `NULL`.
- `retrieve_relevant_sections` fails to embed the gap context and returns `_get_all_sections()` — **every** stored section, ordered by topic, not the top 3.
- Both LLM prompts therefore receive the entire methods corpus (~7 KB) rather than a targeted retrieval.

The system is functionally correct (the model gets the methods) but the retrieval is inert, and the full corpus inflates every prompt's input tokens. Fixing this requires a real embeddings provider (Voyage AI is Anthropic's documented recommendation) and a re-run of `initialize_methods`.

### Fallback Chain

```
_embed_text returns None      → _get_all_sections()          (all sections)
no rows in method_sections    → _get_all_sections()          (empty list)
no section has an embedding   → _get_all_sections()
retrieve raises               → self.methods_context          (raw methods.txt)
methods.txt missing           → ""                            (warning logged; prompts carry no methods)
```

### `method_sections` Schema

```sql
CREATE TABLE IF NOT EXISTS method_sections (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    section_title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,           -- float32[1536], currently always NULL
    embedding_model TEXT,     -- "claude"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_method_sections_topic ON method_sections(topic);
CREATE UNIQUE INDEX IF NOT EXISTS idx_method_sections_topic_title
    ON method_sections(topic, section_title);
```

The unique index on `(topic, section_title)` is what makes `INSERT OR REPLACE` idempotent across generator instantiations — without it every run would duplicate the corpus.

---

## 6. Database Schema & Workflow

### Recommendations Table

```sql
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    gap_id TEXT NOT NULL,
    problem TEXT NOT NULL,
    evidence_summary TEXT,
    recommended_action TEXT NOT NULL,
    affected_pages TEXT,       -- JSON: ["https://...", ...]
    suggested_owner TEXT,
    priority INTEGER,          -- 1-10
    estimated_effort INTEGER,  -- 1-3 (story points)
    measurement_plan TEXT,
    confidence TEXT,           -- "high", "medium", "low"
    status TEXT NOT NULL DEFAULT "draft",
    created_by TEXT,
    approved_by TEXT,
    approval_timestamp DATETIME,
    review_notes TEXT,         -- JSON: {comment, reason} or a JSON-encoded string
    platform TEXT,             -- "reddit" | "linkedin" | "facebook"; NULL for articles
    implementation_steps TEXT, -- JSON: [{step, effort, owner, notes?}] or ["step", ...]
    templates_applied TEXT,    -- JSON: [template_id, ...]
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (gap_id) REFERENCES gaps(id)
);
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations(status);
CREATE INDEX IF NOT EXISTS idx_recommendations_gap_id ON recommendations(gap_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_priority_status ON recommendations(priority DESC, status);
CREATE INDEX IF NOT EXISTS idx_recommendations_platform ON recommendations(platform);
```

Three columns added since the last revision: `platform`, `implementation_steps`, `templates_applied`. `save_recommendation` / `save_recommendations` branch on whether any of those keys are present in the dict and emit a narrower INSERT if not, for backward compatibility with older callers.

Fields the generator produces that are **not persisted**: `type`, `will_auto_publish`, `diagnosis`, `root_causes`, `article_suggestion`, `content_outline`, `hashtags`, `frequency`. The LLM's article title, sections, and rationale — and the full social media content plan — live only in the returned dicts and are lost after the orchestrator writes the row. Recovering them means re-running generation. This is the most significant persistence gap in the module.

### `recommendation_templates` Table

```sql
CREATE TABLE IF NOT EXISTS recommendation_templates (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,       -- "article", "reddit", "linkedin", "facebook"
    template_type TEXT NOT NULL,  -- "implementation_steps", "content_outline", "post_template"
    content TEXT NOT NULL,        -- JSON: template structure and variables
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

CRUD exists in `SQLiteStore` (`save_recommendation_template`, `get_recommendation_template`, `get_recommendation_templates(platform=, template_type=)`), but **nothing in the generation path reads or writes it**. The generator's templates are Python constants (`PLATFORM_PROMPTS`, `_get_fallback_implementation_steps_*`), and `templates_applied` is never populated. The table is scaffolding for a future externalized-template feature.

### Status Workflow

```
Recommendation created (generate_for_gap)
  ↓
  ├─ article, confidence == "high" AND priority >= 8
  │    ├─> status = "pending_publish"
  │         ├─ orchestrator: should_auto_approve() → "approved" (approved_by = "system")
  │
  ├─ article, otherwise            → status = "draft"
  ├─ social media (always)         → status = "draft"

Manual transitions (dashboard Recommendations view):
  draft / pending_publish / pending_approval / edited
    ├─ Edit    → status = "edited"     (direct UPDATE; problem, action, priority, effort)
    ├─ Approve → status = "approved"   (approved_by = "dashboard_user", approval_timestamp set)
    └─ Reject  → status = "rejected"   (review_notes = reason)
```

Statuses in use: `draft`, `pending_publish`, `pending_approval`, `edited`, `approved`, `rejected`. The schema's inline comment still lists the older set (`draft, pending_approval, approved, rejected, implemented`) and omits `pending_publish` and `edited` — the comment is stale; there is no CHECK constraint, so nothing enforces either list. `implemented` is defined but never written by any code path.

### Store API

| Method | Purpose |
|---|---|
| `save_recommendation(rec)` | Single INSERT; branches on presence of the three newer columns |
| `save_recommendations(recs)` | Batch INSERT in one transaction, rollback on error |
| `update_recommendation_status(id, status, approved_by=, review_notes=)` | Sets status + approval fields; `approval_timestamp` only set when `approved_by` is given; `review_notes` is `json.dumps`'d |
| `get_recommendation(id)` | Full row with `affected_pages`, `review_notes`, `implementation_steps`, `templates_applied` JSON-parsed |
| `update_recommendation(id, updates)` | Allowlisted field update — `problem`, `recommended_action`, `priority`, `estimated_effort`, `status`, `review_notes`, `suggested_owner`, `measurement_plan`, `confidence`, `affected_pages`. Returns bool |
| `approve_recommendation(id, approved_by)` | Status → approved, stamps timestamp |
| `reject_recommendation(id, review_notes)` | Status → rejected, `review_notes` stored as `{"reason": ...}` |

Two rejection paths store `review_notes` differently: `reject_recommendation` writes `{"reason": "..."}`, while the dashboard's Reject button calls `update_recommendation_status`, which writes a bare JSON-encoded string. Readers must handle both.

### Gaps Table (Source of Recommendations)

```sql
CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    gap_type TEXT NOT NULL,   -- "visibility" | "citation" (content/technical/authority deferred)
    striim_visibility REAL,
    top_competitor_visibility REAL,
    top_competitor_name TEXT,
    affected_prompts TEXT,    -- JSON; currently always [] — never populated by the detector
    evidence_ids TEXT,        -- JSON: ["metrics-{run_id}-{topic}"] or ["citations-{run_id}-{topic}"]
    priority TEXT,            -- "high", "medium", "low"
    confidence TEXT,          -- "high", "medium", "low"
    run_id TEXT NOT NULL,
    created_timestamp DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES evaluation_runs(run_id)
);
```

`evidence_ids` always holds exactly one synthetic identifier, so every recommendation's `evidence_summary` fallback reads "1 evidence sources" — and the diagnosis prompt always reports "Evidence sources: 1, Affected questions: 0". The LLM is being told the gap has essentially no evidence behind it. Populating `affected_prompts` from a `response_analysis` join is the single highest-leverage improvement available to prompt quality here.

### Data Retention

From `data_retention_policy`:

| Table | Retention |
|---|---|
| `raw_responses`, `response_analysis`, `citations`, `website_checks` | 365 days |
| `crawler_logs` | 90 days |
| `visibility_metrics`, `gaps`, `recommendations`, `method_sections` | NULL (indefinite) |

Because raw responses age out at 365 days while recommendations are kept forever, recommendations eventually outlive the evidence that produced them.

### Query Patterns

```sql
-- Dashboard: all recommendations for a run
SELECT r.* FROM recommendations r
JOIN gaps g ON r.gap_id = g.id
WHERE g.run_id = ?
ORDER BY r.priority DESC, r.status = 'approved' DESC;

-- Dashboard: approval queue
SELECT r.* FROM recommendations r
JOIN gaps g ON r.gap_id = g.id
WHERE g.run_id = ?
  AND r.status IN ('draft', 'pending_approval', 'pending_publish', 'edited')
ORDER BY r.priority DESC;

-- Social recommendations for one platform
SELECT * FROM recommendations WHERE platform = 'linkedin' ORDER BY priority DESC;

-- Articles only
SELECT * FROM recommendations WHERE platform IS NULL ORDER BY priority DESC;
```

---

## 7. Dashboard

Two Streamlit views consume recommendations (`aeo_eval/dashboard/app.py`):

**Gaps & Recommendations** (`render_gaps_recommendations_view`) — read-oriented. Lists gaps and their recommendations with status badges, evidence expander, and an implementation-steps expander.

**Recommendations** (`render_recommendations_view`) — the approval UI. Per recommendation: status badge, platform badge (color-coded per platform), priority, implementation steps, and four actions — **Edit** (inline form for problem / action / priority / effort; saving sets status to `edited`), **Approve**, **Reject** (with a reason form), **Details**. A status filter covers All / Draft / Pending Approval / Pending Publish / Edited.

Both views tolerate rows missing `platform` and `implementation_steps` via `'key' in rec.keys()` guards, so they work against pre-migration databases.

The Edit save path opens its own `sqlite3` connection and issues a raw UPDATE rather than going through `SQLiteStore.update_recommendation`, bypassing that method's field allowlist and error handling. Worth consolidating.

---

## 8. Pipeline Integration

Module 9 of the evaluation pipeline:

```
Module 2: Evaluation             → run prompts through the answer engine
Module 3: Response Analysis      → extract brands, positions, claims, citations
Module 4: Metrics Calculation    → visibility rates per topic
Module 5: Citation Dedup         → deduplicate and classify URLs
Module 6: Website Accessibility  → robots.txt, sitemap, response times (optional)
Module 8: Gap Detection          → visibility + citation gaps, priority + confidence
Module 9: Recommendation Generation  → YOU ARE HERE
  ├─ Resolve a Claude engine (reuse, or build via factory, or None)
  ├─ generate_for_run(run_id) → (recommendations, cost)
  ├─ Fold LLM cost into evaluation_runs.cost
  ├─ save_recommendation() per rec
  └─ should_auto_approve() → update_recommendation_status(..., "approved", approved_by="system")
```

`run_full_pipeline` returns `{run_id, num_prompts, num_gaps, num_recommendations, num_auto_approved}`.

**Volume:** each gap yields up to 4 recommendations on the LLM path and exactly 1 on the template path, at a cost of up to 4 Claude calls per gap (1 diagnosis + 1 article + 3 social, minus any that fail). A run with 10 gaps is ~50 structured-output calls. With `general.cost_limit_per_run` at 1.0 and `cost_limit_per_day` at 5.0 (lowered from 10.0), recommendation generation is now a material share of a run's budget, not a rounding error.

---

## 9. Implementation Notes

### Implemented
- Recommendation generation from gaps — LLM and template paths
- Two-stage LLM flow: diagnosis → article recommendation, with structured output
- Platform-specific social media recommendations for Reddit, LinkedIn, Facebook
- Implementation steps with per-step effort and owner (LLM-generated, hardcoded fallbacks)
- RAG scaffolding: chunking, storage, cosine similarity, top-K retrieval *(retrieval inert — see §5)*
- Priority scoring (1–10) and confidence inheritance from gaps
- Auto-approval on high priority + high confidence
- Full approval workflow: draft → edited/approved/rejected, with reviewer and timestamp
- Streamlit approval UI with edit, approve, reject, details, and status filtering
- Per-call LLM cost tracking folded into run totals
- Configurable `max_tokens` per provider, with truncation diagnostics

### Deferred / Not Implemented
- `content`, `technical`, and `authority` gap types (detector returns visibility + citation only)
- `recommendation_templates` table is created and has CRUD, but no code path reads or writes it; `templates_applied` is always NULL
- `affected_prompts` on gaps is always `[]`
- `implemented` status is defined but never set
- Persistence of `diagnosis`, `root_causes`, `article_suggestion`, `content_outline`, `hashtags`, `frequency`

### Known Issues
1. **RAG retrieval is inert** — `client.messages.embed` is not a real Anthropic API, so embeddings are always NULL and every prompt gets the full methods corpus (§5).
2. **Duplicated auto-approval thresholds** — `>= 8` in the generator, `>= 7` in `should_auto_approve`; equivalent today only because priority 7 is unreachable (§3).
3. **`implementation_steps` is polymorphic** — objects for articles, strings for social, same column (§1).
4. **Citation gap percentages render as counts** — `top_competitor_visibility` holds a count formatted with `:.0%` (§2).
5. **Empty evidence in prompts** — `evidence_ids` has one synthetic entry, `affected_prompts` is empty; the LLM diagnoses gaps it is told have no supporting evidence (§6).
6. **`will_auto_publish` is never persisted** despite store docstrings describing it as the source of `status` (§3).
7. **Two `review_notes` encodings** — `{"reason": ...}` vs. a bare JSON string, depending on which path rejected (§6).
8. **Dashboard edit bypasses the store layer** — raw SQL, no field allowlist (§7).

### Fallback Behaviors
- **No engine, or either LLM stage fails** → template article recommendation, no social recommendations
- **Social stage fails for one platform** → that platform skipped, others continue
- **RAG retrieval fails** → all stored sections, then raw `methods.txt`, then empty string
- **LLM omits `implementation_steps`** → hardcoded fallback list for the gap type
- **Structured response truncated** → `{"raw_response": ...}`, caller uses defaults, warning names the config key to raise
