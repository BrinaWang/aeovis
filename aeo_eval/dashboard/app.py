"""Streamlit dashboard for AEO Visibility Platform."""

import os
from pathlib import Path

# Load .env from project root - essential for API keys
try:
    from dotenv import load_dotenv
    # Start from the directory containing this file and look up
    dashboard_dir = Path(__file__).resolve().parent
    project_root = dashboard_dir.parent.parent

    # Look for .env in multiple locations: project root, parent, current dir
    env_search_paths = [
        project_root / ".env",
        project_root.parent / ".env",
        Path.cwd() / ".env",
    ]

    for env_path in env_search_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except (ImportError, Exception):
    # If python-dotenv not available or fails, continue anyway
    # ANTHROPIC_API_KEY might be set in environment already
    pass

import sqlite3
import json
import threading
import time
import yaml
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from aeo_eval.config import config, PROJECT_ROOT
from aeo_eval.dashboard.progress import fetch_run_progress, describe_progress
from aeo_eval.dashboard.formatting import (
    EFFORT_LABELS,
    get_effort_color,
    get_platform_badge,
    normalize_implementation_step,
)
from aeo_eval.data.prompt_loader import load_prompts
from aeo_eval.engine.factory import available_engines, create_engine
from aeo_eval.runner.evaluator import RunOptions
from aeo_eval.orchestrator import AEOPipelineOrchestrator
from aeo_eval.website_accessibility import WebsiteAccessibilityChecker

def _db_path() -> str:
    """Resolve the DB path at call time so config changes are honored."""
    return str(config.general.output_db_path)


def select_prompts(prompts, topic=None, priority=None, limit=None):
    """Filter loaded prompts by topic/priority, then apply the limit."""
    selected = [
        p for p in prompts
        if (topic is None or p.topic == topic)
        and (priority is None or p.priority == priority)
    ]
    return selected[:limit] if limit else selected


def run_evaluation(engine_name: str, num_prompts: int, topic: str = None,
                   persona: str = None, priority: str = None):
    """Run a new evaluation."""
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Starting evaluation: engine={engine_name}, num_prompts={num_prompts}")

        topic = None if topic in (None, "All Topics") else topic
        persona = None if persona in (None, "All Personas") else persona
        priority = None if priority in (None, "All Priorities") else priority

        logger.info(f"Loading prompts from {config.general.question_json_path}")
        prompts = select_prompts(
            load_prompts(str(config.general.question_json_path)),
            topic=topic, priority=priority, limit=num_prompts,
        )
        logger.info(f"Loaded {len(prompts)} prompts")
        if not prompts:
            return {"error": "No prompts found with selected filters"}

        # Initialize engine
        logger.info(f"Creating engine: {engine_name}")
        engine = create_engine(engine_name)
        logger.info(f"Engine created successfully")

        # Prepare run options
        run_options = RunOptions(
            topic=topic,
            persona=persona,
            priority=priority,
            dry_run=False,
            run_type="dashboard",
            notes=f"Run from dashboard: {engine_name}",
        )

        # Run pipeline
        pipeline_config = {
            "db_path": _db_path(),
            "cost_limit_per_run": config.general.cost_limit_per_run,
        }
        logger.info(f"Starting pipeline with db_path={pipeline_config['db_path']}")
        orchestrator = AEOPipelineOrchestrator(engine, pipeline_config)
        result = orchestrator.run_full_pipeline(prompts, run_options)
        logger.info(f"Pipeline complete: {result}")

        return result
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Evaluation failed: {type(e).__name__}: {e}", exc_info=True)
        return {"error": f"{type(e).__name__}: {str(e)}"}


def get_db_connection():
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all_runs():
    """Fetch all evaluation runs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM evaluation_runs
        ORDER BY timestamp DESC
    """)
    runs = cursor.fetchall()
    conn.close()
    return runs


def delete_run(run_id):
    """Delete a run and all its related data in correct order."""
    conn = get_db_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        # Get all related IDs BEFORE deleting anything
        cursor.execute("SELECT id FROM gaps WHERE run_id = ?", (run_id,))
        gap_ids = [row['id'] for row in cursor.fetchall()]

        cursor.execute("SELECT id FROM raw_responses WHERE run_id = ?", (run_id,))
        response_ids = [row['id'] for row in cursor.fetchall()]

        cursor.execute("SELECT id FROM response_analysis WHERE raw_response_id IN ({})".format(
            ','.join('?' * len(response_ids))
        ) if response_ids else "SELECT id FROM response_analysis WHERE 1=0", response_ids)
        analysis_ids = [row['id'] for row in cursor.fetchall()]

        # Delete in order of dependencies (leaf nodes first)
        # 1. citation_occurrences (depends on response_analysis and citations)
        if analysis_ids:
            cursor.execute("DELETE FROM citation_occurrences WHERE response_analysis_id IN ({})".format(
                ','.join('?' * len(analysis_ids))
            ), analysis_ids)

        # 2. recommendations (depends on gaps)
        if gap_ids:
            cursor.execute("DELETE FROM recommendations WHERE gap_id IN ({})".format(
                ','.join('?' * len(gap_ids))
            ), gap_ids)

        # 3. response_analysis (depends on raw_responses)
        if response_ids:
            cursor.execute("DELETE FROM response_analysis WHERE raw_response_id IN ({})".format(
                ','.join('?' * len(response_ids))
            ), response_ids)

        # 4. Tables that directly reference evaluation_runs
        cursor.execute("DELETE FROM gaps WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM visibility_metrics WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM raw_responses WHERE run_id = ?", (run_id,))

        # 5. Finally delete the run itself
        cursor.execute("DELETE FROM evaluation_runs WHERE run_id = ?", (run_id,))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def fetch_latest_run():
    """Fetch the latest evaluation run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM evaluation_runs
        ORDER BY timestamp DESC LIMIT 1
    """)
    run = cursor.fetchone()
    conn.close()
    return run


def fetch_run_by_id(run_id):
    """Fetch a specific run by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM evaluation_runs WHERE run_id = ?
    """, (run_id,))
    run = cursor.fetchone()
    conn.close()
    return run


def fetch_metrics_for_run(run_id):
    """Fetch visibility metrics for a run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM visibility_metrics
        WHERE run_id = ? AND dimension IN ('overall', 'by_topic')
        ORDER BY dimension, dimension_value
    """, (run_id,))
    metrics = cursor.fetchall()
    conn.close()
    return metrics


def fetch_gaps_for_run(run_id):
    """Fetch detected gaps for a run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM gaps
        WHERE run_id = ?
        ORDER BY priority = 'high' DESC, priority = 'medium' DESC
    """, (run_id,))
    gaps = cursor.fetchall()
    conn.close()
    return gaps


def fetch_recommendations_for_run(run_id):
    """Fetch recommendations for a run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.* FROM recommendations r
        JOIN gaps g ON r.gap_id = g.id
        WHERE g.run_id = ?
        ORDER BY r.priority DESC, r.status = 'approved' DESC
    """, (run_id,))
    recommendations = cursor.fetchall()
    conn.close()
    return recommendations


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


def fetch_historical_trends(days=30):
    """Fetch historical visibility trends."""
    conn = get_db_connection()
    cursor = conn.cursor()
    since = datetime.now() - timedelta(days=days)
    cursor.execute("""
        SELECT er.timestamp, vm.dimension, vm.dimension_value,
               vm.striim_mention_rate, vm.striim_top3_rate, vm.striim_citation_rate
        FROM visibility_metrics vm
        JOIN evaluation_runs er ON vm.run_id = er.run_id
        WHERE er.timestamp >= ? AND vm.dimension = 'overall'
        ORDER BY er.timestamp
    """, (since.isoformat(),))
    trends = cursor.fetchall()
    conn.close()
    return trends


def fetch_cost_trends(days=30):
    """Fetch historical cost trends across runs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    since = datetime.now() - timedelta(days=days)
    cursor.execute("""
        SELECT timestamp, engine, cost, num_prompts
        FROM evaluation_runs
        WHERE timestamp >= ?
        ORDER BY timestamp
    """, (since.isoformat(),))
    trends = cursor.fetchall()
    conn.close()
    return trends


def fetch_website_checks_for_run(run_id):
    """Fetch website checks for a run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT wc.* FROM website_checks wc WHERE wc.run_id = ? ORDER BY wc.check_timestamp DESC LIMIT 100", (run_id,))
    checks = cursor.fetchall()
    conn.close()
    return checks


