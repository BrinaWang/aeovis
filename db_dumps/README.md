# Database dumps

Plain-SQL snapshots of the SQLite databases in `data/` (which is gitignored).
Committing these keeps the accumulated evaluation data in version control.

| File | Source | Contents |
|------|--------|----------|
| `eval_runs.sql` | `data/eval_runs.db` | Live database: all evaluation runs, raw responses, analyses, citations, website checks, crawler logs, metrics, gaps, recommendations |
| `aeovis_legacy.sql` | `data/aeovis.db` | Older August 2026 database from an earlier schema; kept for history |

## Refresh the dump

Run from the repo root after new evaluation runs:

```
sqlite3 data/eval_runs.db .dump > db_dumps/eval_runs.sql
```

Then commit and push as normal.

## Restore

```
sqlite3 data/eval_runs.db < db_dumps/eval_runs.sql
```

The target file must not already exist, or the `CREATE TABLE` statements will fail.
