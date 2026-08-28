# Bug-Fix Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the fourteen correctness bugs found in the AEOvis pipeline (data persistence, citation history, gap detection, LLM structured output, cost accounting, metrics, dashboard, CLI, retention) without touching Modules 6/7.

**Architecture:** The pipeline is `CLI/dashboard → AEOPipelineOrchestrator → Evaluator (engine + Module 3 analysis) → SQLite → metrics/citations/gaps/recommendations → dashboard`. All fixes preserve that shape; the biggest structural changes are (a) persistence moves from the analysis path into `Evaluator.run_one` so every result is stored, (b) `citation_occurrences` starts being written so citation data becomes run-scoped, and (c) engines gain a real schema-enforced structured-output call whose cost is accounted for.

**Tech Stack:** Python ≥3.9, Pydantic v2 (config only), SQLite (stdlib `sqlite3`), pytest, `anthropic` SDK, `openai` SDK, Streamlit + Plotly (dashboard).

**Spec:** No standalone spec file — this implements the bug-fix design approved in conversation on 2026-08-17. The bug inventory below is the authoritative scope. Platform spec for context: `spec.md` (repo root).

## Bug Inventory (scope)

| ID | Bug | Task |
|---|---|---|
| A2 | Two DBs with different defaults (`data/eval_runs.db` via config vs hardcoded `data/aeovis.db`) | 1 |
| E1 | CLI advertises engines that don't exist; ★ CLI passes a `ProviderConfig` object where a dict is required, crashing `run --engine claude` with `AttributeError` | 2 |
| A1 | Failed/timeout/rate-limited results never persisted | 3 |
| A1b | ★ `evaluation_runs` totals never written — dashboard cost always $0.00 | 4 |
| A3 | `INSERT OR REPLACE` wipes citation history; `citation_occurrences` never written | 5 |
| A4 | Citation gaps scan all history, not the run; same-domain comparison is degenerate | 6 |
| A5 | Visibility thresholds always use "Medium"; case mismatch `high` vs `High` | 7 |
| B1 | Claude "structured output" is prompt-and-pray; ★ `temperature=0` 400s on `claude-opus-5`; `openai` missing from dependencies | 8 |
| B2 | Analysis LLM calls bypass rate limiter and cost tracker; analyzer engine is whatever engine is under test | 9 |
| C1 | `recommendation_rate` faked as `mention_rate` despite `striim_recommended` being stored | 10 |
| C2 | `citation_rate` can exceed 100%; by-topic citation rate hardcoded 0 | 11 |
| D1/D3 | Dashboard topic filter crashes (`p.get` on dataclass); fake topic list; `run_type="dashboard"` off-Literal | 12 |
| D2 | Dashboard citation counts always 0 (reads never-written table, ignores run_id) | 13 |
| E2 | Retention policy recorded but never enforced | 14 |

Decisions locked in during design approval: analyzer engine defaults to **Claude with fallback to the engine under test**; `data/aeovis.db` is **left in place** (just no longer written to); modules 6 and 7 are **out of scope**.

## Global Constraints

- Python ≥ 3.9 (`pyproject.toml` `requires-python`): no `match` statements, use `Optional[X]` / `List[X]` typing.
- Canonical DB path is `config.general.output_db_path` (default `data/eval_runs.db`). Never hardcode `data/aeovis.db` anywhere.
- Do NOT implement Modules 6/7. `website_checks` and `crawler_logs` tables stay untouched.
- Tests must never write to real files under `data/` — the autouse fixture in Task 1 guarantees this; every test that needs a DB passes an explicit `tmp_path` path or relies on that fixture.
- The virtualenv is `.venv/` at repo root. Run tests as: `.venv/bin/python -m pytest tests/ -v` (or activate first).
- One commit per task, conventional-commit style (`fix:`, `feat:`, `test:`).
- Leave `data/aeovis.db` and `data/eval_runs.db` files on disk untouched.
- All timestamps written by us use `datetime.now().isoformat()` to match existing rows.

---

### Task 1: Test isolation + canonical DB path (A2)

The orchestrator defaults to a hardcoded `"data/aeovis.db"` at `aeo_eval/orchestrator.py:49` instead of the configured path. Also, several code paths default to the configured DB, so tests must be isolated from the real `data/` directory before anything else changes.

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_db_path.py`
- Modify: `aeo_eval/orchestrator.py` (imports + line 49)

**Interfaces:**
- Consumes: `aeo_eval.config.config` (global `Config` object), `AEOPipelineOrchestrator(engine, config: dict)`.
- Produces: invariant used by every later task — `AEOPipelineOrchestrator(...).db_path == config dict "db_path" if set, else str(app_config.general.output_db_path)`. Also the autouse `isolate_db_path` fixture all later tests rely on.

- [ ] **Step 1: Write the autouse isolation fixture**

Create `tests/conftest.py`:

```python
"""Shared test fixtures."""
import pytest


@pytest.fixture(autouse=True)
def isolate_db_path(monkeypatch, tmp_path):
    """Point the configured output DB at a per-test temp file.

    Any code path that falls back to config.general.output_db_path must
    never touch the real data/ directory during tests.
    """
    from aeo_eval.config import config as app_config

    monkeypatch.setattr(app_config.general, "output_db_path", tmp_path / "test.db")
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_db_path.py`:

```python
"""Canonical database path resolution."""
from aeo_eval.config import config as app_config
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.orchestrator import AEOPipelineOrchestrator


def test_orchestrator_defaults_to_config_db_path():
    orch = AEOPipelineOrchestrator(MockEngine(), config={})
    assert orch.db_path == str(app_config.general.output_db_path)


def test_orchestrator_explicit_db_path_wins(tmp_path):
    db = tmp_path / "explicit.db"
    orch = AEOPipelineOrchestrator(MockEngine(), config={"db_path": str(db)})
    assert orch.db_path == str(db)