def fetch_website_checks_by_crawler(run_id):
    """Fetch website checks grouped by crawler and result for a specific run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT crawler, result, COUNT(*) as count FROM website_checks WHERE run_id = ? GROUP BY crawler, result ORDER BY crawler", (run_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def fetch_all_module6_checks():
    """Fetch all website checks from all runs, ordered by timestamp descending."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT wc.*, er.timestamp as run_timestamp
        FROM website_checks wc
        LEFT JOIN evaluation_runs er ON wc.run_id = er.run_id
        ORDER BY wc.check_timestamp DESC
        LIMIT 500
    """)
    checks = cursor.fetchall()
    conn.close()
    return checks


def fetch_module6_run_history():
    """Fetch distinct Module 6 runs (runs that have website checks)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT wc.run_id, MAX(wc.check_timestamp) as last_check, COUNT(*) as num_checks
        FROM website_checks wc
        GROUP BY wc.run_id
        ORDER BY MAX(wc.check_timestamp) DESC
        LIMIT 50
    """)
    runs = cursor.fetchall()
    conn.close()
    return runs


def run_module6_standalone(pages: list, crawlers: list) -> dict:
    """Run Module 6 checks independently and store results."""
    try:
        import logging
        import uuid
        from aeo_eval.storage.sqlite_store import SQLiteStore

        logger = logging.getLogger(__name__)
        logger.info(f"Starting standalone Module 6 run on {len(pages)} pages for {len(crawlers)} crawlers")

        # Create a synthetic run ID for this Module 6-only run
        run_id = f"module6-{uuid.uuid4().hex[:12]}"

        # Initialize database
        store = SQLiteStore(_db_path())
        store.init_db()

        # Create checker and run checks
        checker = WebsiteAccessibilityChecker()
        checks = checker.check_pages(pages, crawlers)

        # Add run_id to each check
        for check in checks:
            check['run_id'] = run_id

        # Store results
        if checks:
            store.store_website_checks(checks)
            logger.info(f"Stored {len(checks)} website accessibility checks for run {run_id}")
            return {
                "success": True,
                "run_id": run_id,
                "num_checks": len(checks),
                "pages_checked": len(pages),
                "crawlers_checked": len(crawlers)
            }
        else:
            return {
                "success": False,
                "error": "No checks generated"
            }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Module 6 standalone run failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def fetch_crawler_logs_summary(run_id):
    """Fetch crawler logs summary with request and error counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT crawler, COUNT(*) as request_count, SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) as error_count FROM crawler_logs WHERE run_id = ? GROUP BY crawler ORDER BY request_count DESC", (run_id,))
    summary = cursor.fetchall()
    conn.close()
    return summary


def fetch_crawler_logs_by_path(run_id):
    """Fetch crawler logs grouped by path, crawler, and status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT path, crawler, http_status, COUNT(*) as count FROM crawler_logs WHERE run_id = ? GROUP BY path, crawler, http_status ORDER BY count DESC LIMIT 50", (run_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def fetch_crawler_log_failures(run_id):
    """Fetch failed requests from crawler logs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, host, path, crawler, http_status, response_time_ms FROM crawler_logs WHERE run_id = ? AND http_status >= 400 ORDER BY timestamp DESC LIMIT 50", (run_id,))
    failures = cursor.fetchall()
    conn.close()
    return failures


def fetch_cost_by_topic():
    """Fetch cost breakdown by topic across all runs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            vm.dimension_value as topic,
            COUNT(DISTINCT vm.run_id) as num_runs,
            SUM(er.cost) as total_cost,
            SUM(er.num_prompts) as total_prompts,
            AVG(er.cost) as avg_cost_per_run
        FROM visibility_metrics vm
        JOIN evaluation_runs er ON vm.run_id = er.run_id
        WHERE vm.dimension = 'by_topic' AND vm.dimension_value IS NOT NULL
        GROUP BY vm.dimension_value
        ORDER BY total_cost DESC
    """)
    results = cursor.fetchall()
    conn.close()
    return results


def fetch_daily_budget_status():
    """Fetch today's cost and calculate remaining budget."""
    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.now().date()
    cursor.execute("""
        SELECT SUM(cost) as total_cost
        FROM evaluation_runs
        WHERE DATE(timestamp) = ?
    """, (today.isoformat(),))
    result = cursor.fetchone()
    conn.close()

    today_cost = result['total_cost'] or 0
    daily_limit = config.general.cost_limit_per_day
    remaining = daily_limit - today_cost

    return {
        'today_cost': today_cost,
        'daily_limit': daily_limit,
        'remaining': remaining,
        'percent_used': (today_cost / daily_limit * 100) if daily_limit > 0 else 0
    }


def fetch_recommendations_for_approval(run_id):
    """Fetch recommendations for approval with statuses: draft, pending_approval, pending_publish, edited."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.* FROM recommendations r
        JOIN gaps g ON r.gap_id = g.id
        WHERE g.run_id = ? AND r.status IN ('draft', 'pending_approval', 'pending_publish', 'edited')
        ORDER BY r.priority DESC, r.created_timestamp DESC
    """, (run_id,))
    recommendations = cursor.fetchall()
    conn.close()
    return recommendations


def fetch_recommendation_evidence_bulk(rec_ids):
    """Fetch evidence rows for many recommendations in one query, keyed by id."""
    if not rec_ids:
        return {}
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(rec_ids))
    cursor.execute(f"""
        SELECT r.id, r.gap_id, r.problem, r.evidence_summary, r.affected_pages,
               g.topic, g.gap_type, g.striim_visibility, g.top_competitor_visibility,
               g.top_competitor_name, g.priority as gap_priority, g.confidence
        FROM recommendations r
        JOIN gaps g ON r.gap_id = g.id
        WHERE r.id IN ({placeholders})
    """, list(rec_ids))
    rows = cursor.fetchall()
    conn.close()
    return {row['id']: row for row in rows}


def format_metric_card(label, value, change=None, subtext=None):
    """Create a formatted metric card."""
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.metric(label, f"{value:.1%}" if isinstance(value, float) else value)
    if change:
        with col2:
            st.caption(f"Change: {change:+.1%}")
    if subtext:
        with col3:
            st.caption(subtext)


