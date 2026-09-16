# AEO Visibility Dashboard

The AEO Visibility Platform includes a live Streamlit dashboard that displays insights from your evaluation runs.

## Quick Start

### Install Dependencies

```bash
pip install streamlit plotly pandas
```

Or install all project dependencies:

```bash
pip install -e .
```

### Run the Dashboard

```bash
bash scripts/dashboard.sh
```

Or directly:

```bash
streamlit run aeo_eval/dashboard/app.py
```

The dashboard will open at `http://localhost:8501`

## Dashboard Views

### 📊 Visibility Metrics

Displays key metrics from the most recent evaluation run:

- **Mention Rate**: Percentage of responses mentioning Striim
- **Top-3 Placement**: Percentage of mentions appearing in top 3 results
- **Citation Rate**: Percentage of responses citing Striim content
- **Competitive Share**: Top competitor visibility compared to Striim

**By-Topic Breakdown**: View metrics segmented by evaluation topics (CDC, Oracle to Snowflake, Schema Evolution, etc.)

**Visibility Trend**: Line chart showing 30-day trend of mention rate, top-3 placement, and citation rate across all runs.

### 🎯 Gaps & Recommendations

Identifies visibility gaps and actionable recommendations:

**Detected Gaps**:
- Organized by gap type (Visibility and Citation are produced today; the filter also lists Content and Technical for future use)
- Shows Striim visibility vs. top competitor
- Indicates priority and confidence level
- Filterable by gap type and priority

**Recommendations**:
- Generated from detected gaps with priority scores (1-10)
- Shows approval status (Draft, Pending, Approved, Rejected, Implemented)
- Displays estimated effort and suggested owner
- Filterable by status

### 📚 Citation Analysis

Analyzes citation patterns and sources:

**Most-Cited Domains**:
- Bar chart showing top 10 domains by citation count
- Categorized by source type (Striim-owned, Competitor, Technical Publication, Review Platform, etc.)
- Full table view of all citations

**Citation Sources by Category**:
- Pie chart showing breakdown of citation sources by category
- Helps identify competitor visibility vs. Striim content presence

## Data Flow

The dashboard pulls real-time data from the SQLite database:

1. **Evaluation Runs** → Latest run metadata (engine, cost, timestamp)
2. **Visibility Metrics** → Overall and by-topic mention/citation rates
3. **Gaps** → Detected visibility and citation gaps
4. **Recommendations** → Generated actions with approval status
5. **Citations** → Deduplicated domain analysis

## Updating the Dashboard

The dashboard reflects the latest evaluation run in the database. To see new data:

1. Run a new evaluation (from the CLI, or with the dashboard's **Configure & Run** panel):
   ```bash
   python -m aeo_eval.cli run --engine claude --limit 5
   ```

2. Refresh the dashboard (F5 or browser reload)

The metrics and gaps will automatically update to reflect the newest run.

## Customization

Edit `aeo_eval/dashboard/app.py` to:

- Change the historical trend window (currently 30 days)
- Add new metrics or visualizations
- Modify color schemes
- Add filters or drill-down capabilities
- Export data to CSV/PDF

## Troubleshooting

**"No evaluation runs found"**
- Ensure the database exists: `data/eval_runs.db`
- Run the demo to generate sample data: `bash scripts/demo.sh`

**Missing data in views**
- Check the database:
  ```bash
  sqlite3 data/eval_runs.db "SELECT count(*) FROM evaluation_runs;"
  ```
- Run a complete evaluation: `python -m aeo_eval.cli run --engine claude`

**Performance issues**
- Limit the historical trend window in the code
- Filter by specific dates or topics
- Archive old runs to a separate database