```

- [ ] **Step 3: Run tests to verify the first fails**

Run: `.venv/bin/python -m pytest tests/test_db_path.py -v`
Expected: `test_orchestrator_defaults_to_config_db_path` FAILS (db_path is `data/aeovis.db`); the second passes.

- [ ] **Step 4: Fix the orchestrator default**

In `aeo_eval/orchestrator.py`, add to the imports:

```python
from aeo_eval.config import config as app_config
```

Replace line 49 (`self.db_path = self.config.get("db_path", "data/aeovis.db")`) with:

```python
self.db_path = str(self.config.get("db_path") or app_config.general.output_db_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db_path.py -v`
Expected: 2 PASS

- [ ] **Step 6: Run the full suite to catch fallout**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: no new failures vs the pre-change baseline (run the suite once before starting if you don't have a baseline). If a test asserted the old `data/aeovis.db` default, update it to expect the configured path.

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_db_path.py aeo_eval/orchestrator.py
git commit -m "fix: single canonical DB path from config; isolate tests from real data dir"
```

---

### Task 2: Engine factory from the provider registry (E1)

`aeo_eval/config.py:13-17` already has a `PROVIDERS` registry (`name -> "module:Class"`), but `cli.py` and `dashboard/app.py` each hand-roll `get_engine` with if/elif chains, advertise engines that don't exist (gemini/grok/perplexity), and — the ★ bug — `cmd_run` passes a Pydantic `ProviderConfig` object as `config_dict`, so `ClaudeEngine.__init__`'s `self.config.get("api_key")` raises `AttributeError` on a real run.

**Files:**
- Create: `aeo_eval/engine/factory.py`
- Create: `tests/engine/test_factory.py`
- Modify: `aeo_eval/cli.py` (delete `get_engine`, use factory, `--engine` choices)
- Modify: `aeo_eval/dashboard/app.py` (delete `get_engine`, use factory, engine radio options)

**Interfaces:**
- Consumes: `PROVIDERS` and `config` from `aeo_eval.config`; engine classes' `__init__(config: Optional[dict])`.
- Produces: `create_engine(name: str, config_dict: Optional[dict] = None) -> BaseEngine` and `available_engines() -> List[str]` in `aeo_eval.engine.factory`. Tasks 9 and 12 import these.

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/test_factory.py`:

```python
"""Engine factory tests."""
import pytest

from aeo_eval.engine.factory import available_engines, create_engine
from aeo_eval.engine.mock_engine import MockEngine


def test_available_engines_only_lists_registered():
    engines = available_engines()
    assert "mock" in engines
    assert "claude" in engines
    assert "openai" in engines
    assert "gemini" not in engines  # config-only, no implementation
    assert "grok" not in engines


def test_create_engine_mock():
    assert isinstance(create_engine("mock"), MockEngine)


def test_create_engine_unknown_name():
    with pytest.raises(ValueError, match="Unknown engine 'grok'"):
        create_engine("grok")


def test_create_engine_hands_engines_a_plain_dict():
    # Regression: the CLI used to pass a ProviderConfig object, which
    # crashed ClaudeEngine with AttributeError on .get().
    engine = create_engine("claude", {"api_key": "test-key"})
    assert engine.config["api_key"] == "test-key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/engine/test_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aeo_eval.engine.factory'`

- [ ] **Step 3: Implement the factory**

Create `aeo_eval/engine/factory.py`:

```python
"""Engine construction from the provider registry."""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

from aeo_eval.config import PROVIDERS, config as app_config
from aeo_eval.engine.base import BaseEngine


def available_engines() -> List[str]:
    """Names of engines with a registered implementation."""
    return sorted(PROVIDERS)


def create_engine(name: str, config_dict: Optional[Dict[str, Any]] = None) -> BaseEngine:
    """Instantiate an engine by registry name.

    Args:
        name: Key in aeo_eval.config.PROVIDERS.
        config_dict: Engine configuration as a plain dict. Defaults to
            the matching provider section of the global config.

    Raises:
        ValueError: unknown name, or the engine rejects its config
            (e.g. a missing API key).
    """
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown engine '{name}'. Available: {', '.join(available_engines())}"
        )
    module_path, class_name = PROVIDERS[name].split(":")
    engine_cls = getattr(importlib.import_module(module_path), class_name)
    if config_dict is None:
        provider = app_config.providers.get(name)
        config_dict = provider.model_dump() if provider else {}
    return engine_cls(config_dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/engine/test_factory.py -v`
Expected: 4 PASS

- [ ] **Step 5: Rewire the CLI**

In `aeo_eval/cli.py`:
1. Delete the whole `get_engine` function (lines 29–74) and the now-unused imports of `BaseEngine` and `MockEngine`.
2. Add `from aeo_eval.engine.factory import available_engines, create_engine` to the imports.
3. In `cmd_run`, replace `engine = get_engine(args.engine, config.providers.get(args.engine))` with:

```python
    try:
        engine = create_engine(args.engine)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

4. In `main()`, change the run parser's engine argument to:

```python
    run_parser.add_argument(
        "--engine",
        choices=available_engines(),
        default="claude",
        help="AI engine to use",
    )
```

- [ ] **Step 6: Rewire the dashboard**

In `aeo_eval/dashboard/app.py`:
1. Delete the module's `get_engine` function (lines 20–36).
2. Add `from aeo_eval.engine.factory import available_engines, create_engine` to the imports.
3. In `run_evaluation`, replace `engine = get_engine(engine_name)` with `engine = create_engine(engine_name)`.
4. In `main()`, change the engine radio to `engine_choice = st.radio("Choose engine:", available_engines(), horizontal=True, help="Engines come from the provider registry")`.

- [ ] **Step 7: Verify CLI behavior and run the suite**

Run: `.venv/bin/python -m aeo_eval.cli run --engine gemini --limit 1; echo "exit=$?"`
Expected: argparse rejects `gemini` (invalid choice) with exit code 2.

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: no new failures.

- [ ] **Step 8: Commit**

```bash
git add aeo_eval/engine/factory.py tests/engine/test_factory.py aeo_eval/cli.py aeo_eval/dashboard/app.py
git commit -m "fix: drive engine construction from PROVIDERS registry; fixes ProviderConfig crash and phantom engine choices"
```

---

### Task 3: Persist every run result (A1)

`save_run()` is only called inside `Evaluator._extract_and_store_analysis` (`aeo_eval/runner/evaluator.py:221`), which only runs for successful responses — failed, timed-out, and rate-limited results are counted but never stored. Move persistence into `run_one` for every non-dry-run result.

**Files:**
- Create: `tests/test_run_persistence.py`
- Modify: `aeo_eval/runner/evaluator.py`

**Interfaces:**
- Consumes: `SQLiteStore(db_path)`, `.init_db()`, `.save_run(result)`, `.get_raw_responses_by_batch(batch_id)`; `create_engine` is NOT used here.
- Produces: `Evaluator.store: SQLiteStore` and `Evaluator.db_path: str` attributes constructed in `__init__` (Tasks 4 and 9 use `self.store`); `_save_result_best_effort(result)` helper.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_persistence.py`:

```python
"""Every engine result — including failures — must be persisted."""
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator, RunOptions
from aeo_eval.storage.sqlite_store import SQLiteStore


class FailingEngine(MockEngine):
    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.status = "failed"
        result.response_text = None
        result.error = "boom"
        return result


def make_prompt(pid="p1"):
    return Prompt(
        id=pid, prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_failed_result_is_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(FailingEngine(), {"db_path": db})
    evaluator.run_one(make_prompt())
    rows = SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"] == "boom"


def test_successful_result_is_persisted_exactly_once(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(MockEngine(), {"db_path": db})
    evaluator.run_one(make_prompt())
    rows = SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"


def test_dry_run_is_not_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(MockEngine(), {"db_path": db})
    evaluator.run_one(make_prompt(), RunOptions(dry_run=True))
    assert SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_run_persistence.py -v`
Expected: `test_failed_result_is_persisted` FAILS (0 rows). The success test may pass (analysis path saved it) — that's fine; the failure test is the driver.

- [ ] **Step 3: Implement**

In `aeo_eval/runner/evaluator.py`:

1. Add to imports: `from aeo_eval.config import config as app_config`.

2. In `Evaluator.__init__`, after `self.cost_tracker = ...`, add:

```python
        self.db_path = str(self.config.get("db_path") or app_config.general.output_db_path)
        self.store = SQLiteStore(self.db_path)
        self.store.init_db()
```

3. Add a helper method to `Evaluator`:

```python
    def _save_result_best_effort(self, result: RunResult) -> None:
        """Persist a result; storage failures must not fail the run."""
        try:
            self.store.save_run(result)
        except Exception as exc:
            logger.warning(
                f"Failed to persist result {result.run_id}: {type(exc).__name__}: {exc}"
            )
```

4. In `run_one`, in the non-dry-run branch, reorder so persistence happens for every result and before cost enforcement can raise:

```python
            else:
                # Run the engine
                result = self.engine.run(prompt.prompt)
                result.prompt_id = prompt.id
                result.run_batch_id = self.run_batch_id
                result.run_type = options.run_type
                result.engine_name = self.engine.__class__.__name__
                result.run_timestamp = self.run_timestamp

                # Persist EVERY outcome (success, failed, timeout,
                # rate_limited) before anything that can raise.
                self._save_result_best_effort(result)

                # Track actual cost (may raise CostLimitExceeded)
                if result.actual_cost is not None:
                    self.cost_tracker.add(prompt.id, result.actual_cost)

                # Extract analysis — best-effort, success only.
                if result.status == "success" and result.response_text:
                    self._extract_and_store_analysis(prompt, result)
```

5. In `run_one`'s generic `except Exception` handler, persist the synthetic failed result before returning it — assign the `RunResult(...)` to a variable `failed`, call `self._save_result_best_effort(failed)`, then `return failed`.

6. In `run_batch`'s `except CostLimitExceeded` handler, assign the synthetic `RunResult(...)` to `cost_limit_result`, call `self._save_result_best_effort(cost_limit_result)`, then `results.append(cost_limit_result)`.

7. In `_extract_and_store_analysis`, delete these three lines (the store now lives on `self` and the raw response is already saved):

```python
            store = SQLiteStore(self.config.get("db_path", "data/aeovis.db"))
            store.init_db()
            store.save_run(result)
```

and change `store.save_analysis(analysis_output)` to `self.store.save_analysis(analysis_output)`. Update the docstring sentence that mentions persisting the raw response.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_run_persistence.py -v`
Expected: 3 PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: no new failures. Watch `tests/test_runner.py` and `tests/integration/` — if any test constructed `Evaluator` expecting no DB writes, it now writes to the isolated tmp DB from Task 1's fixture, which is harmless; only assertions about *duplicate* saves would need updating (there should be exactly one row per result now).

- [ ] **Step 6: Commit**

```bash
git add tests/test_run_persistence.py aeo_eval/runner/evaluator.py
git commit -m "fix: persist all run results including failures, not just analyzed successes"
```

---

### Task 4: Write real evaluation_runs totals (A1b)

The `evaluation_runs` row is only created by `INSERT OR IGNORE` inside `save_run` with `num_prompts=1` and no cost, so the dashboard's Cost column always shows $0.00 and prompt counts are wrong. Upsert the real batch totals at the end of `run_batch`.

**Files:**
- Create: `tests/test_evaluation_run_totals.py`
- Modify: `aeo_eval/storage/sqlite_store.py`
- Modify: `aeo_eval/runner/evaluator.py` (`run_batch` end)

**Interfaces:**
- Consumes: `EvaluationRun` dataclass (`aeo_eval/models/result.py`), `Evaluator.store` from Task 3.
- Produces: `SQLiteStore.save_evaluation_run(run: EvaluationRun) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_evaluation_run_totals.py`:

```python
"""Batch totals must land in the evaluation_runs table."""
import sqlite3

import pytest

from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator


class CostedEngine(MockEngine):
    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.actual_cost = 0.02
        result.input_tokens = 100
        result.output_tokens = 200
        return result


def make_prompt(pid):
    return Prompt(
        id=pid, prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_evaluation_run_totals_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(CostedEngine(), {"db_path": db})
    evaluator.run_batch([make_prompt("p1"), make_prompt("p2")])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT num_prompts, cost, status, duration_seconds FROM evaluation_runs WHERE run_id = ?",
        (evaluator.run_batch_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 2
    assert row[1] == pytest.approx(0.04)
    assert row[2] == "completed"
    assert row[3] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_evaluation_run_totals.py -v`
Expected: FAIL — `num_prompts` is 1 (the IGNORE placeholder) and `cost` is 0.0.

- [ ] **Step 3: Implement `save_evaluation_run`**

In `aeo_eval/storage/sqlite_store.py`:

1. Change the models import to: `from aeo_eval.models.result import RunResult, EvaluationRun`.
2. Add the method to `SQLiteStore`:

```python
    def save_evaluation_run(self, run: EvaluationRun) -> None:
        """Upsert the batch-level summary row with real totals.

        save_run() creates a minimal placeholder row per batch via
        INSERT OR IGNORE; this overwrites it with the true totals once
        the batch finishes.
        """
        status = (
            "completed" if run.prompts_failed == 0
            else ("failed" if run.prompts_succeeded == 0 else "partial_failure")
        )
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO evaluation_runs
                (run_id, timestamp, engine, model, num_prompts, filters,
                 status, cost, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    num_prompts = excluded.num_prompts,
                    filters = excluded.filters,
                    status = excluded.status,
                    cost = excluded.cost,
                    duration_seconds = excluded.duration_seconds
                """,
                (
                    run.run_id,
                    run.run_timestamp.isoformat(),
                    run.engine,
                    run.model_version,
                    run.prompts_run,
                    json.dumps(run.filters_applied),
                    status,
                    run.total_cost,
                    int(run.duration_seconds),
                ),
            )
            conn.commit()
```

3. In `aeo_eval/runner/evaluator.py` `run_batch`, when constructing `EvaluationRun`, replace the implicit `duration_seconds=0.0` by adding this field to the constructor call:

```python
            duration_seconds=(datetime.now() - self.run_timestamp).total_seconds(),
```

4. Immediately after the `EvaluationRun` is constructed (before the final `logger.info`), add:

```python
        if not options.dry_run:
            try:
                self.store.save_evaluation_run(evaluation_run)
            except Exception as exc:
                logger.warning(
                    f"Failed to persist evaluation run summary: {type(exc).__name__}: {exc}"
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_evaluation_run_totals.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite, then commit**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: no new failures.

```bash
git add tests/test_evaluation_run_totals.py aeo_eval/storage/sqlite_store.py aeo_eval/runner/evaluator.py
git commit -m "fix: persist real batch totals to evaluation_runs (dashboard cost was always \$0)"
```

---

### Task 5: Citation history upsert + citation_occurrences (A3)

`save_citations` uses `INSERT OR REPLACE`, which mints a new id and resets `first_observed`/`occurrence_count` every run — destroying exactly the citation history the spec requires. And `citation_occurrences` (the run/response linkage table) is never written, which is why gaps and the dashboard can't scope citations to a run.

**Files:**
- Create: `tests/citations/test_citation_store.py`
- Modify: `aeo_eval/citations/deduplicator.py`
- Modify: `aeo_eval/storage/sqlite_store.py` (`save_citations`)

**Interfaces:**
- Consumes: schema tables `citations` (UNIQUE `normalized_url`) and `citation_occurrences` (FKs to `citations.id`, `response_analysis.id`).
- Produces: each dict from `CitationDeduplicator.process_citations_from_run` gains an `"occurrences": List[str]` key (response_analysis ids, one per appearance). `SQLiteStore.save_citations` upserts by `normalized_url` (preserving `id`/`first_observed`, accumulating `occurrence_count`) and inserts one `citation_occurrences` row per entry in `"occurrences"`. Tasks 6 and 13 query `citation_occurrences`.

- [ ] **Step 1: Write the failing tests**

Create `tests/citations/test_citation_store.py`:

```python
"""Citation persistence: history preserved across runs, occurrences written."""
import json
import sqlite3

from aeo_eval.citations.deduplicator import CitationDeduplicator
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_analysis(db, run_id, analysis_id, citations):
    """Insert the minimal rows an analysis needs (run -> response -> analysis)."""
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, 'p1', 'mock')",
        (rr_id, run_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, striim_recommended, citations) "
        "VALUES (?, ?, 1, 0, ?)",
        (analysis_id, rr_id, json.dumps(citations)),
    )
    conn.commit()
    conn.close()


def make_citation(**overrides):
    base = {
        "original_url": "https://ex.com/a?x=1",
        "normalized_url": "https://ex.com/a",
        "domain": "ex.com",
        "source_category": "other",
        "occurrence_count": 2,
        "first_observed": "2026-01-01T00:00:00",
        "last_observed": "2026-01-01T00:00:00",
        "occurrences": [],
    }
    base.update(overrides)
    return base


def test_upsert_preserves_first_observed_and_accumulates_count(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    store.save_citations([make_citation()])
    conn = sqlite3.connect(db)
    original_id = conn.execute("SELECT id FROM citations").fetchone()[0]
    conn.close()

    store.save_citations([make_citation(
        occurrence_count=3,
        first_observed="2026-02-01T00:00:00",
        last_observed="2026-02-01T00:00:00",
    )])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id, first_observed, last_observed, occurrence_count FROM citations"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    cid, first, last, count = rows[0]
    assert cid == original_id            # id survives
    assert first == "2026-01-01T00:00:00"  # history preserved
    assert last == "2026-02-01T00:00:00"
    assert count == 5                     # 2 + 3 accumulated


def test_occurrence_rows_written(tmp_path):
    db = str(tmp_path / "t.db")
    seed_analysis(db, "run-1", "an-1", ["https://ex.com/a"])
    store = SQLiteStore(db)
    store.save_citations([make_citation(occurrence_count=1, occurrences=["an-1"])])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT co.response_analysis_id, c.normalized_url "
        "FROM citation_occurrences co JOIN citations c ON co.citation_id = c.id"
    ).fetchall()
    conn.close()
    assert rows == [("an-1", "https://ex.com/a")]


def test_deduplicator_emits_occurrences(tmp_path):
    db = str(tmp_path / "t.db")
    seed_analysis(db, "run-1", "an-1", ["https://ex.com/a", "https://ex.com/a?utm=x"])
    seed_analysis(db, "run-1", "an-2", ["https://ex.com/a"])
    conn = sqlite3.connect(db)
    citations = CitationDeduplicator(conn).process_citations_from_run("run-1")
    conn.close()
    assert len(citations) == 1
    entry = citations[0]
    assert entry["occurrence_count"] == 3
    assert sorted(entry["occurrences"]) == ["an-1", "an-1", "an-2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/citations/test_citation_store.py -v`
Expected: all 3 FAIL (`occurrence_count == 3` not 5 / no occurrence rows / KeyError `occurrences`).

- [ ] **Step 3: Implement the deduplicator change**

Replace the body of `CitationDeduplicator.process_citations_from_run` in `aeo_eval/citations/deduplicator.py` with:

```python
        cursor = self.conn.execute(
            """
            SELECT ra.id, ra.citations
            FROM response_analysis ra
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            WHERE rr.run_id = ?
            """,
            (run_id,),
        )

        import json

        deduped: Dict[str, Dict] = {}
        for analysis_id, citations_json in cursor.fetchall():
            if not citations_json:
                continue
            citations = (
                json.loads(citations_json)
                if isinstance(citations_json, str)
                else citations_json
            )
            for url in citations:
                if not url:
                    continue
                normalized = normalize_url(url)
                entry = deduped.get(normalized)
                if entry is None:
                    domain = extract_domain(normalized)
                    deduped[normalized] = {
                        "original_url": url,
                        "normalized_url": normalized,
                        "domain": domain,
                        "source_category": classify_source(url, domain),
                        "occurrence_count": 1,
                        "first_observed": datetime.now().isoformat(),
                        "last_observed": datetime.now().isoformat(),
                        "occurrences": [analysis_id],
                    }
                else:
                    entry["occurrence_count"] += 1
                    entry["last_observed"] = datetime.now().isoformat()
                    entry["occurrences"].append(analysis_id)

        return list(deduped.values())
```

- [ ] **Step 4: Implement the store change**

Replace `SQLiteStore.save_citations` in `aeo_eval/storage/sqlite_store.py` with:

```python
    def save_citations(self, citations: List[Dict]) -> None:
        """Upsert deduplicated citations and record per-response occurrences.

        Upserting by normalized_url preserves the original row id and
        first_observed while accumulating occurrence_count, so citation
        history survives across runs (the old INSERT OR REPLACE wiped it).
        """
        import uuid

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for citation in citations:
                conn.execute(
                    """
                    INSERT INTO citations
                    (id, url, normalized_url, domain, source_category,
                     first_observed, last_observed, occurrence_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(normalized_url) DO UPDATE SET
                        last_observed = excluded.last_observed,
                        occurrence_count = citations.occurrence_count + excluded.occurrence_count
                    """,
                    (
                        str(uuid.uuid4()),
                        citation.get("original_url", ""),
                        citation["normalized_url"],
                        citation["domain"],
                        citation["source_category"],
                        citation["first_observed"],
                        citation["last_observed"],
                        citation["occurrence_count"],
                    ),
                )
                citation_id = conn.execute(
                    "SELECT id FROM citations WHERE normalized_url = ?",
                    (citation["normalized_url"],),
                ).fetchone()[0]
                for analysis_id in citation.get("occurrences", []):
                    conn.execute(
                        """
                        INSERT INTO citation_occurrences
                        (id, citation_id, response_analysis_id)
                        VALUES (?, ?, ?)
                        """,
                        (str(uuid.uuid4()), citation_id, analysis_id),
                    )
            conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass, then the full suite**

Run: `.venv/bin/python -m pytest tests/citations/ tests/ -v`
Expected: new tests PASS; no new failures elsewhere (`tests/integration/` exercises the orchestrator citation step — occurrences now also get written there, which existing assertions should tolerate).

- [ ] **Step 6: Commit**

```bash
git add tests/citations/test_citation_store.py aeo_eval/citations/deduplicator.py aeo_eval/storage/sqlite_store.py
git commit -m "fix: preserve citation history across runs and write citation_occurrences"
```

---

### Task 6: Run-scoped, topic-based citation gaps (A4)

`detect_citation_gaps` queries the entire `citations` table (all history, ignoring `run_id`) and compares Striim vs competitor counts *for the same domain* — impossible by construction, since a domain is classified as either `striim_owned` or `competitor`, never both. Rewrite it per the spec: within this run, per topic, flag when competitor pages are cited and Striim pages are not.

**Files:**
- Create: `tests/gaps/test_citation_gaps.py`
- Modify: `aeo_eval/gaps/detector.py` (`detect_citation_gaps`)

**Interfaces:**
- Consumes: `citation_occurrences` rows from Task 5; `prompts` table (topic per prompt_id).
- Produces: gap dicts with the same keys as before (`id, topic, gap_type="citation", striim_visibility, top_competitor_visibility, top_competitor_name, priority, confidence, evidence_ids, affected_prompts, run_id, created_timestamp`) — `RecommendationGenerator` consumes these unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/gaps/test_citation_gaps.py`:

```python
"""Citation gaps must be run-scoped and topic-based."""
import json
import sqlite3
import uuid

from aeo_eval.gaps.detector import GapDetector
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed(conn, run_id, topic, analysis_id, cited_domains):
    """Seed one analyzed response in `topic` citing `cited_domains`.

    cited_domains: list of (domain, source_category) tuples.
    """
    prompt_id = f"prompt-{topic}-{analysis_id}"
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO prompts (id, prompt_text, topic, persona, intent, priority) "
        "VALUES (?, 'q', ?, 'x', 'y', 'high')",
        (prompt_id, topic),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, ?, 'mock')",
        (rr_id, run_id, prompt_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, striim_recommended, citations) "
        "VALUES (?, ?, 1, 0, ?)",
        (analysis_id, rr_id, json.dumps([])),
    )
    for domain, category in cited_domains:
        url = f"https://{domain}/{uuid.uuid4().hex[:6]}"
        cit_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
            "first_observed, last_observed, occurrence_count) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)",
            (cit_id, url, url, domain, category),
        )
        conn.execute(
            "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
            "VALUES (?, ?, ?)",
            (str(uuid.uuid4()), cit_id, analysis_id),
        )
    conn.commit()


def make_db(tmp_path):
    db = str(tmp_path / "t.db")
    SQLiteStore(db).init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_flags_topic_with_competitor_citations_and_no_striim(tmp_path):
    conn = make_db(tmp_path)
    seed(conn, "run-1", "Oracle CDC", "an-1",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor")])
    gaps = GapDetector(conn).detect_citation_gaps("run-1")
    assert len(gaps) == 1
    assert gaps[0]["topic"] == "Oracle CDC"
    assert gaps[0]["gap_type"] == "citation"


def test_topic_with_striim_citation_not_flagged(tmp_path):
    conn = make_db(tmp_path)
    seed(conn, "run-1", "Oracle CDC", "an-1",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor"), ("striim.com", "striim_owned")])
    assert GapDetector(conn).detect_citation_gaps("run-1") == []


def test_other_runs_do_not_leak_in(tmp_path):
    conn = make_db(tmp_path)
    # 3 competitor citations, but in a DIFFERENT run
    seed(conn, "run-0", "Oracle CDC", "an-old",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor")])
    seed(conn, "run-1", "Oracle CDC", "an-new", [("fivetran.com", "competitor")])
    assert GapDetector(conn).detect_citation_gaps("run-1") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/gaps/test_citation_gaps.py -v`
Expected: FAIL (old implementation flags per-domain across all history: wrong topic values, run leakage).

- [ ] **Step 3: Rewrite `detect_citation_gaps`**

Replace the whole method in `aeo_eval/gaps/detector.py` with:

```python
    def detect_citation_gaps(self, run_id: str) -> List[Dict]:
        """Detect topics where competitor pages are cited but Striim pages are not.

        Run-scoped: only citations observed in this run (via
        citation_occurrences) are considered. A gap fires when a topic
        has >= 3 competitor-owned citations and zero Striim-owned ones.
        """
        cursor = self.conn.execute(
            """
            SELECT p.topic,
                   SUM(CASE WHEN c.source_category = 'competitor' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.source_category = 'striim_owned' THEN 1 ELSE 0 END)
            FROM citation_occurrences co
            JOIN citations c ON co.citation_id = c.id
            JOIN response_analysis ra ON co.response_analysis_id = ra.id
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            JOIN prompts p ON rr.prompt_id = p.id
            WHERE rr.run_id = ?
            GROUP BY p.topic
            """,
            (run_id,),
        )

        gaps = []
        for topic, competitor_citations, striim_citations in cursor.fetchall():
            if striim_citations == 0 and competitor_citations >= 3:
                gaps.append({
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "gap_type": "citation",
                    "striim_visibility": 0.0,
                    "top_competitor_visibility": float(competitor_citations),
                    "top_competitor_name": "Competitor",
                    "priority": "high" if competitor_citations > 5 else "medium",
                    "confidence": "high" if competitor_citations > 5 else "medium",
                    "evidence_ids": [f"citations-{run_id}-{topic}"],
                    "affected_prompts": [],
                    "run_id": run_id,
                    "created_timestamp": datetime.now().isoformat(),
                })
        return gaps
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `.venv/bin/python -m pytest tests/gaps/ tests/ -v`
Expected: new tests PASS. If `tests/gaps/test_detector.py` has citation-gap tests asserting the old per-domain behavior, rewrite those assertions to the new topic-based rule (same thresholds: ≥3 flags, >5 → high).

- [ ] **Step 5: Commit**

```bash
git add tests/gaps/test_citation_gaps.py tests/gaps/test_detector.py aeo_eval/gaps/detector.py
git commit -m "fix: citation gaps are run-scoped and topic-based per spec"
```

---

### Task 7: Real topic priorities for visibility thresholds (A5)

`detect_visibility_gaps` hardcodes `"Medium"` at `aeo_eval/gaps/detector.py:60`, so the spec's High (15%) / Low (2%) thresholds never apply. Also `question.json` stores priorities lowercase (`"high"`) while `VISIBILITY_THRESHOLDS` keys are capitalized (`"High"`) — normalize.

**Files:**
- Create: `tests/gaps/test_topic_priority.py`
- Modify: `aeo_eval/gaps/thresholds.py`
- Modify: `aeo_eval/gaps/detector.py` (`detect_visibility_gaps` + new helper)

**Interfaces:**
- Consumes: `prompts` table (persisted by `orchestrator` via `save_prompts`); `visibility_metrics` rows.
- Produces: `GapDetector._topic_priority(topic: str) -> str`; `should_flag_visibility_gap` accepts any case.

- [ ] **Step 1: Write the failing tests**

Create `tests/gaps/test_topic_priority.py`:

```python
"""Visibility gap thresholds must use the topic's real priority, any case."""
import sqlite3

from aeo_eval.gaps.detector import GapDetector
from aeo_eval.gaps.thresholds import should_flag_visibility_gap
from aeo_eval.storage.sqlite_store import SQLiteStore


def test_thresholds_are_case_insensitive():
    # 12% is below the High threshold (15%) but above Medium (5%)
    assert should_flag_visibility_gap(0.12, 0.0, "high") is True
    assert should_flag_visibility_gap(0.12, 0.0, "High") is True
    assert should_flag_visibility_gap(0.12, 0.0, "medium") is False


def seed_topic_metrics(db, run_id, topic, priority, mention_rate):
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO prompts (id, prompt_text, topic, persona, intent, priority) "
        "VALUES (?, 'q', ?, 'x', 'y', ?)",
        (f"p-{topic}", topic, priority),
    )
    conn.commit()
    conn.close()
    store.save_metrics(run_id, {
        "dimension": "by_topic", "dimension_value": topic,
        "mention_rate": mention_rate, "competitor_mention_rates": {},
        "num_responses": 12,
    })


def test_high_priority_topic_uses_high_threshold(tmp_path):
    db = str(tmp_path / "t.db")
    seed_topic_metrics(db, "run-1", "Oracle CDC", "high", 0.12)
    conn = sqlite3.connect(db)
    gaps = GapDetector(conn).detect_visibility_gaps("run-1")
    conn.close()
    assert len(gaps) == 1  # 12% < 15% High threshold


def test_medium_priority_topic_uses_medium_threshold(tmp_path):
    db = str(tmp_path / "t.db")
    seed_topic_metrics(db, "run-1", "Data Replication", "medium", 0.12)
    conn = sqlite3.connect(db)
    gaps = GapDetector(conn).detect_visibility_gaps("run-1")
    conn.close()
    assert gaps == []  # 12% > 5% Medium threshold, no competitor pressure
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/gaps/test_topic_priority.py -v`
Expected: `test_thresholds_are_case_insensitive` FAILS on `"high"` (falls to default 0.05); `test_high_priority_topic_uses_high_threshold` FAILS (hardcoded Medium → no gap).

- [ ] **Step 3: Implement**

In `aeo_eval/gaps/thresholds.py`, at the top of `should_flag_visibility_gap`, before the threshold lookup:

```python
    normalized_priority = (topic_priority or "Medium").strip().capitalize()
    threshold = VISIBILITY_THRESHOLDS.get(normalized_priority, 0.05)
```

(remove the old `threshold = VISIBILITY_THRESHOLDS.get(topic_priority, 0.05)` line; also loosen the parameter annotation to `str` since inputs may be any case).

In `aeo_eval/gaps/detector.py`, add a helper to `GapDetector`:

```python
    def _topic_priority(self, topic: str) -> str:
        """Highest priority among the topic's prompts; Medium if unknown."""
        row = self.conn.execute(
            """
            SELECT priority FROM prompts
            WHERE topic = ? AND priority IS NOT NULL
            ORDER BY CASE LOWER(priority)
                WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT 1
            """,
            (topic,),
        ).fetchone()
        return row[0] if row else "Medium"
```

and in `detect_visibility_gaps`, replace

```python
            if should_flag_visibility_gap(striim_rate, top_competitor_rate, "Medium"):
```

with

```python
            if should_flag_visibility_gap(
                striim_rate, top_competitor_rate, self._topic_priority(topic)
            ):
```

- [ ] **Step 4: Run tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/gaps/ tests/ -v`
Expected: new tests PASS; adjust any existing detector test that relied on the hardcoded Medium threshold (seed a `prompts` row with the priority the test intends, since topics without prompt rows still default to Medium).

- [ ] **Step 5: Commit**

```bash
git add tests/gaps/test_topic_priority.py aeo_eval/gaps/thresholds.py aeo_eval/gaps/detector.py
git commit -m "fix: visibility gap thresholds use real topic priority, case-insensitive"
```

---

### Task 8: Real structured output + usage accounting in engines (B1 + B2 transport)

`ClaudeEngine.run_with_structured_output` ignores the schema entirely (prompt-and-pray JSON). The Claude API supports schema-enforced structured outputs via `output_config={"format": {"type": "json_schema", "schema": ...}}` — the analog of what `OpenAIEngine` already does. Additionally: ★ both Claude calls pass `temperature=0`, which the API **rejects with a 400 on `claude-opus-5`** (sampling params were removed on Opus 4.7+) — remove it; structured calls bypass the rate limiter and report no usage — fix both; the extraction schema lacks `additionalProperties: false` and complete `required` lists (needed by both providers' strict modes) and uses unsupported `minimum`/`maximum` constraints — fix; `openai` is missing from `pyproject.toml`; `anthropic>=0.28.0` predates `output_config`.

**Files:**
- Modify: `aeo_eval/models/analysis.py` (add `StructuredCallResult`)
- Modify: `aeo_eval/engine/base.py` (annotation + docstring of `run_with_structured_output`)
- Modify: `aeo_eval/engine/claude_engine.py`
- Modify: `aeo_eval/engine/openai_engine.py`
- Modify: `aeo_eval/analysis/llm_extractor.py` (module-level `EXTRACTION_SCHEMA`, tuple return)
- Modify: `aeo_eval/analysis/extractor.py` (propagate `analysis_cost`)
- Modify: `pyproject.toml` (bump `anthropic`, add `openai`)
- Create: `tests/engine/test_structured_output.py`

**Interfaces:**
- Consumes: `BaseEngine.estimate_cost`, `get_rate_limiter()`.
- Produces:
  - `StructuredCallResult` dataclass in `aeo_eval.models.analysis`: fields `data: Dict[str, Any]`, `input_tokens: int = 0`, `output_tokens: int = 0`, `cost: float = 0.0`.
  - `BaseEngine.run_with_structured_output(prompt_text, schema) -> StructuredCallResult` (all engines).
  - `extract_with_claude(engine, response_text, competitors) -> Tuple[Optional[LLMExtractionOutput], float]` (output, cost).
  - `extract_response(...)` return dict gains key `"analysis_cost": float`. Task 9 consumes it.

- [ ] **Step 1: Upgrade dependencies**

```bash
.venv/bin/pip install -U anthropic openai
.venv/bin/python -c "import anthropic, openai; print(anthropic.__version__, openai.__version__)"
```

Edit `pyproject.toml` dependencies: change `"anthropic>=0.28.0"` to `"anthropic>=<the printed version>"` and add `"openai>=<the printed version>"` (openai was missing entirely — `openai_engine.py` imports it).

- [ ] **Step 2: Write the failing tests**

Create `tests/engine/test_structured_output.py`:

```python
"""Structured output must be schema-enforced, rate-limited, and report usage."""
import json
from unittest.mock import MagicMock

from aeo_eval.engine.claude_engine import ClaudeEngine
from aeo_eval.models.analysis import StructuredCallResult

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"x": {"type": "integer"}}, "required": ["x"]}


def make_engine():
    engine = ClaudeEngine({"api_key": "test-key"})
    engine.client = MagicMock()
    text_block = MagicMock()
    text_block.text = json.dumps({"x": 2})
    message = MagicMock()
    message.content = [text_block]
    message.usage.input_tokens = 500
    message.usage.output_tokens = 100
    engine.client.messages.create.return_value = message
    return engine


def test_claude_structured_call_uses_output_config_and_no_temperature():
    engine = make_engine()
    engine.run_with_structured_output("analyze this", SCHEMA)
    kwargs = engine.client.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA}
    }
    assert "temperature" not in kwargs


def test_claude_run_does_not_send_temperature():
    engine = make_engine()
    engine.run("hello")
    kwargs = engine.client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs


def test_structured_call_returns_usage_and_cost():
    engine = make_engine()
    result = engine.run_with_structured_output("analyze this", SCHEMA)
    assert isinstance(result, StructuredCallResult)
    assert result.data == {"x": 2}
    assert result.input_tokens == 500
    assert result.output_tokens == 100
    # 500/1000 * 0.003 + 100/1000 * 0.015 = 0.0015 + 0.0015
    assert abs(result.cost - 0.003) < 1e-9
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/engine/test_structured_output.py -v`
Expected: FAIL (`ImportError: StructuredCallResult`, then no `output_config` kwarg, `temperature` present).

- [ ] **Step 4: Add `StructuredCallResult`**

In `aeo_eval/models/analysis.py`, extend imports to `from typing import Any, Dict, List, Literal, Optional` and add:

```python
@dataclass
class StructuredCallResult:
    """Parsed structured-output call plus its token usage and cost."""
    data: Dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
```

- [ ] **Step 5: Update the engines**

`aeo_eval/engine/claude_engine.py`:
1. Add `from aeo_eval.models.analysis import StructuredCallResult` to imports.
2. In `run()`, delete the line `temperature=0,  # For consistency` from `_call_claude` (the API rejects sampling params on claude-opus-5).
3. Replace `run_with_structured_output` entirely with:

```python
    def run_with_structured_output(
        self,
        prompt_text: str,
        schema: Dict[str, Any],
    ) -> StructuredCallResult:
        """Run a prompt with schema-enforced structured output.

        Uses the Messages API's output_config.format (json_schema), so
        the response text is guaranteed to be valid JSON matching the
        schema. Used by Module 3 (Response Analysis).
        """
        logger.debug("Running Claude with structured output schema")

        self._rate_limiter_instance.wait_for_tokens(
            prompt_tokens=100, completion_tokens=1000
        )

        def _call_claude_structured():
            return self.client.messages.create(
                model=self.model_name,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt_text}],
                output_config={
                    "format": {"type": "json_schema", "schema": schema}
                },
                timeout=self.timeout,
            )

        message = self._retry_manager.retry(_call_claude_structured)
        response_text = message.content[0].text if message.content else ""
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse structured response as JSON: {response_text}")
            data = {"raw_response": response_text}

        return StructuredCallResult(
            data=data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=self.estimate_cost(input_tokens, output_tokens),
        )
```

`aeo_eval/engine/openai_engine.py` — same treatment (keep `temperature=0` in `run()`; gpt-4o accepts it):
1. Add `from aeo_eval.models.analysis import StructuredCallResult` to imports.
2. Replace `run_with_structured_output` with:

```python
    def run_with_structured_output(
        self,
        prompt_text: str,
        schema: Dict[str, Any],
    ) -> StructuredCallResult:
        """Run a prompt with OpenAI strict JSON-schema output."""
        logger.debug("Running OpenAI with structured output schema")

        self._rate_limiter_instance.wait_for_tokens(
            prompt_tokens=100, completion_tokens=1000
        )

        def _call_openai_structured():
            return self.client.chat.completions.create(
                model=self.model_name,
                max_tokens=2000,
                temperature=0,
                messages=[{"role": "user", "content": prompt_text}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "schema": schema,
                        "strict": True,
                    },
                },
                timeout=self.timeout,
            )

        response = self._retry_manager.retry(_call_openai_structured)
        response_text = response.choices[0].message.content if response.choices else ""
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse structured response as JSON: {response_text}")
            data = {"raw_response": response_text}

        return StructuredCallResult(
            data=data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=self.estimate_cost(input_tokens, output_tokens),
        )
```

`aeo_eval/engine/base.py`: change `run_with_structured_output`'s return annotation from `Dict[str, Any]` to `"StructuredCallResult"` and its docstring's Returns line to `Parsed output plus token usage and cost.` (add `from aeo_eval.models.analysis import StructuredCallResult` under `if TYPE_CHECKING:` or as a plain import — a plain import is fine, there is no cycle).

- [ ] **Step 6: Fix the extraction schema and plumb the tuple return**

In `aeo_eval/analysis/llm_extractor.py`:

1. Hoist the schema out of `extract_with_claude` into a module-level constant, strict-mode compliant (every object gets `additionalProperties: False`; every property listed in `required`; numeric `minimum`/`maximum` removed — structured outputs don't support them, ranges are enforced by the prompt text instead):

```python
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "striim_position": {"type": ["integer", "null"]},
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "position": {"type": ["integer", "null"]},
                    "is_recommended": {"type": "boolean"},
                },
                "required": ["name", "position", "is_recommended"],
            },
        },
        "striim_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "sentiment": {"enum": ["positive", "neutral", "negative"]},
                    "confidence": {"type": "number"},
                    "supporting_citation_url": {"type": ["string", "null"]},
                },
                "required": ["text", "sentiment", "confidence", "supporting_citation_url"],
            },
        },
        "general_sentiment_toward_striim": {"enum": ["positive", "neutral", "negative"]},
        "extraction_confidence": {"type": "number"},
        "flagged_for_review": {"type": "boolean"},
    },
    "required": [
        "striim_position",
        "competitors",
        "striim_claims",
        "general_sentiment_toward_striim",
        "extraction_confidence",
        "flagged_for_review",
    ],
}
```

2. Change `extract_with_claude` to return `Tuple[Optional[LLMExtractionOutput], float]` (add `Tuple` to the typing import). Replace the schema literal with `EXTRACTION_SCHEMA`, and inside the `try`:

```python
    try:
        call = engine.run_with_structured_output(prompt, EXTRACTION_SCHEMA)
        result = call.data
```

Keep the existing conversion code operating on `result`, and change the final returns to:

```python
        return (
            LLMExtractionOutput(
                striim_position=result.get("striim_position"),
                competitors=competitors_list,
                striim_claims=claims_list,
                general_sentiment_toward_striim=result.get(
                    "general_sentiment_toward_striim", "neutral"
                ),
                extraction_confidence=result.get("extraction_confidence", 0.5),
                flagged_for_review=result.get("flagged_for_review", False),
            ),
            call.cost,
        )
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None, 0.0
```

3. In `aeo_eval/analysis/extractor.py`'s `extract_response`, change the call site to:

```python
    llm_output, analysis_cost = extract_with_claude(engine, response_text, competitors)
```

Add `"analysis_cost": 0.0` to the fallback dict (the `llm_output is None` branch) and `"analysis_cost": analysis_cost` to the success dict.

- [ ] **Step 7: Run tests, fix stale assertions, run the suite**

Run: `.venv/bin/python -m pytest tests/engine/test_structured_output.py tests/ -v`
Expected: new tests PASS. Known fallout to fix:
- `tests/test_claude_engine.py`: delete/adjust any assertion that `messages.create` was called with `temperature=0`.
- `tests/analysis/test_llm_extractor.py`: fake engines returning plain dicts must now return `StructuredCallResult(data=<old dict>)`, and call sites unpack `output, cost = extract_with_claude(...)`.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml aeo_eval/models/analysis.py aeo_eval/engine/ aeo_eval/analysis/ tests/engine/test_structured_output.py tests/test_claude_engine.py tests/analysis/test_llm_extractor.py
git commit -m "fix: schema-enforced structured output with usage reporting; drop temperature on Claude (400s on opus-5)"
```

---

### Task 9: Dedicated analyzer engine + analysis cost tracking (B2)

Analysis extraction currently runs on whatever engine is under test, and its spend is invisible to the `$35` `CostTracker`. Per the approved design: the analyzer defaults to Claude (configurable via the pipeline config key `analysis_provider`), falls back to the engine under test when Claude isn't constructible (no API key), and its cost is added to the tracker.

**Files:**
- Create: `tests/test_analyzer_engine.py`
- Modify: `aeo_eval/runner/evaluator.py`

**Interfaces:**
- Consumes: `create_engine` from Task 2; `analysis_cost` key from Task 8; `Evaluator.store` from Task 3.
- Produces: `Evaluator.analyzer_engine: BaseEngine` attribute; pipeline config key `"analysis_provider"` (default `"claude"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analyzer_engine.py`:

```python
"""Analyzer engine selection and analysis-cost accounting."""
import pytest

from aeo_eval.config import config as app_config
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator

VALID_EXTRACTION = {
    "striim_position": 1,
    "competitors": [],
    "striim_claims": [],
    "general_sentiment_toward_striim": "neutral",
    "extraction_confidence": 0.9,
    "flagged_for_review": False,
}


class AnalyzingMockEngine(MockEngine):
    """Mock engine that also supports structured output with a fixed cost."""

    def run_with_structured_output(self, prompt_text, schema):
        return StructuredCallResult(
            data=dict(VALID_EXTRACTION), input_tokens=400, output_tokens=150, cost=0.005
        )


def make_prompt():
    return Prompt(
        id="p1", prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_analyzer_falls_back_to_engine_when_claude_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(app_config.providers["claude"], "api_key", None)
    engine = MockEngine()
    evaluator = Evaluator(engine, {"db_path": str(tmp_path / "t.db")})
    assert evaluator.analyzer_engine is engine


def test_analyzer_same_provider_reuses_engine(tmp_path):
    engine = MockEngine()
    evaluator = Evaluator(
        engine, {"db_path": str(tmp_path / "t.db"), "analysis_provider": "mock"}
    )
    assert evaluator.analyzer_engine is engine


def test_analysis_cost_is_tracked(tmp_path):
    engine = AnalyzingMockEngine()
    evaluator = Evaluator(
        engine, {"db_path": str(tmp_path / "t.db"), "analysis_provider": "mock"}
    )
    evaluator.run_one(make_prompt())
    # MockEngine sets no actual_cost, so all tracked spend is analysis spend.
    assert evaluator.cost_tracker.spent == pytest.approx(0.005)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_analyzer_engine.py -v`
Expected: FAIL (`AttributeError: 'Evaluator' object has no attribute 'analyzer_engine'`; spent == 0.0).

- [ ] **Step 3: Implement**

In `aeo_eval/runner/evaluator.py`:

1. Add to imports: `from aeo_eval.engine.factory import create_engine`.

2. In `Evaluator.__init__`, after the store setup from Task 3, add:

```python
        # Module 3 analysis runs on a dedicated analyzer engine (Claude
        # by default, configurable via "analysis_provider"), falling
        # back to the engine under test when it can't be constructed
        # (e.g. no API key).
        analyzer_name = self.config.get("analysis_provider", "claude")
        if engine.name == analyzer_name:
            self.analyzer_engine: BaseEngine = engine
        else:
            try:
                self.analyzer_engine = create_engine(analyzer_name)
            except Exception as exc:
                logger.warning(
                    f"Analyzer engine '{analyzer_name}' unavailable "
                    f"({type(exc).__name__}: {exc}); falling back to "
                    f"'{engine.name}' for analysis."
                )
                self.analyzer_engine = engine
```

3. In `_extract_and_store_analysis`, change the extraction call to use the analyzer and track its cost:

```python
            analysis = extract_response(
                response_text=result.response_text,
                engine=self.analyzer_engine,
                competitors=DEFAULT_COMPETITORS,
            )
            result.analysis = analysis

            analysis_cost = analysis.get("analysis_cost", 0.0)
            if analysis_cost:
                try:
                    self.cost_tracker.add(f"{prompt.id}:analysis", analysis_cost)
                except CostLimitExceeded:
                    logger.warning(
                        "Cost limit reached (including analysis spend); "
                        "remaining prompts will not run."
                    )
```

(The `CostLimitExceeded` catch is deliberate: `CostTracker.add` records the spend *before* raising, so the budget stays accurate, the current prompt's already-received result is kept, and the next `run_one` budget check stops the batch.)

- [ ] **Step 4: Run tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_analyzer_engine.py tests/ -v`
Expected: new tests PASS; no new failures. Note: with a real `ANTHROPIC_API_KEY` in the developer's env, mock-engine tests would construct a real ClaudeEngine as analyzer (no API call happens — MockEngine responses go through `extract_with_claude` against the analyzer, which WOULD call the API). To keep the suite offline, also add to `tests/conftest.py`'s fixture (same function, after the DB line):

```python
    monkeypatch.setattr(app_config.providers["claude"], "api_key", None, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
```

with the matching import moved to the top of the fixture. This forces the fallback path for every test that doesn't explicitly configure an analyzer.

- [ ] **Step 5: Commit**

```bash
git add tests/test_analyzer_engine.py tests/conftest.py aeo_eval/runner/evaluator.py
git commit -m "feat: dedicated analyzer engine with fallback; analysis LLM spend counted against cost limit"
```

---

### Task 10: Real recommendation_rate (C1)

`MetricsCalculator` sets `recommendation_rate = mention_rate` in both the overall and by-topic paths, even though `response_analysis.striim_recommended` is stored per response.

**Files:**
- Create: `tests/metrics/test_rates.py`
- Modify: `aeo_eval/metrics/calculator.py`

**Interfaces:**
- Consumes: `response_analysis.striim_recommended` column.
- Produces: metrics dicts where `"recommendation_rate"` = recommended responses / total responses (both dimensions).

- [ ] **Step 1: Write the failing test**

Create `tests/metrics/test_rates.py` (Task 11 adds more tests to this same file):

```python
"""Metric rates must come from stored data, not approximations."""
import json
import sqlite3

from aeo_eval.metrics.calculator import MetricsCalculator
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_response(conn, run_id, analysis_id, *, topic="Oracle CDC",
                  mentioned=1, recommended=0, citations=None):
    prompt_id = f"p-{topic}"
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO prompts (id, prompt_text, topic, persona, intent, priority) "
        "VALUES (?, 'q', ?, 'x', 'y', 'high')",
        (prompt_id, topic),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, ?, 'mock')",
        (rr_id, run_id, prompt_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, "
        "striim_recommended, citations, brands_found) VALUES (?, ?, ?, ?, ?, '[]')",
        (analysis_id, rr_id, mentioned, recommended, json.dumps(citations or [])),
    )
    conn.commit()


def make_conn(tmp_path):
    db = str(tmp_path / "t.db")
    SQLiteStore(db).init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_recommendation_rate_uses_stored_flag(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", mentioned=1, recommended=1)
    seed_response(conn, "run-1", "an-2", mentioned=1, recommended=0)
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["mention_rate"] == 1.0
    assert metrics["recommendation_rate"] == 0.5


def test_by_topic_recommendation_rate(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", recommended=1)
    seed_response(conn, "run-1", "an-2", recommended=0)
    by_topic = MetricsCalculator(conn).calculate_metrics_by_topic("run-1")
    assert by_topic[0]["recommendation_rate"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/metrics/test_rates.py -v`
Expected: FAIL — recommendation_rate equals 1.0 (the mention rate).

- [ ] **Step 3: Implement**

In `aeo_eval/metrics/calculator.py`:

1. `calculate_metrics_for_run`: add `ra.striim_recommended,` to the SELECT column list (after `ra.striim_mentioned,`); update the tuple unpack to `mentioned, recommended, position, brands_json, citations_json, prompt_id = row`; add a counter `striim_recommendations = 0` and inside the loop `if recommended: striim_recommendations += 1`; replace `"recommendation_rate": mention_rate,  # Rough approximation...` with:

```python
            "recommendation_rate": striim_recommendations / total_responses if total_responses > 0 else 0.0,
```

2. `calculate_metrics_by_topic`: add `ra.striim_recommended,` to the per-topic SELECT (make it the second column, after `ra.striim_mentioned`), so rows are `(mentioned, recommended, position, citations, brands_found)` — update the index-based accesses accordingly (`r[1]` becomes `recommended`, positions move to `r[2]`, citations to `r[3]`, brands to `r[4]`). Compute `striim_recommendations = sum(1 for r in rows if r[1])` and set:

```python
                "recommendation_rate": striim_recommendations / total if total > 0 else 0.0,
```

- [ ] **Step 4: Run tests, then the full suite; commit**

Run: `.venv/bin/python -m pytest tests/metrics/ tests/ -v`
Expected: PASS; update any assertion in `tests/metrics/test_calculator.py` that encoded `recommendation_rate == mention_rate`.

```bash
git add tests/metrics/test_rates.py tests/metrics/test_calculator.py aeo_eval/metrics/calculator.py
git commit -m "fix: recommendation_rate computed from stored striim_recommended flag"
```

---

### Task 11: Meaningful citation_rate (C2)

`citation_rate` currently counts total citations per response (can exceed 100%) and the by-topic value is hardcoded `0.0`. Redefine as **share of responses that cite at least one Striim-owned page** — that's what the `striim_citation_rate` column and the spec's "Striim citation rate: 7%" example mean — computed identically in both dimensions.

**Files:**
- Modify: `tests/metrics/test_rates.py` (append tests)
- Modify: `aeo_eval/metrics/calculator.py`

**Interfaces:**
- Consumes: `response_analysis.citations` JSON column (list of URL strings).
- Produces: module-level helper `has_striim_citation(citations_json) -> bool` in `aeo_eval/metrics/calculator.py`; `"citation_rate"` semantics change in both metric dicts.

- [ ] **Step 1: Append the failing tests**

Add to `tests/metrics/test_rates.py`:

```python
def test_citation_rate_is_share_of_responses_citing_striim(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1",
                  citations=["https://www.striim.com/docs/", "https://ex.com/a"])
    seed_response(conn, "run-1", "an-2", citations=["https://ex.com/b"])
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["citation_rate"] == 0.5


def test_citation_rate_cannot_exceed_one(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", citations=[
        "https://www.striim.com/a", "https://www.striim.com/b",
        "https://www.striim.com/c",
    ])
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["citation_rate"] == 1.0


def test_by_topic_citation_rate_not_hardcoded_zero(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", citations=["https://www.striim.com/x"])
    by_topic = MetricsCalculator(conn).calculate_metrics_by_topic("run-1")
    assert by_topic[0]["citation_rate"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/metrics/test_rates.py -v`
Expected: the three new tests FAIL (rate counts citations; by-topic is 0.0).

- [ ] **Step 3: Implement**

In `aeo_eval/metrics/calculator.py`, add a module-level helper:

```python
def has_striim_citation(citations_json) -> bool:
    """True when the response's citation list includes a striim.com URL."""
    if not citations_json:
        return False
    citations = (
        json.loads(citations_json)
        if isinstance(citations_json, str)
        else citations_json
    )
    return any(
        isinstance(url, str) and "striim.com" in url.lower()
        for url in citations
    )
```

In `calculate_metrics_for_run`: replace the `citation_counts` counter with `striim_citing_responses = 0` and inside the loop replace the citations block with:

```python
            if has_striim_citation(citations_json):
                striim_citing_responses += 1
```

and set `citation_rate = striim_citing_responses / total_responses if total_responses > 0 else 0.0`.

In `calculate_metrics_by_topic`: with the column order from Task 10 (`mentioned, recommended, position, citations, brands_found`), compute `striim_citing = sum(1 for r in rows if has_striim_citation(r[3]))` and replace `"citation_rate": 0.0,  # Would need...` with:

```python
                "citation_rate": striim_citing / total if total > 0 else 0.0,
```

- [ ] **Step 4: Run tests, then the full suite; commit**

Run: `.venv/bin/python -m pytest tests/metrics/ tests/ -v`
Expected: PASS (fix any `test_calculator.py` assertion that expected the old citations-per-response semantics).

```bash
git add tests/metrics/test_rates.py tests/metrics/test_calculator.py aeo_eval/metrics/calculator.py
git commit -m "fix: citation_rate = share of responses citing a Striim page; by-topic no longer hardcoded 0"
```

---

### Task 12: Dashboard run controls + run_type literal (D1 + D3)

Three dashboard defects: `run_evaluation` calls `p.get('topic')` on `Prompt` dataclasses (crashes the moment a topic is selected); the topic dropdown lists topics that don't exist in `question.json`; `run_type="dashboard"` violates the `Literal["manual", "scheduled"]` contract. Also make the module read the DB path at call time (needed for testability and by Task 13).

**Files:**
- Create: `tests/dashboard/test_select_prompts.py`
- Modify: `aeo_eval/models/result.py` (both `run_type` Literals)
- Modify: `aeo_eval/runner/evaluator.py` (`RunOptions.run_type` + `Evaluator.run_type` Literals)
- Modify: `aeo_eval/dashboard/app.py`

**Interfaces:**
- Consumes: `load_prompts`, `Prompt` dataclass attributes (`.topic`, `.priority`).
- Produces: `select_prompts(prompts, topic=None, priority=None, limit=None) -> list` and `_db_path() -> str` in `aeo_eval.dashboard.app`; widened `Literal["manual", "scheduled", "dashboard"]` everywhere `run_type` is typed.

- [ ] **Step 1: Write the failing tests**

Create `tests/dashboard/test_select_prompts.py`:

```python
"""Dashboard prompt selection: attribute access, filter-then-limit."""
from aeo_eval.dashboard.app import select_prompts
from aeo_eval.models.prompt import Prompt


def make_prompts():
    return [
        Prompt(id=f"p{i}", prompt="q", topic=topic, persona="x",
               intent="y", priority=priority)
        for i, (topic, priority) in enumerate([
            ("Oracle CDC", "high"),
            ("Oracle CDC", "medium"),
            ("Data Replication", "high"),
            ("Data Replication", "low"),
        ])
    ]


def test_topic_filter_uses_dataclass_attributes():
    selected = select_prompts(make_prompts(), topic="Oracle CDC")
    assert [p.id for p in selected] == ["p0", "p1"]


def test_priority_filter():
    selected = select_prompts(make_prompts(), priority="high")
    assert [p.id for p in selected] == ["p0", "p2"]


def test_limit_applies_after_filtering():
    selected = select_prompts(make_prompts(), topic="Data Replication", limit=1)
    assert [p.id for p in selected] == ["p2"]


def test_no_filters_returns_all():
    assert len(select_prompts(make_prompts())) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/dashboard/test_select_prompts.py -v`
Expected: FAIL with `ImportError: cannot import name 'select_prompts'`.

- [ ] **Step 3: Widen the run_type Literals**

- `aeo_eval/models/result.py`: change both occurrences of `Literal["manual", "scheduled"]` (in `RunResult` and `EvaluationRun`) to `Literal["manual", "scheduled", "dashboard"]`.
- `aeo_eval/runner/evaluator.py`: same change in `RunOptions.run_type` and the `Evaluator.run_type` attribute annotation in `__init__`.

- [ ] **Step 4: Fix the dashboard module**

In `aeo_eval/dashboard/app.py`:

1. Replace the module-level `DB_PATH = config.general.output_db_path` with:

```python
def _db_path() -> str:
    """Resolve the DB path at call time so config changes are honored."""
    return str(config.general.output_db_path)
```

and update every `DB_PATH` reference: `get_db_connection` becomes `conn = sqlite3.connect(_db_path())`, and `run_evaluation`'s pipeline config uses `"db_path": _db_path()`.

2. Add the pure selection helper (below `_db_path`):

```python
def select_prompts(prompts, topic=None, priority=None, limit=None):
    """Filter loaded prompts by topic/priority, then apply the limit."""
    selected = [
        p for p in prompts
        if (topic is None or p.topic == topic)
        and (priority is None or p.priority == priority)
    ]
    return selected[:limit] if limit else selected
```

3. Rewrite the top of `run_evaluation` (everything before `# Initialize engine`) as:

```python
    try:
        topic = None if topic in (None, "All Topics") else topic
        persona = None if persona in (None, "All Personas") else persona
        priority = None if priority in (None, "All Priorities") else priority

        prompts = select_prompts(
            load_prompts(str(config.general.question_json_path)),
            topic=topic, priority=priority, limit=num_prompts,
        )
        if not prompts:
            return {"error": "No prompts found with selected filters"}
```

and simplify the `RunOptions` construction to use the already-normalized values:

```python
        run_options = RunOptions(
            topic=topic,
            persona=persona,
            priority=priority,
            dry_run=False,
            run_type="dashboard",
            notes=f"Run from dashboard: {engine_name}",
        )
```

4. In `main()`'s "Run New Evaluation" expander, build real filter options:

```python
            all_prompts = load_prompts(str(config.general.question_json_path))
            topic_options = ["All Topics"] + sorted({p.topic for p in all_prompts})
            priority_options = ["All Priorities", "high", "medium", "low"]
```

and use `topic_options` / `priority_options` in the two `st.selectbox` calls (replacing the hardcoded `["All Topics", "CDC", "Oracle to Snowflake", "Schema Evolution"]` and `["All Priorities", "high", "medium", "low"]` lists).

- [ ] **Step 5: Run tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/dashboard/ tests/ -v`
Expected: PASS.

- [ ] **Step 6: Smoke-test the dashboard manually**

Run: `bash scripts/dashboard.sh` — in the sidebar pick engine `mock`, topic "Oracle CDC", 3 prompts, Start Evaluation. Expected: run completes (no `AttributeError`), appears in the run list with a non-zero-prompts row. Ctrl-C to stop.

- [ ] **Step 7: Commit**

```bash
git add tests/dashboard/test_select_prompts.py aeo_eval/models/result.py aeo_eval/runner/evaluator.py aeo_eval/dashboard/app.py
git commit -m "fix: dashboard topic filter crash, real topic list, filter-then-limit; widen run_type literal"
```

---

### Task 13: Run-scoped dashboard citation counts (D2)

`fetch_citations_for_run` LEFT JOINs `citation_occurrences` (empty until Task 5, now populated) and ignores its `run_id` argument, so counts were always 0 and never scoped. Rewrite the query.

**Files:**
- Create: `tests/dashboard/test_citation_query.py`
- Modify: `aeo_eval/dashboard/app.py` (`fetch_citations_for_run`)

**Interfaces:**
- Consumes: `citation_occurrences` rows (Task 5), `_db_path()` (Task 12).
- Produces: `fetch_citations_for_run(run_id)` returning rows with keys `domain`, `source_category`, `citation_count`, scoped to `run_id`.

- [ ] **Step 1: Write the failing test**

Create `tests/dashboard/test_citation_query.py`:

```python
"""Dashboard citation counts must be run-scoped and non-zero."""
import json
import sqlite3
import uuid

from aeo_eval.config import config as app_config
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_citation(conn, run_id, analysis_id, domain, category):
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, 'p1', 'mock')",
        (rr_id, run_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, striim_recommended, citations) "
        "VALUES (?, ?, 1, 0, ?)",
        (analysis_id, rr_id, json.dumps([])),
    )
    url = f"https://{domain}/{uuid.uuid4().hex[:6]}"
    cit_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
        "first_observed, last_observed, occurrence_count) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)",
        (cit_id, url, url, domain, category),
    )
    conn.execute(
        "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
        "VALUES (?, ?, ?)",
        (str(uuid.uuid4()), cit_id, analysis_id),
    )
    conn.commit()


def test_fetch_citations_scoped_to_run(tmp_path, monkeypatch):
    db = tmp_path / "dash.db"
    monkeypatch.setattr(app_config.general, "output_db_path", db)
    SQLiteStore(str(db)).init_db()
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON")
    seed_citation(conn, "run-1", "an-1", "fivetran.com", "competitor")
    seed_citation(conn, "run-1", "an-2", "fivetran.com", "competitor")
    seed_citation(conn, "run-2", "an-3", "estuary.dev", "competitor")
    conn.close()

    from aeo_eval.dashboard.app import fetch_citations_for_run

    rows = fetch_citations_for_run("run-1")
    assert len(rows) == 1
    assert rows[0]["domain"] == "fivetran.com"
    assert rows[0]["citation_count"] == 2  # run-2's estuary.dev excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/dashboard/test_citation_query.py -v`
Expected: FAIL — old query returns both domains (run_id ignored) with `citation_count` values not scoped.

- [ ] **Step 3: Rewrite the query**

Replace `fetch_citations_for_run` in `aeo_eval/dashboard/app.py` with:

```python
def fetch_citations_for_run(run_id):
    """Fetch citation counts observed in this run, grouped by domain."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.domain, c.source_category, COUNT(co.id) as citation_count
        FROM citation_occurrences co
        JOIN citations c ON co.citation_id = c.id
        JOIN response_analysis ra ON co.response_analysis_id = ra.id
        JOIN raw_responses rr ON ra.raw_response_id = rr.id
        WHERE rr.run_id = ?
        GROUP BY c.domain, c.source_category
        ORDER BY citation_count DESC
        LIMIT 20
    """, (run_id,))
    citations = cursor.fetchall()
    conn.close()
    return citations
```

- [ ] **Step 4: Run tests, then the full suite; commit**

Run: `.venv/bin/python -m pytest tests/dashboard/ tests/ -v`
Expected: PASS.

```bash
git add tests/dashboard/test_citation_query.py aeo_eval/dashboard/app.py
git commit -m "fix: dashboard citation counts read citation_occurrences scoped to the selected run"
```

---

### Task 14: Enforce the retention policy (E2)

The `data_retention_policy` table is seeded (365 days for responses/analyses/citations/website checks, 90 for crawler logs, NULL = keep forever for metrics/gaps/recommendations) but nothing enforces it. Add a purge that runs at the start of each pipeline run, deleting children before parents to satisfy FKs.

**Files:**
- Create: `tests/test_retention.py`
- Modify: `aeo_eval/storage/sqlite_store.py` (add `apply_retention`)
- Modify: `aeo_eval/orchestrator.py` (call it after `init_db`)

**Interfaces:**
- Consumes: `data_retention_policy` rows; `created_at` columns (SQLite `CURRENT_TIMESTAMP` format, comparable to `datetime('now', '-N days')`).
- Produces: `SQLiteStore.apply_retention() -> Dict[str, int]` (rows deleted per table).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retention.py`:

```python
"""Retention policy must actually delete expired rows, FK-safely."""
import json
import sqlite3
import uuid

from aeo_eval.storage.sqlite_store import SQLiteStore

OLD = "2020-01-01 00:00:00"  # far beyond every retention window


def seed(conn, run_id, analysis_id, created_at, with_citation=True):
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine, created_at) "
        "VALUES (?, ?, 'p1', 'mock', ?)",
        (rr_id, run_id, created_at),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, "
        "striim_recommended, citations, created_at) VALUES (?, ?, 1, 0, ?, ?)",
        (analysis_id, rr_id, json.dumps([]), created_at),
    )
    if with_citation:
        cit_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
            "first_observed, last_observed, occurrence_count, created_at) "
            "VALUES (?, 'https://ex.com/a', ?, 'ex.com', 'other', ?, ?, 1, ?)",
            (cit_id, f"https://ex.com/{analysis_id}", created_at, created_at, created_at),
        )
        conn.execute(
            "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
            "VALUES (?, ?, ?)",
            (str(uuid.uuid4()), cit_id, analysis_id),
        )
    conn.commit()


def counts(conn):
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("raw_responses", "response_analysis", "citations",
                      "citation_occurrences")
    }