def render_visibility_metrics_view(run):
    """Render detailed trends and metrics breakdown."""
    st.markdown("<h3 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Detailed Metrics & Trends</h3>", unsafe_allow_html=True)

    metrics = fetch_metrics_for_run(run['run_id'])

    if metrics:
        # By-topic breakdown
        topic_metrics = [m for m in metrics if m['dimension'] == 'by_topic']
        if topic_metrics:
            st.markdown("#### Metrics by Topic")

            df_topics = pd.DataFrame([
                {
                    'Topic': m['dimension_value'],
                    'Mention Rate': m['striim_mention_rate'] or 0,
                    'Top-3 Rate': m['striim_top3_rate'] or 0,
                    'Citation Rate': m['striim_citation_rate'] or 0,
                    'Responses': m['num_responses']
                }
                for m in topic_metrics
            ])

            st.dataframe(df_topics, use_container_width=True, hide_index=True)

        # Trend chart
        st.markdown("#### Visibility Trend (Last 30 Days)")
        trends = fetch_historical_trends(30)

        if trends:
            df_trends = pd.DataFrame([
                {
                    'Date': datetime.fromisoformat(t['timestamp']).date(),
                    'Mention Rate': t['striim_mention_rate'] or 0,
                    'Top-3 Rate': t['striim_top3_rate'] or 0,
                    'Citation Rate': t['striim_citation_rate'] or 0,
                }
                for t in trends
            ])

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_trends['Date'], y=df_trends['Mention Rate'],
                mode='lines+markers', name='Mention Rate',
                line=dict(color='#0369a1', width=2),
                marker=dict(size=6)
            ))
            fig.add_trace(go.Scatter(
                x=df_trends['Date'], y=df_trends['Top-3 Rate'],
                mode='lines+markers', name='Top-3 Placement',
                line=dict(color='#f59e0b', width=2),
                marker=dict(size=6)
            ))
            fig.add_trace(go.Scatter(
                x=df_trends['Date'], y=df_trends['Citation Rate'],
                mode='lines+markers', name='Citation Rate',
                line=dict(color='#10b981', width=2),
                marker=dict(size=6)
            ))

            fig.update_layout(
                hovermode='x unified',
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No historical data available yet. Run evaluations to see trends.")

        # Cost trend chart
        st.markdown("#### Cost Trend (Last 30 Days)")
        cost_trends = fetch_cost_trends(30)

        if cost_trends:
            df_costs = pd.DataFrame([
                {
                    'Date': datetime.fromisoformat(t['timestamp']).date(),
                    'Cost': t['cost'] or 0,
                    'Engine': t['engine'],
                    'Prompts': t['num_prompts']
                }
                for t in cost_trends
            ])

            fig = go.Figure()
            for engine in df_costs['Engine'].unique():
                engine_data = df_costs[df_costs['Engine'] == engine]
                fig.add_trace(go.Scatter(
                    x=engine_data['Date'], y=engine_data['Cost'],
                    mode='lines+markers', name=engine,
                    line=dict(width=2),
                    marker=dict(size=6)
                ))

            fig.update_layout(
                hovermode='x unified',
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white',
                yaxis_title='Cost ($)',
                xaxis_title='Date'
            )
            st.plotly_chart(fig, use_container_width=True)


def render_gaps_recommendations_view(run):
    """Render the Gaps & Recommendations view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Gaps & Recommendations</h2>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        gap_type_filter = st.selectbox(
            "Gap Type",
            ["All Types", "Visibility", "Citation", "Content", "Technical"],
            key="gap_type"
        )
    with col2:
        priority_filter = st.selectbox(
            "Priority",
            ["All Priorities", "High", "Medium", "Low"],
            key="priority"
        )

    gaps = fetch_gaps_for_run(run['run_id'])

    if gaps:
        # Filter gaps
        filtered_gaps = gaps
        if gap_type_filter != "All Types":
            filtered_gaps = [g for g in filtered_gaps if g['gap_type'] == gap_type_filter.lower()]
        if priority_filter != "All Priorities":
            filtered_gaps = [g for g in filtered_gaps if g['priority'] == priority_filter.lower()]

        if filtered_gaps:
            st.markdown("#### Detected Gaps")

            for gap in filtered_gaps:
                priority_color = {
                    'high': '',
                    'medium': '',
                    'low': ''
                }

                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        st.markdown(f"**{gap['topic']}** — {gap['gap_type'].title()}")
                        st.caption(f"Striim: {gap['striim_visibility']:.1%} | "
                                 f"{gap['top_competitor_name']}: {gap['top_competitor_visibility']:.1%}")

                    with col2:
                        st.caption(f"{priority_color.get(gap['priority'], '?')} "
                                 f"{gap['priority'].upper()}")

                    with col3:
                        st.caption(f"Confidence: {gap['confidence'].upper()}")
        else:
            st.info("No gaps match the selected filters.")
    else:
        st.info("No gaps detected yet.")

    # Recommendations
    st.markdown("#### Recommendations")
    recommendations = fetch_recommendations_for_run(run['run_id'])

    if recommendations:
        status_filter = st.selectbox(
            "Status",
            ["All Statuses", "Draft", "Pending Approval", "Approved", "Rejected"],
            key="status"
        )

        filtered_recs = recommendations
        if status_filter != "All Statuses":
            filtered_recs = [
                r for r in filtered_recs
                if r['status'] == status_filter.lower().replace(" ", "_")
            ]

        if filtered_recs:
            evidence_by_rec = fetch_recommendation_evidence_bulk([r['id'] for r in filtered_recs])
            for rec in filtered_recs:
                status_color = {
                    'draft': '',
                    'pending_approval': '',
                    'approved': '',
                    'rejected': '',
                    'implemented': ''
                }

                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])

                    with col1:
                        st.markdown(f"**{rec['recommended_action']}**")
                        st.caption(f"Priority: {rec['priority']}/10 | "
                                 f"Effort: {rec['estimated_effort']} pts")

                    with col2:
                        status_label = rec['status'].replace('_', ' ').title()
                        st.caption(f"{status_color.get(rec['status'], '?')} {status_label}")

                    # Full problem statement
                    st.markdown("**Problem:**")
                    st.markdown(rec['problem'])

                    # Evidence summary
                    if rec['evidence_summary']:
                        st.markdown("**Evidence:**")
                        st.markdown(rec['evidence_summary'])

                    # Expandable section for full details
                    with st.expander("View Full Details"):
                        evidence = evidence_by_rec.get(rec['id'])

                        # Gap context
                        if evidence:
                            st.markdown("**Gap Context:**")
                            st.markdown(f"{evidence['topic']} - {evidence['gap_type'].title()}")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.caption(f"Striim Visibility: {evidence['striim_visibility']:.1%}")
                            with col2:
                                st.caption(f"Competitor ({evidence['top_competitor_name']}): {evidence['top_competitor_visibility']:.1%}")
                            with col3:
                                st.caption(f"Confidence: {evidence['confidence'].title()}")

                        # Affected pages
                        if rec['affected_pages']:
                            try:
                                affected = json.loads(rec['affected_pages'])
                                if affected:
                                    st.markdown("**Affected Pages:**")
                                    for page in affected:
                                        st.caption(f"- {page}")
                            except (json.JSONDecodeError, TypeError):
                                st.caption(f"Affected Pages: {rec['affected_pages']}")

                        # Implementation steps
                        impl_steps = rec['implementation_steps'] if 'implementation_steps' in rec.keys() else None
                        if impl_steps:
                            st.markdown("**Implementation Steps:**")
                            render_implementation_steps(impl_steps)

                        # Metadata
                        st.markdown("**Metadata:**")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption(f"ID: {rec['id']}")
                            st.caption(f"Gap ID: {rec['gap_id']}")
                            st.caption(f"Created: {rec['created_timestamp']}")
                        with col2:
                            if 'suggested_owner' in rec.keys() and rec['suggested_owner']:
                                st.caption(f"Suggested Owner: {rec['suggested_owner']}")
                            if 'measurement_plan' in rec.keys() and rec['measurement_plan']:
                                st.caption(f"Measurement Plan: {rec['measurement_plan']}")
                            if 'approved_by' in rec.keys() and rec['approved_by']:
                                st.caption(f"Approved By: {rec['approved_by']}")
        else:
            st.info("No recommendations match the selected filters.")
    else:
        st.info("No recommendations generated yet.")


def render_comparison_view(all_runs):
    """Render the Run Comparison view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Run Comparison</h2>", unsafe_allow_html=True)

    # Get metrics for all runs
    all_metrics = []
    for run in all_runs:
        metrics = fetch_metrics_for_run(run['run_id'])
        overall = next((m for m in metrics if m['dimension'] == 'overall'), None)
        if overall:
            all_metrics.append({
                'Run ID': run['run_id'][-8:],
                'Timestamp': datetime.fromisoformat(run['timestamp']).strftime('%Y-%m-%d %H:%M'),
                'Engine': run['engine'],
                'Mention Rate': overall['striim_mention_rate'] or 0,
                'Top-3 Rate': overall['striim_top3_rate'] or 0,
                'Citation Rate': overall['striim_citation_rate'] or 0,
                'Recommendation Rate': overall['striim_recommendation_rate'] or 0,
                'Responses': overall['num_responses'],
                'Cost': run['cost'] or 0,
                'Cost/Prompt': ((run['cost'] or 0) / run['num_prompts']) if run['num_prompts'] > 0 else 0
            })

    if all_metrics:
        df_comparison = pd.DataFrame(all_metrics)

        # Metrics table
        st.markdown("#### Metrics Across Runs")
        st.dataframe(df_comparison, use_container_width=True, hide_index=True)

        # Trend comparison chart
        st.markdown("#### Metric Trends")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_comparison['Timestamp'],
            y=df_comparison['Mention Rate'],
            mode='lines+markers',
            name='Mention Rate',
            line=dict(color='#0369a1', width=2),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_comparison['Timestamp'],
            y=df_comparison['Top-3 Rate'],
            mode='lines+markers',
            name='Top-3 Placement',
            line=dict(color='#f59e0b', width=2),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_comparison['Timestamp'],
            y=df_comparison['Citation Rate'],
            mode='lines+markers',
            name='Citation Rate',
            line=dict(color='#10b981', width=2),
            marker=dict(size=8)
        ))

        fig.update_layout(
            hovermode='x unified',
            height=450,
            margin=dict(l=0, r=0, t=0, b=0),
            template='plotly_white'
        )
        st.plotly_chart(fig, use_container_width=True)

        # Performance summary
        col1, col2, col3, col4 = st.columns(4)

        latest = df_comparison.iloc[0]  # Most recent run
        oldest = df_comparison.iloc[-1]  # Oldest run

        with col1:
            delta = latest['Mention Rate'] - oldest['Mention Rate']
            st.metric(
                "Mention Rate Change",
                f"{delta:+.1%}",
                f"From {oldest['Mention Rate']:.1%} to {latest['Mention Rate']:.1%}"
            )

        with col2:
            delta = latest['Top-3 Rate'] - oldest['Top-3 Rate']
            st.metric(
                "Top-3 Change",
                f"{delta:+.1%}",
                f"From {oldest['Top-3 Rate']:.1%} to {latest['Top-3 Rate']:.1%}"
            )

        with col3:
            delta = latest['Citation Rate'] - oldest['Citation Rate']
            st.metric(
                "Citation Rate Change",
                f"{delta:+.1%}",
                f"From {oldest['Citation Rate']:.1%} to {latest['Citation Rate']:.1%}"
            )

        with col4:
            total_runs = len(df_comparison)
            st.metric(
                "Total Runs",
                total_runs,
                f"{(latest['Timestamp'])}"
            )
    else:
        st.info("No comparable metrics found.")