def test_expired_rows_deleted_fresh_rows_kept(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    seed(conn, "run-old", "an-old", OLD)
    fresh = conn.execute("SELECT datetime('now')").fetchone()[0]
    seed(conn, "run-new", "an-new", fresh)
    conn.close()

    deleted = store.apply_retention()

    conn = sqlite3.connect(db)
    remaining = counts(conn)
    conn.close()
    assert remaining == {
        "raw_responses": 1, "response_analysis": 1,
        "citations": 1, "citation_occurrences": 1,
    }
    assert deleted["raw_responses"] == 1
    assert deleted["response_analysis"] == 1


def test_apply_retention_is_idempotent_on_empty_db(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    assert all(v == 0 for v in store.apply_retention().values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention.py -v`
Expected: FAIL with `AttributeError: 'SQLiteStore' object has no attribute 'apply_retention'`.

- [ ] **Step 3: Implement `apply_retention`**

Add to `SQLiteStore` in `aeo_eval/storage/sqlite_store.py`:

```python
    def apply_retention(self) -> Dict[str, int]:
        """Delete rows older than their data_retention_policy window.

        Children are purged before parents to satisfy foreign keys:
        citation_occurrences reference both response_analysis and
        citations; response_analysis references raw_responses. Tables
        with a NULL retention (metrics, gaps, recommendations) are
        never touched. Returns rows deleted per table.
        """
        deleted: Dict[str, int] = {}
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            policies = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT table_name, retention_days FROM data_retention_policy"
                ).fetchall()
                if row[1] is not None
            }

            def modifier(days):
                return f"-{int(days)} days"

            # 1. citation_occurrences referencing expiring analyses,
            #    analyses of expiring raw responses, or expiring citations.
            ra_days = policies.get("response_analysis")
            if ra_days is not None:
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE response_analysis_id IN "
                    "(SELECT id FROM response_analysis WHERE created_at < datetime('now', ?))",
                    (modifier(ra_days),),
                )
            rr_days = policies.get("raw_responses")
            if rr_days is not None:
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE response_analysis_id IN "
                    "(SELECT ra.id FROM response_analysis ra "
                    " JOIN raw_responses rr ON ra.raw_response_id = rr.id "
                    " WHERE rr.created_at < datetime('now', ?))",
                    (modifier(rr_days),),
                )
                # analyses attached to expiring raw responses go too,
                # even if the analysis row itself is younger.
                conn.execute(
                    "DELETE FROM response_analysis WHERE raw_response_id IN "
                    "(SELECT id FROM raw_responses WHERE created_at < datetime('now', ?))",
                    (modifier(rr_days),),
                )
            c_days = policies.get("citations")
            if c_days is not None:
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE citation_id IN "
                    "(SELECT id FROM citations WHERE created_at < datetime('now', ?))",
                    (modifier(c_days),),
                )

            # 2. The policy tables themselves, children before parents.
            for table in (
                "response_analysis",
                "crawler_logs",
                "website_checks",
                "citations",
                "raw_responses",
            ):
                days = policies.get(table)
                if days is None:
                    continue
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE created_at < datetime('now', ?)",
                    (modifier(days),),
                )
                deleted[table] = cur.rowcount
            conn.commit()
        return deleted
```

(`table` interpolation is safe — the names come from the fixed tuple above, not from data.)

- [ ] **Step 4: Wire into the orchestrator**

In `aeo_eval/orchestrator.py` `run_full_pipeline`, immediately after `self.store.init_db()`:

```python
            purged = self.store.apply_retention()
            purged = {k: v for k, v in purged.items() if v}
            if purged:
                logger.info(f"Retention purge removed rows: {purged}")
```

- [ ] **Step 5: Run tests, then the full suite; commit**

Run: `.venv/bin/python -m pytest tests/test_retention.py tests/ -v`
Expected: PASS.

```bash
git add tests/test_retention.py aeo_eval/storage/sqlite_store.py aeo_eval/orchestrator.py
git commit -m "feat: enforce data_retention_policy with FK-safe purge at pipeline start"
```

---

### Task 15: Full verification sweep

**Files:**
- Possibly modify: any test file with stale assertions not caught per-task.

**Interfaces:** none — verification only.

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: everything passes. Fix any straggler (most likely candidates: `tests/test_runner.py`, `tests/integration/test_full_pipeline.py`, `tests/integration/test_module3_end_to_end.py` — they exercise the evaluator/orchestrator whose persistence and analyzer behavior changed; assertions to update are counts of persisted rows and any expectation that failures are absent from storage).

- [ ] **Step 2: End-to-end smoke with the mock engine**

```bash
.venv/bin/python -m aeo_eval.cli run --engine mock --limit 5 --db /tmp/aeovis-smoke.db
.venv/bin/python - <<'EOF'
import sqlite3
conn = sqlite3.connect("/tmp/aeovis-smoke.db")
runs = conn.execute("SELECT run_id, num_prompts, cost, status FROM evaluation_runs").fetchall()
assert runs and runs[0][1] == 5, runs
print("evaluation_runs OK:", runs)
print("raw_responses:", conn.execute("SELECT COUNT(*) FROM raw_responses").fetchone()[0])
EOF
rm /tmp/aeovis-smoke.db
```

Expected: `num_prompts == 5`, 5 raw responses, no traceback.

- [ ] **Step 3: Commit any straggler fixes**

```bash
git add -A tests/
git commit -m "test: align remaining assertions with fixed persistence/metrics behavior"
```

---

## Out of scope / deferred

- Modules 6 (website & crawler accessibility) and 7 (request-log analysis) — explicitly excluded by the user.
- Housekeeping (uncommitted `spec.md`/`considerations.txt`, stale `.worktrees/2026-08-14-modules-3-10/`) — needs the user's decision; not part of this plan.
- Migrating historical rows from `data/aeovis.db` — the file stays untouched per the approved design.