def render_citation_analysis_view(run):
    """Render the Citation Analysis view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Citation Analysis</h2>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Most-Cited Domains")
        citations = fetch_citations_for_run(run['run_id'])

        if citations:
            df_citations = pd.DataFrame([
                {
                    'Domain': c['domain'],
                    'Category': c['source_category'] or 'Uncategorized',
                    'Citations': c['citation_count'] or 0
                }
                for c in citations
            ])

            # Bar chart
            fig = px.bar(
                df_citations.head(10),
                x='Citations',
                y='Domain',
                orientation='h',
                color='Category',
                hover_data=['Category'],
                labels={'Citations': 'Number of Citations'}
            )
            fig.update_layout(
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)

            # Table
            st.dataframe(df_citations, use_container_width=True, hide_index=True)
        else:
            st.info("No citation data available yet.")

    with col2:
        st.markdown("#### Citation Sources by Category")

        if citations:
            # Count by category
            category_counts = {}
            for c in citations:
                cat = c['source_category'] or 'Uncategorized'
                category_counts[cat] = category_counts.get(cat, 0) + (c['citation_count'] or 0)

            if category_counts:
                fig = go.Figure(data=[go.Pie(
                    labels=list(category_counts.keys()),
                    values=list(category_counts.values()),
                    marker=dict(
                        colors=['#0369a1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'][:len(category_counts)]
                    )
                )])
                fig.update_layout(
                    height=400,
                    margin=dict(l=0, r=0, t=0, b=0),
                    template='plotly_white'
                )
                st.plotly_chart(fig, use_container_width=True)


def render_request_logs_view(run):
    """Render the Request Logs view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Request Logs</h2>", unsafe_allow_html=True)

    # Fetch logs data
    summary = fetch_crawler_logs_summary(run['run_id'])
    by_path = fetch_crawler_logs_by_path(run['run_id'])
    failures = fetch_crawler_log_failures(run['run_id'])

    if not summary and not by_path and not failures:
        st.info("No request log data available yet.")
        return

    # Calculate aggregate metrics
    total_requests = sum(row['request_count'] for row in summary) if summary else 0
    total_errors = sum(row['error_count'] or 0 for row in summary) if summary else 0
    error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0

    # Display metric cards
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Requests", total_requests)

    with col2:
        st.metric("Failed Requests", total_errors)

    with col3:
        st.metric("Error Rate %", f"{error_rate:.1f}%")

    st.divider()

    # Crawler Activity Table
    if summary:
        st.markdown("#### Crawler Activity")

        df_crawler_activity = pd.DataFrame([
            {
                'Crawler': row['crawler'],
                'Requests': row['request_count'],
                'Errors': row['error_count'] or 0,
                'Error Rate': f"{(row['error_count'] or 0) / row['request_count'] * 100:.1f}%" if row['request_count'] > 0 else "0%"
            }
            for row in summary
        ])

        st.dataframe(df_crawler_activity, use_container_width=True, hide_index=True)
    else:
        st.info("No crawler activity data available.")

    st.divider()

    # Failed Requests Detail Table
    if failures:
        st.markdown("#### Failed Requests (Status >= 400)")

        df_failures = pd.DataFrame([
            {
                'Time': row['timestamp'],
                'Crawler': row['crawler'],
                'Path': row['path'],
                'Status': row['http_status'],
                'Response (ms)': row['response_time_ms']
            }
            for row in failures
        ])

        st.dataframe(df_failures, use_container_width=True, hide_index=True)
    else:
        st.info("No failed requests recorded.")

    st.divider()

    # Top Paths Accessed Table
    if by_path:
        st.markdown("#### Top Paths Accessed")

        df_paths = pd.DataFrame([
            {
                'Path': row['path'],
                'Crawler': row['crawler'],
                'Status': row['http_status'],
                'Count': row['count']
            }
            for row in by_path
        ])

        st.dataframe(df_paths, use_container_width=True, hide_index=True)
    else:
        st.info("No path data available.")


def render_website_access_view(run):
    """Render the Website Access view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Website Access</h2>", unsafe_allow_html=True)

    checks = fetch_website_checks_for_run(run['run_id'])

    if checks:
        # Parse result data to count status categories
        publicly_accessible = 0
        blocked_error = 0
        poorly_extractable = 0

        for check in checks:
            result = check['result'] or 'unknown'
            if result == 'publicly_accessible':
                publicly_accessible += 1
            elif result in ('blocked_by_robots', 'http_error_4xx'):
                blocked_error += 1
            elif result == 'poorly_extractable':
                poorly_extractable += 1

        total_checks = len(checks)

        # Display metric cards
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Publicly Accessible",
                publicly_accessible,
                f"{publicly_accessible/total_checks:.1%}" if total_checks > 0 else "0%"
            )

        with col2:
            st.metric(
                "Blocked/Error",
                blocked_error,
                f"{blocked_error/total_checks:.1%}" if total_checks > 0 else "0%"
            )

        with col3:
            st.metric(
                "Poorly Extractable",
                poorly_extractable,
                f"{poorly_extractable/total_checks:.1%}" if total_checks > 0 else "0%"
            )

        with col4:
            st.metric(
                "Total Checks",
                total_checks
            )

        # Display table with website check details
        st.markdown("#### Website Check Details")

        df_checks = pd.DataFrame([
            {
                'URL': c['striim_url'],
                'Crawler': c['crawler'],
                'Robots': c['robots_allowed'] if c['robots_allowed'] is not None else 'Unknown',
                'HTTP': c['http_status'],
                'Noindex': c['noindex'] if c['noindex'] is not None else 'Unknown',
                'Result': c['result'] or 'Unknown'
            }
            for c in checks
        ])

        st.dataframe(df_checks, use_container_width=True, hide_index=True)

        # Display result summary bar chart
        st.markdown("#### Result Summary")

        crawler_results = fetch_website_checks_by_crawler(run['run_id'])
        if crawler_results:
            df_summary = pd.DataFrame([
                {
                    'Crawler': r['crawler'],
                    'Result': r['result'] or 'Unknown',
                    'Count': r['count']
                }
                for r in crawler_results
            ])

            fig = px.bar(
                df_summary,
                x='Crawler',
                y='Count',
                color='Result',
                barmode='group',
                labels={'Count': 'Number of Checks', 'Crawler': 'Crawler Type'}
            )
            fig.update_layout(
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No website check data available yet. Run evaluations to see website access information.")


def render_implementation_steps(steps_json):
    """Render implementation steps from JSON."""
    if not steps_json:
        st.info("No implementation steps available.")
        return

    try:
        if isinstance(steps_json, str):
            steps = json.loads(steps_json)
        else:
            steps = steps_json

        if not isinstance(steps, list):
            st.info("Invalid implementation steps format.")
            return

        for i, raw_step in enumerate(steps, 1):
            # Article recs store dict steps, social media recs store
            # plain strings; normalize both to one shape.
            step = normalize_implementation_step(raw_step, i)

            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.caption(f"**{i}. {step['step']}**")
                if step['notes']:
                    st.caption(f"__{step['notes']}__")
            with col2:
                if step['effort']:
                    effort_color = get_effort_color(step['effort'])
                    st.caption(f"<span style='color: {effort_color}; font-weight: 600;'>**{step['effort']}**</span>", unsafe_allow_html=True)
            with col3:
                if step['owner']:
                    st.caption(f"_{step['owner']}_")
    except json.JSONDecodeError:
        st.error("Failed to parse implementation steps JSON.")
    except Exception as e:
        st.error(f"Error rendering steps: {str(e)}")


def render_recommendations_view(run):
    """Render the Recommendations management view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Recommendations</h2>", unsafe_allow_html=True)

    # Status filter
    col1, col2 = st.columns([2, 4])
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All For Approval", "Draft", "Pending Approval", "Pending Publish", "Edited"],
            key="rec_status_filter"
        )

    recommendations = fetch_recommendations_for_approval(run['run_id'])

    if not recommendations:
        st.info("No recommendations found for this run.")
        return

    # Filter by status
    filtered_recs = recommendations
    if status_filter == "Draft":
        filtered_recs = [r for r in recommendations if r['status'] == 'draft']
    elif status_filter == "Pending Approval":
        filtered_recs = [r for r in recommendations if r['status'] == 'pending_approval']
    elif status_filter == "Pending Publish":
        filtered_recs = [r for r in recommendations if r['status'] == 'pending_publish']
    elif status_filter == "Edited":
        filtered_recs = [r for r in recommendations if r['status'] == 'edited']

    if not filtered_recs:
        st.info(f"No recommendations with status: {status_filter}")
        return

    # Display recommendations
    st.markdown(f"#### {len(filtered_recs)} Recommendation(s)")

    # Status color mapping
    status_colors = {
        'draft': '',
        'pending_approval': '',
        'pending_publish': '',
        'edited': '',
        'approved': '',
        'rejected': '',
        'implemented': ''
    }

    evidence_by_rec = fetch_recommendation_evidence_bulk([r['id'] for r in filtered_recs])

    for rec in filtered_recs:
        evidence = evidence_by_rec.get(rec['id'])

        with st.container(border=True):
            # Header with status badge, platform badge, and priority
            col1, col2, col3 = st.columns([2.5, 1, 1])

            with col1:
                status_badge = status_colors.get(rec['status'], '❓')
                status_label = rec['status'].replace('_', ' ').title()
                # Display platform badge if platform exists
                platform = rec['platform'] if 'platform' in rec.keys() else None
                platform_badge = get_platform_badge(platform)
                if platform_badge:
                    st.markdown(f"**{status_label}** {platform_badge}", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{status_label}**")

            with col2:
                priority_num = rec['priority'] or 0
                st.markdown(f"**Priority:** {priority_num}/10")

            with col3:
                effort_num = rec['estimated_effort'] or 0
                effort_label = EFFORT_LABELS.get(effort_num, 'Unknown')
                effort_color = get_effort_color(effort_num)
                st.markdown(f"<span style='color: {effort_color}; font-weight: 600;'>**Effort:** {effort_label}</span>", unsafe_allow_html=True)

            st.divider()

            # Problem and Action
            st.markdown(f"**Problem:** {rec['problem']}")
            st.markdown(f"**Recommended Action:** {rec['recommended_action']}")

            # Evidence summary
            if rec['evidence_summary']:
                st.markdown(f"**Evidence:** {rec['evidence_summary']}")

            # Gap context
            if evidence:
                st.markdown(f"**Gap Context:** {evidence['topic']} - {evidence['gap_type'].title()}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.caption(f"Striim Visibility: {evidence['striim_visibility']:.1%}")
                with col2:
                    st.caption(f"Competitor ({evidence['top_competitor_name']}): {evidence['top_competitor_visibility']:.1%}")
                with col3:
                    st.caption(f"Confidence: {evidence['confidence'].title()}")

            # Affected pages
            if rec['affected_pages']:
                try:
                    affected = json.loads(rec['affected_pages'])
                    if affected:
                        st.markdown("**Affected Pages:**")
                        for page in affected[:5]:  # Show first 5
                            st.caption(f"- {page}")
                        if len(affected) > 5:
                            st.caption(f"... and {len(affected) - 5} more")
                except (json.JSONDecodeError, TypeError):
                    st.caption(f"Affected Pages: {rec['affected_pages'][:100]}")

            # Implementation steps - expandable section
            impl_steps = rec['implementation_steps'] if 'implementation_steps' in rec.keys() else None
            if impl_steps:
                with st.expander("Implementation Steps", expanded=False):
                    render_implementation_steps(impl_steps)

            # Action buttons
            st.divider()
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("Edit", key=f"edit_{rec['id']}", use_container_width=True):
                    st.session_state[f"edit_mode_{rec['id']}"] = not st.session_state.get(f"edit_mode_{rec['id']}", False)
                    st.rerun()

            with col2:
                if st.button("Approve", key=f"approve_{rec['id']}", use_container_width=True):
                    try:
                        from aeo_eval.storage.sqlite_store import SQLiteStore
                        store = SQLiteStore(_db_path())
                        store.update_recommendation_status(
                            rec['id'],
                            'approved',
                            approved_by='dashboard_user'
                        )
                        st.success("Recommendation approved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to approve: {str(e)}")

            with col3:
                if st.button("Reject", key=f"reject_{rec['id']}", use_container_width=True):
                    st.session_state[f"reject_mode_{rec['id']}"] = not st.session_state.get(f"reject_mode_{rec['id']}", False)
                    st.rerun()

            with col4:
                if st.button("Details", key=f"details_{rec['id']}", use_container_width=True):
                    st.session_state[f"details_mode_{rec['id']}"] = not st.session_state.get(f"details_mode_{rec['id']}", False)
                    st.rerun()

            # Edit mode
            if st.session_state.get(f"edit_mode_{rec['id']}", False):
                st.markdown("##### Edit Recommendation")
                with st.form(f"edit_form_{rec['id']}"):
                    edited_problem = st.text_area(
                        "Problem",
                        value=rec['problem'],
                        key=f"problem_{rec['id']}"
                    )
                    edited_action = st.text_area(
                        "Recommended Action",
                        value=rec['recommended_action'],
                        key=f"action_{rec['id']}"
                    )
                    edited_priority = st.slider(
                        "Priority (1-10)",
                        1, 10,
                        value=rec['priority'] or 5,
                        key=f"priority_{rec['id']}"
                    )
                    edited_effort = st.select_slider(
                        "Estimated Effort",
                        options=[1, 2, 3],
                        value=rec['estimated_effort'] or 2,
                        format_func=lambda x: {1: 'Low', 2: 'Medium', 3: 'High'}.get(x, str(x)),
                        key=f"effort_{rec['id']}"
                    )

                    if st.form_submit_button("Save Changes"):
                        try:
                            from aeo_eval.storage.sqlite_store import SQLiteStore
                            import sqlite3
                            conn = sqlite3.connect(_db_path())
                            conn.execute("PRAGMA foreign_keys = ON")
                            conn.execute("""
                                UPDATE recommendations
                                SET problem = ?, recommended_action = ?, priority = ?, estimated_effort = ?, status = 'edited'
                                WHERE id = ?
                            """, (edited_problem, edited_action, edited_priority, edited_effort, rec['id']))
                            conn.commit()
                            conn.close()
                            st.success("Recommendation updated!")
                            st.session_state[f"edit_mode_{rec['id']}"] = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save: {str(e)}")

            # Reject mode
            if st.session_state.get(f"reject_mode_{rec['id']}", False):
                st.markdown("##### Reject Recommendation")
                with st.form(f"reject_form_{rec['id']}"):
                    reject_reason = st.text_area(
                        "Reason for rejection",
                        key=f"reject_reason_{rec['id']}"
                    )

                    if st.form_submit_button("Confirm Rejection"):
                        try:
                            from aeo_eval.storage.sqlite_store import SQLiteStore
                            store = SQLiteStore(_db_path())
                            store.update_recommendation_status(
                                rec['id'],
                                'rejected',
                                approved_by='dashboard_user',
                                review_notes=reject_reason
                            )
                            st.success("Recommendation rejected!")
                            st.session_state[f"reject_mode_{rec['id']}"] = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reject: {str(e)}")

            # Details mode
            if st.session_state.get(f"details_mode_{rec['id']}", False):
                st.markdown("##### Full Details")
                details_col1, details_col2 = st.columns(2)

                with details_col1:
                    st.caption(f"**ID:** {rec['id']}")
                    st.caption(f"**Gap ID:** {rec['gap_id']}")
                    st.caption(f"**Created:** {rec['created_timestamp']}")
                    if rec['approved_by']:
                        st.caption(f"**Approved By:** {rec['approved_by']}")
                    platform = rec['platform'] if 'platform' in rec.keys() else None
                    if platform:
                        st.caption(f"**Platform:** {platform.title()}")

                with details_col2:
                    if rec['measurement_plan']:
                        st.caption(f"**Measurement Plan:** {rec['measurement_plan']}")
                    if rec['suggested_owner']:
                        st.caption(f"**Suggested Owner:** {rec['suggested_owner']}")
                    if rec['review_notes']:
                        st.caption(f"**Review Notes:** {rec['review_notes']}")

                # Show full implementation steps in details view
                impl_steps = rec['implementation_steps'] if 'implementation_steps' in rec.keys() else None
                if impl_steps:
                    st.markdown("**Full Implementation Steps:**")
                    render_implementation_steps(impl_steps)

                # Show templates applied
                templates_applied = rec['templates_applied'] if 'templates_applied' in rec.keys() else None
                if templates_applied:
                    st.markdown("**Templates Applied:**")
                    try:
                        templates = json.loads(templates_applied)
                        for template_id in templates:
                            st.caption(f"- {template_id}")
                    except (json.JSONDecodeError, TypeError):
                        st.caption(f"Templates: {rec['templates_applied']}")


def render_cost_view():
    """Render the Cost Analysis view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Cost Analysis</h2>", unsafe_allow_html=True)

    st.markdown("""
    Track and analyze evaluation costs across runs and engines.
    """)

    # Daily budget status
    st.markdown("#### Daily Budget Status")
    budget_status = fetch_daily_budget_status()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Today's Cost", f"${budget_status['today_cost']:.2f}")
    with col2:
        st.metric("Daily Limit", f"${budget_status['daily_limit']:.2f}")
    with col3:
        remaining = budget_status['remaining']
        remaining_color = "" if remaining > 0 else "🔴"
        st.metric(f"{remaining_color} Remaining", f"${remaining:.2f}")
    with col4:
        percent_used = budget_status['percent_used']
        st.metric("Budget Used", f"{percent_used:.1f}%")

    st.divider()

    # Settings section
    with st.expander("Cost Limit Settings", expanded=False):
        st.markdown("#### Adjust Token & Cost Limits")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Daily Cost Limit**")
            daily_limit = st.number_input(
                "Maximum spend per day ($)",
                min_value=1.0,
                max_value=10000.0,
                value=float(config.general.cost_limit_per_day),
                step=5.0,
                help="Maximum total cost allowed per calendar day",
                key="daily_cost_limit"
            )

        with col2:
            st.markdown("**Cost Limit Per Run**")
            run_limit = st.number_input(
                "Maximum spend per run ($)",
                min_value=1.0,
                max_value=1000.0,
                value=float(config.general.cost_limit_per_run),
                step=1.0,
                help="Maximum cost allowed for a single evaluation run",
                key="run_cost_limit"
            )

        # Save button
        if st.button("Save Limits", use_container_width=True):
            try:
                # Update config in memory
                config.general.cost_limit_per_day = daily_limit
                config.general.cost_limit_per_run = run_limit

                # Write to config file
                config_path = PROJECT_ROOT / "config.yaml"
                with open(config_path, "r") as f:
                    config_data = yaml.safe_load(f) or {}

                if "general" not in config_data:
                    config_data["general"] = {}

                config_data["general"]["cost_limit_per_day"] = daily_limit
                config_data["general"]["cost_limit_per_run"] = run_limit

                with open(config_path, "w") as f:
                    yaml.dump(config_data, f, default_flow_style=False)

                st.success(f"✓ Limits saved!\n- Daily: ${daily_limit:.2f}\n- Per Run: ${run_limit:.2f}")
            except Exception as e:
                st.error(f"Failed to save limits: {str(e)}")

    st.divider()

    all_runs = fetch_all_runs()

    if not all_runs:
        st.info("No runs available yet. Run evaluations to see cost data.")
        return

    # Summary metrics
    st.markdown("#### Overall Cost Summary")

    total_cost = sum(r['cost'] or 0 for r in all_runs)
    total_prompts = sum(r['num_prompts'] for r in all_runs)
    avg_cost_per_prompt = (total_cost / total_prompts) if total_prompts > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Cost (All Runs)", f"${total_cost:.2f}")
    with col2:
        st.metric("Total Prompts", total_prompts)
    with col3:
        st.metric("Avg Cost/Prompt", f"${avg_cost_per_prompt:.4f}")
    with col4:
        st.metric("Number of Runs", len(all_runs))

    st.divider()

    # Cost by engine
    st.markdown("#### Cost by Engine")

    engine_costs = {}
    engine_prompts = {}
    for run in all_runs:
        engine = run['engine']
        if engine not in engine_costs:
            engine_costs[engine] = 0
            engine_prompts[engine] = 0
        engine_costs[engine] += run['cost'] or 0
        engine_prompts[engine] += run['num_prompts']

    engine_data = []
    for engine in sorted(engine_costs.keys()):
        cost = engine_costs[engine]
        prompts = engine_prompts[engine]
        avg_per_prompt = (cost / prompts) if prompts > 0 else 0
        engine_data.append({
            'Engine': engine,
            'Total Cost': cost,
            'Total Prompts': prompts,
            'Avg Cost/Prompt': avg_per_prompt,
            'Num Runs': sum(1 for r in all_runs if r['engine'] == engine)
        })

    df_engines = pd.DataFrame(engine_data)

    col1, col2 = st.columns(2)
    with col1:
        st.dataframe(df_engines, use_container_width=True, hide_index=True)

    with col2:
        if not df_engines.empty:
            fig = go.Figure(data=[go.Pie(
                labels=df_engines['Engine'],
                values=df_engines['Total Cost'],
                marker=dict(
                    colors=['#0369a1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'][:len(df_engines)]
                ),
                textposition='inside',
                textinfo='label+percent'
            )])
            fig.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Cost by topic
    st.markdown("#### Cost by Topic")

    topic_costs = fetch_cost_by_topic()

    if topic_costs:
        df_topics = pd.DataFrame([
            {
                'Topic': t['topic'] or 'Unknown',
                'Num Runs': t['num_runs'],
                'Total Cost': f"${t['total_cost']:.4f}" if t['total_cost'] else "$0.00",
                'Total Prompts': t['total_prompts'],
                'Avg Cost/Run': f"${t['avg_cost_per_run']:.4f}" if t['avg_cost_per_run'] else "$0.00"
            }
            for t in topic_costs
        ])

        st.dataframe(df_topics, use_container_width=True, hide_index=True)
    else:
        st.info("No topic-level cost data available yet.")

    st.divider()

    # Cost trend over time
    st.markdown("#### Cost Trend (Last 30 Days)")
    cost_trends = fetch_cost_trends(30)

    if cost_trends:
        df_costs = pd.DataFrame([
            {
                'Date': datetime.fromisoformat(t['timestamp']).date(),
                'Cost': t['cost'] or 0,
                'Engine': t['engine'],
                'Prompts': t['num_prompts']
            }
            for t in cost_trends
        ])

        fig = go.Figure()
        for engine in sorted(df_costs['Engine'].unique()):
            engine_data = df_costs[df_costs['Engine'] == engine]
            fig.add_trace(go.Scatter(
                x=engine_data['Date'],
                y=engine_data['Cost'],
                mode='lines+markers',
                name=engine,
                line=dict(width=2),
                marker=dict(size=6)
            ))

        fig.update_layout(
            hovermode='x unified',
            height=450,
            margin=dict(l=0, r=0, t=0, b=0),
            template='plotly_white',
            yaxis_title='Cost ($)',
            xaxis_title='Date',
            legend=dict(x=0.01, y=0.99)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No cost trend data available yet.")

    st.divider()

    # Detailed run costs
    st.markdown("#### All Runs - Detailed Cost Breakdown")

    df_runs = pd.DataFrame([
        {
            'Run ID': r['run_id'][-8:],
            'Timestamp': datetime.fromisoformat(r['timestamp']).strftime('%Y-%m-%d %H:%M'),
            'Engine': r['engine'],
            'Prompts': r['num_prompts'],
            'Total Cost': f"${r['cost']:.4f}" if r['cost'] else "$0.00",
            'Cost/Prompt': f"${(r['cost'] / r['num_prompts']):.4f}" if r['num_prompts'] > 0 else "$0.00",
            'Duration (s)': r['duration_seconds'] or 0
        }
        for r in all_runs
    ])

    st.dataframe(df_runs, use_container_width=True, hide_index=True)


def render_module6_checks_view():
    """Render the Module 6 (Website Accessibility) checks independent view."""
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Website and Crawler Accessibility Checks</h2>", unsafe_allow_html=True)

    st.markdown("""
    Module 6 checks whether important Striim pages are accessible to AI crawlers,
    including robots.txt rules, HTTP status, extractability, and llms.txt coverage.
    Run checks independently or review historical results.
    """)

    # Control section
    with st.expander("Run New Module 6 Check", expanded=False):
        st.markdown("##### Configuration")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Pages to Check**")
            pages_default = config.evaluation.important_striim_pages
            pages_input = st.text_area(
                "Enter URLs (one per line):",
                value="\n".join(pages_default),
                height=100,
                key="module6_pages"
            )
            pages = [p.strip() for p in pages_input.strip().split("\n") if p.strip()]

        with col2:
            st.markdown("**Crawlers to Simulate**")
            crawlers_default = config.evaluation.crawlers
            crawlers_input = st.text_area(
                "Enter crawler user-agents (one per line):",
                value="\n".join(crawlers_default),
                height=100,
                key="module6_crawlers"
            )
            crawlers = [c.strip() for c in crawlers_input.strip().split("\n") if c.strip()]

        if st.button("Run Module 6 Checks", type="primary", use_container_width=True):
            with st.spinner(f"Running checks on {len(pages)} pages for {len(crawlers)} crawlers..."):
                result = run_module6_standalone(pages, crawlers)

                if result["success"]:
                    st.success(
                        f"✓ Module 6 complete! Run ID: {result['run_id'][-12:]} | "
                        f"{result['num_checks']} checks stored"
                    )
                    st.rerun()
                else:
                    st.error(f"Module 6 failed: {result.get('error', 'Unknown error')}")

    st.divider()

    # Results section
    st.markdown("#### Recent Results")

    # Get all checks
    all_checks = fetch_all_module6_checks()

    if all_checks:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        publicly_accessible = sum(1 for c in all_checks if c['result'] == 'publicly_accessible')
        blocked_error = sum(1 for c in all_checks if c['result'] in ('blocked_by_robots', 'http_error_4xx', 'http_error_5xx'))
        poorly_extractable = sum(1 for c in all_checks if c['result'] == 'poorly_extractable')

        with col1:
            st.metric("Publicly Accessible", publicly_accessible)
        with col2:
            st.metric("Blocked/Error", blocked_error)
        with col3:
            st.metric("Poorly Extractable", poorly_extractable)
        with col4:
            st.metric("Total Checks", len(all_checks))

        st.divider()

        # Results table
        st.markdown("#### Check Details")

        df_checks = pd.DataFrame([
            {
                'URL': c['striim_url'],
                'Crawler': c['crawler'],
                'HTTP Status': c['http_status'] or 'N/A',
                'Robots': 'Allowed' if c['robots_allowed'] else ('Blocked' if c['robots_allowed'] is not None else 'Unknown'),
                'Noindex': 'Yes' if c['noindex'] else 'No',
                'Result': c['result'] or 'Unknown',
                'Check Time': datetime.fromisoformat(c['check_timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M') if c['check_timestamp'] else 'N/A'
            }
            for c in all_checks
        ])

        st.dataframe(df_checks, use_container_width=True, hide_index=True)

        st.divider()

        # Results by crawler
        st.markdown("#### Results by Crawler")

        crawler_results = {}
        for check in all_checks:
            crawler = check['crawler']
            result = check['result'] or 'unknown'
            if crawler not in crawler_results:
                crawler_results[crawler] = {}
            crawler_results[crawler][result] = crawler_results[crawler].get(result, 0) + 1

        df_crawlers = pd.DataFrame([
            {
                'Crawler': crawler,
                'Result': result,
                'Count': count
            }
            for crawler, results in crawler_results.items()
            for result, count in results.items()
        ])

        if not df_crawlers.empty:
            fig = px.bar(
                df_crawlers,
                x='Crawler',
                y='Count',
                color='Result',
                barmode='group',
                labels={'Count': 'Number of Checks', 'Crawler': 'Crawler Type'}
            )
            fig.update_layout(
                height=400,
                margin=dict(l=0, r=0, t=0, b=0),
                template='plotly_white'
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No Module 6 checks found. Run checks to see results.")


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="AEO Visibility Dashboard",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Custom CSS for visual polish
    st.markdown("""
    <style>
    /* Color tokens */
    :root {
        --primary: #1e40af;
        --success: #10b981;
        --warning: #1e40af;
        --alert: #ef4444;
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --border: #e2e8f0;
    }

    /* Dark gradient background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%) !important;
    }

    .stMainBlockContainer {
        background: transparent;
    }

    /* Animated grid pattern background */
    body::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image:
            radial-gradient(circle at 20% 50%, rgba(30, 64, 175, 0.15) 0%, transparent 50%),
            radial-gradient(circle at 80% 80%, rgba(16, 185, 129, 0.1) 0%, transparent 50%);
        pointer-events: none;
        z-index: 0;
    }

    /* Top bar/header area */
    [data-testid="stTopBar"] {
        background: rgba(255, 255, 255, 0.95) !important;
        backdrop-filter: blur(10px);
        box-shadow: 0 8px 32px rgba(30, 64, 175, 0.15);
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.98) !important;
        box-shadow: 0 8px 32px rgba(30, 64, 175, 0.1);
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        transition: all 0.2s ease;
    }

    [data-testid="stMetric"]:hover {
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        transform: translateY(-2px);
    }

    /* Container styling */
    [data-testid="stVerticalBlockBorderContainer"] {
        background: white;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
        padding: 1.5rem;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.75rem;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 1rem;
    }

    .stTabs [role="tab"] {
        border-radius: 10px;
        padding: 0.75rem 1.5rem !important;
        font-weight: 500;
        border: none;
        background: white;
        color: #64748b;
        transition: all 0.2s ease;
    }

    .stTabs [role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
        color: white;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
    }

    .stTabs [role="tab"]:hover {
        color: #1e40af;
    }

    /* Expanders */
    .streamlit-expander {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: white;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }

    /* Buttons */
    .stButton > button {
        border-radius: 10px;
        font-weight: 500;
        border: 1px solid #e2e8f0;
        transition: all 0.2s ease;
        background: white;
        color: #475569;
    }

    .stButton > button:hover {
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        border-color: #1e40af;
        color: #1e40af;
    }

    /* Configure & Run button - always blue */
    .stButton button:has-text("Configure & Run"),
    [data-testid="stBaseButton"]:has-text("Configure & Run") {
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3) !important;
        border: none !important;
    }

    .stButton button:has-text("Configure & Run"):hover,
    [data-testid="stBaseButton"]:has-text("Configure & Run"):hover {
        background: linear-gradient(135deg, #1e3a8a 0%, #172554 100%) !important;
        box-shadow: 0 6px 16px rgba(30, 64, 175, 0.4) !important;
        color: white !important;
    }

    /* Fallback - style all buttons in the last column if has Configure & Run text */
    .stColumn:last-child .stButton button {
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3) !important;
        border: none !important;
    }

    .stColumn:last-child .stButton button:hover {
        background: linear-gradient(135deg, #1e3a8a 0%, #172554 100%) !important;
        box-shadow: 0 6px 16px rgba(30, 64, 175, 0.4) !important;
        color: white !important;
    }

    /* Navigation buttons */
    .stButton[key="nav_dashboard"] > button,
    .stButton[key="nav_cost"] > button,
    .stButton[key="nav_module6"] > button {
        background: white;
        border: 2px solid #e2e8f0;
        color: #475569;
        font-weight: 600;
        padding: 0.75rem 1.5rem;
    }

    .stButton[key="nav_dashboard"] > button:hover,
    .stButton[key="nav_cost"] > button:hover,
    .stButton[key="nav_module6"] > button:hover {
        border-color: #1e40af;
        color: #1e40af;
        box-shadow: 0 2px 8px rgba(30, 64, 175, 0.1);
    }

    /* Text styling - keep dark in header, light everywhere else */
    h1, h2, h3 {
        color: #ffffff;
        font-weight: 600;
    }

    h1 {
        font-size: 2rem;
        letter-spacing: -0.5px;
    }

    h2 {
        font-size: 1.5rem;
        margin: 2rem 0 1rem 0;
    }

    h5 {
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    /* Radio buttons - blue theme */
    .stRadio {
        color: #ffffff !important;
    }

    .stRadio * {
        color: #ffffff !important;
    }

    .stRadio > div {
        color: #ffffff !important;
    }

    .stRadio > div > label {
        color: #ffffff !important;
    }

    .stRadio > div > div > label {
        color: #ffffff !important;
    }

    .stRadio label {
        color: #ffffff !important;
    }

    /* Radio button color - blue theme */
    .stRadio input[type="radio"] {
        accent-color: #1e40af !important;
    }

    input[type="radio"] {
        accent-color: #1e40af !important;
    }

    [type="radio"] {
        accent-color: #1e40af !important;
    }

    /* Override Baseweb component colors */
    [data-testid="stRadio"] * {
        color: #ffffff !important;
    }

    [data-testid="stSlider"] * {
        color: #ffffff !important;
    }

    /* Baseweb slider and radio elements */
    div[class*="Slider"] {
        accent-color: #1e40af !important;
    }

    div[class*="Radio"] {
        accent-color: #1e40af !important;
    }

    /* Override all orange (#f59e0b) with blue (#1e40af) */
    [style*="#f59e0b"],
    [style*="rgb(245, 158, 11)"],
    [style*="rgba(245, 158, 11"] {
        --primary: #1e40af !important;
        accent-color: #1e40af !important;
    }

    /* Force blue on all interactive elements in config section */
    [data-testid="stRadio"] svg,
    [data-testid="stSlider"] [role="slider"],
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        color: #1e40af !important;
    }

    /* Streamlit slider track and thumb */
    [role="slider"] {
        accent-color: #1e40af !important;
    }

    /* Override any default Streamlit primary color (orange) with blue */
    div, span, button, input, [role*="slider"], [role*="radio"] {
        --streamlit-primary: #1e40af !important;
    }

    /* Target Baseweb Radio component - override orange fill */
    [data-testid="stRadio"] svg circle {
        fill: #1e40af !important;
    }

    [data-testid="stRadio"] [role="radio"] {
        accent-color: #1e40af !important;
    }

    /* Target Baseweb Slider - override orange track */
    [data-testid="stSlider"] [role="slider"] {
        accent-color: #1e40af !important;
    }

    [data-testid="stSlider"] input[type="range"] {
        accent-color: #1e40af !important;
    }

    /* Override inline styles with orange */
    [style*="f59e0b"] {
        color: #1e40af !important;
        fill: #1e40af !important;
        background: #1e40af !important;
        border-color: #1e40af !important;
    }

    /* Slider styling */
    .stSlider {
        color: #ffffff !important;
    }

    .stSlider > label {
        color: #ffffff !important;
    }

    /* Slider thumb and track - blue theme */
    .stSlider [role="slider"] {
        accent-color: #1e40af !important;
    }

    /* Streamlit form elements accent color */
    [data-baseweb="select"] {
        accent-color: #1e40af !important;
    }

    [data-baseweb="input"] {
        accent-color: #1e40af !important;
    }

    /* All form elements should use blue accent */
    input[type="checkbox"],
    input[type="range"] {
        accent-color: #1e40af !important;
    }

    /* Text color - light by default, dark on light backgrounds */
    .stMainBlockContainer {
        color: #ffffff;
    }

    .stMainBlockContainer h1,
    .stMainBlockContainer h2,
    .stMainBlockContainer h3 {
        color: #ffffff;
    }

    /* Dark text on white cards and dataframes */
    [data-testid="stMetric"],
    [data-testid="stVerticalBlockBorderContainer"],
    .stDataFrame,
    [data-testid="stDataFrame"] {
        color: #0f172a !important;
    }

    [data-testid="stMetric"] *,
    [data-testid="stVerticalBlockBorderContainer"] *,
    .stDataFrame *,
    [data-testid="stDataFrame"] * {
        color: #0f172a !important;
    }

    /* Form labels */
    label {
        color: #cbd5e1;
        font-weight: 500;
    }

    /* Input fields text */
    input, textarea, select {
        color: #ffffff !important;
    }

    /* Table text */
    table, th, td {
        color: #0f172a !important;
    }

    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 2rem 0;
    }

    /* Form elements */
    .stSelectbox, .stSlider, .stTextInput, .stTextArea, .stRadio {
        border-radius: 10px;
    }

    /* Selectbox styling */
    .stSelectbox [data-baseweb="select"] {
        background: white;
        border-radius: 10px;
    }

    .stSelectbox label {
        color: #cbd5e1;
        font-weight: 500;
    }

    /* Info/Warning/Error messages */
    .stAlert {
        border-radius: 10px;
        border: 1px solid;
    }

    .stSuccess {
        background: #f0fdf4;
        border-color: #10b981;
        color: #166534;
    }

    .stInfo {
        background: #eff6ff;
        border-color: #1e40af;
        color: #0c2340;
    }

    .stWarning {
        background: #fffbeb;
        border-color: #f59e0b;
        color: #92400e;
    }

    .stError {
        background: #fef2f2;
        border-color: #ef4444;
        color: #7f1d1d;
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
    }

    /* Navigation pills style */
    .stSegmentedControl {
        gap: 0.75rem;
    }

    [data-baseweb="segmented-control"] {
        border-radius: 10px;
    }

    /* Hide sidebar */
    [data-testid="stSidebar"] {
        display: none !important;
    }

    /* Top navigation styling */
    .nav-container {
        display: flex;
        gap: 0.75rem;
        margin-bottom: 2rem;
        flex-wrap: wrap;
    }

    .nav-pill {
        padding: 0.75rem 1.5rem;
        border-radius: 12px;
        border: 2px solid #e2e8f0;
        background: white;
        color: #475569;
        font-weight: 500;
        font-size: 0.95rem;
        cursor: pointer;
        transition: all 0.2s ease;
    }

    .nav-pill:hover {
        border-color: #1e40af;
        color: #1e40af;
        box-shadow: 0 2px 8px rgba(30, 64, 175, 0.1);
    }

    .nav-pill.active {
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
        border-color: #1e40af;
        color: white;
        box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3);
    }

    /* Configure button */
    .config-button {
        padding: 0.875rem 2rem;
        border-radius: 10px;
        border: none;
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
        color: white;
        font-weight: 600;
        font-size: 1rem;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(30, 64, 175, 0.4);
        float: right;
        margin-bottom: 1.5rem;
    }

    .config-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(30, 64, 175, 0.5);
    }

    </style>
    """, unsafe_allow_html=True)

    # Initialize view mode in session state
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "Dashboard"

    # Fetch all runs for run selection
    all_runs = fetch_all_runs()

    if not all_runs:
        st.error("No evaluation runs found. Run the pipeline to generate data.")
        st.stop()

    # Initialize run selector in session state
    if "selected_run_idx" not in st.session_state:
        st.session_state.selected_run_idx = 0

    # Header with title
    st.title("AEO Visibility")

    # Get the selected run
    run = fetch_run_by_id(all_runs[st.session_state.selected_run_idx]['run_id'])

    # Top navigation pills - simple and clean
    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
    with col1:
        if st.button("Dashboard", key="nav_dashboard", use_container_width=True):
            st.session_state.view_mode = "Dashboard"
            st.rerun()
    with col2:
        if st.button("Cost Analysis", key="nav_cost", use_container_width=True):
            st.session_state.view_mode = "Cost"
            st.rerun()
    with col3:
        if st.button("Module 6 Checks", key="nav_module6", use_container_width=True):
            st.session_state.view_mode = "Module 6 Checks"
            st.rerun()
    with col4:
        st.markdown("")
    with col5:
        # Add custom HTML styling for the button
        st.markdown("""
        <style>
        div[data-testid="column"]:last-child button {
            background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%) !important;
            color: white !important;
            font-weight: 600 !important;
            box-shadow: 0 4px 12px rgba(30, 64, 175, 0.3) !important;
            border: none !important;
        }
        div[data-testid="column"]:last-child button:hover {
            background: linear-gradient(135deg, #1e3a8a 0%, #172554 100%) !important;
            box-shadow: 0 6px 16px rgba(30, 64, 175, 0.4) !important;
        }
        </style>
        """, unsafe_allow_html=True)
        if st.button("Configure & Run", key="open_eval_config", use_container_width=True, help="Run a new evaluation"):
            st.session_state.show_eval_config = not st.session_state.get("show_eval_config", False)
            st.rerun()

    st.divider()

    # Cost view
    if st.session_state.view_mode == "Cost":
        render_cost_view()
        return

    # Module 6 Checks view
    if st.session_state.view_mode == "Module 6 Checks":
        render_module6_checks_view()
        return

    # Dashboard view (original)

    # Evaluation config modal (shown when button is clicked)
    if st.session_state.get("show_eval_config", False):
        with st.container(border=True):
            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown("#### Configure & Run New Evaluation")
            with col2:
                if st.button("✕ Close", key="close_eval_config", use_container_width=True):
                    st.session_state.show_eval_config = False
                    st.rerun()

            # Run selection
            run_options = [
                f"{r['run_id'][-8:]} • {datetime.fromisoformat(r['timestamp']).strftime('%Y-%m-%d %H:%M')} • {r['engine']}"
                for r in all_runs
            ]
            selected_idx = st.selectbox(
                "Select Run to View",
                range(len(run_options)),
                format_func=lambda i: run_options[i],
                key="run_selector_config",
                index=st.session_state.selected_run_idx
            )
            st.session_state.selected_run_idx = selected_idx
            run = fetch_run_by_id(all_runs[selected_idx]['run_id'])

            # Run details inline
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.caption(f"**Run Cost:** ${run['cost']:.2f}")
            with col2:
                st.caption(f"**Prompts:** {run['num_prompts']}")
            with col3:
                cost_per_prompt = ((run['cost'] or 0) / run['num_prompts']) if run['num_prompts'] > 0 else 0
                st.caption(f"**Cost/Prompt:** ${cost_per_prompt:.4f}")
            with col4:
                st.caption(f"**Duration:** {run['duration_seconds'] or 0}s")

            st.divider()

            st.markdown("<div style='color: #ffffff; font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;'>Engine Selection</div>", unsafe_allow_html=True)
            engine_choice = st.radio(
                "Choose engine:",
                available_engines(),
                horizontal=True,
                help="Engines come from the provider registry",
                label_visibility="collapsed"
            )

            st.markdown("<div style='color: #ffffff; font-size: 1.1rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 1rem;'>Evaluation Parameters</div>", unsafe_allow_html=True)
            num_prompts = st.slider(
                "Number of prompts:",
                1, 240, 5,
                help="How many questions to evaluate",
                label_visibility="collapsed"
            )

            all_prompts = load_prompts(str(config.general.question_json_path))
            topic_options = ["All Topics"] + sorted({p.topic for p in all_prompts})
            priority_options = ["All Priorities", "high", "medium", "low"]

            col1, col2 = st.columns(2)
            with col1:
                topic_filter = st.selectbox(
                    "Topic (optional):",
                    topic_options,
                    key="run_topic"
                )
            with col2:
                priority_filter = st.selectbox(
                    "Priority (optional):",
                    priority_options,
                    key="run_priority"
                )

            eval_job_running = (
                st.session_state.get("eval_job") is not None
                and st.session_state.eval_job["thread"].is_alive()
            )
            if st.button(
                "Start Evaluation", type="primary", use_container_width=True,
                disabled=eval_job_running,
            ):
                # Run the pipeline in a background thread so the page
                # keeps rendering; a 60-question run takes many minutes
                # and a blocking spinner froze the whole dashboard.
                job = {
                    "engine": engine_choice,
                    "num_prompts": num_prompts,
                    "started": datetime.now().isoformat(),
                    "result": None,
                }

                def _run_in_background(job=job, engine=engine_choice,
                                       n=num_prompts, topic=topic_filter,
                                       priority=priority_filter):
                    job["result"] = run_evaluation(
                        engine_name=engine,
                        num_prompts=n,
                        topic=topic,
                        priority=priority,
                    )

                thread = threading.Thread(target=_run_in_background, daemon=True)
                thread.start()
                # Store the same dict the thread mutates, so job["result"]
                # is visible here once the thread finishes.
                job["thread"] = thread
                st.session_state.eval_job = job
                st.rerun()

        st.divider()

    st.divider()

    # Live progress for a background evaluation run.
    if st.session_state.get("eval_job"):
        job = st.session_state.eval_job
        if job["thread"].is_alive():
            conn = get_db_connection()
            try:
                progress = fetch_run_progress(conn, job["started"])
            finally:
                conn.close()
            st.info(
                f"⏳ Evaluation running ({job['engine']}, "
                f"{job['num_prompts']} questions) — "
                + describe_progress(progress, job["num_prompts"])
            )
            time.sleep(4)
            st.rerun()
        else:
            result = job.get("result") or {}
            if "error" in result:
                st.error(f"Evaluation failed: {result['error']}")
            else:
                st.success(
                    f"✓ Evaluation complete! Run ID: "
                    f"{result.get('run_id', 'unknown')[-8:]}"
                )
            del st.session_state["eval_job"]

    # Get the run for display (after config panel handles selection)
    run = fetch_run_by_id(all_runs[st.session_state.selected_run_idx]['run_id'])

    # VISIBILITY METRICS - MAIN FOCUS
    st.markdown("<h2 style='color: #ffffff; margin-bottom: 1.5rem; font-weight: 600;'>Visibility Metrics</h2>", unsafe_allow_html=True)

    metrics = fetch_metrics_for_run(run['run_id'])

    if metrics:
        overall = next((m for m in metrics if m['dimension'] == 'overall'), None)

        if overall:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                mention_rate = overall['striim_mention_rate'] or 0
                st.metric(
                    "Mention Rate",
                    f"{mention_rate:.1%}",
                    f"{overall['num_responses']} responses"
                )

            with col2:
                avg_pos = overall['striim_avg_position']
                subtext = f"Avg Position: {avg_pos:.1f}" if avg_pos is not None else "Avg Position: —"
                top3_rate = overall['striim_top3_rate'] or 0
                st.metric(
                    "Top-3 Placement",
                    f"{top3_rate:.1%}",
                    subtext
                )

            with col3:
                citation_rate = overall['striim_citation_rate'] or 0
                recommendation_rate = overall['striim_recommendation_rate'] or 0
                st.metric(
                    "Citation Rate",
                    f"{citation_rate:.1%}",
                    f"Recommendation: {recommendation_rate:.1%}"
                )

            with col4:
                competitors = json.loads(overall['competitor_mention_rates'] or '{}')
                if competitors:
                    top_competitor = max(competitors.items(), key=lambda x: x[1])
                    st.metric(
                        "Top Competitor",
                        f"{top_competitor[0]}",
                        f"{top_competitor[1]:.1%}"
                    )

    st.divider()

    # Tabs for deeper analysis
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Gaps & Recommendations",
        "Citation Analysis",
        "Run Comparison",
        "Trends & Details",
        "Recommendations Management"
    ])

    with tab1:
        render_gaps_recommendations_view(run)

    with tab2:
        render_citation_analysis_view(run)

    with tab3:
        render_comparison_view(all_runs)

    with tab4:
        render_visibility_metrics_view(run)

    with tab5:
        render_recommendations_view(run)


if __name__ == "__main__":
    main()
