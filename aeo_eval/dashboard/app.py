"""Streamlit dashboard for AEO Visibility Platform."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from aeo_eval.config import config
from aeo_eval.data.prompt_loader import load_prompts
from aeo_eval.engine.factory import available_engines, create_engine
from aeo_eval.runner.evaluator import RunOptions
from aeo_eval.orchestrator import AEOPipelineOrchestrator

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
        topic = None if topic in (None, "All Topics") else topic
        persona = None if persona in (None, "All Personas") else persona
        priority = None if priority in (None, "All Priorities") else priority

        prompts = select_prompts(
            load_prompts(str(config.general.question_json_path)),
            topic=topic, priority=priority, limit=num_prompts,
        )
        if not prompts:
            return {"error": "No prompts found with selected filters"}

        # Initialize engine
        engine = create_engine(engine_name)

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
        orchestrator = AEOPipelineOrchestrator(engine, pipeline_config)
        result = orchestrator.run_full_pipeline(prompts, run_options)

        return result
    except Exception as e:
        return {"error": str(e)}


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


def fetch_website_checks_for_run(run_id):
    """Fetch website checks for a run."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT wc.* FROM website_checks wc ORDER BY wc.check_timestamp DESC LIMIT 100")
    checks = cursor.fetchall()
    conn.close()
    return checks


def fetch_website_checks_by_crawler(run_id=None):
    """Fetch website checks grouped by crawler and result."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT crawler, result, COUNT(*) as count FROM website_checks GROUP BY crawler, result ORDER BY crawler")
    results = cursor.fetchall()
    conn.close()
    return results


def fetch_crawler_logs_summary():
    """Fetch crawler logs summary with request and error counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT crawler, COUNT(*) as request_count, SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) as error_count FROM crawler_logs GROUP BY crawler ORDER BY request_count DESC")
    summary = cursor.fetchall()
    conn.close()
    return summary


def fetch_crawler_logs_by_path():
    """Fetch crawler logs grouped by path, crawler, and status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT path, crawler, http_status, COUNT(*) as count FROM crawler_logs GROUP BY path, crawler, http_status ORDER BY count DESC LIMIT 50")
    results = cursor.fetchall()
    conn.close()
    return results


def fetch_crawler_log_failures():
    """Fetch failed requests from crawler logs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, host, path, crawler, http_status, response_time_ms FROM crawler_logs WHERE http_status >= 400 ORDER BY timestamp DESC LIMIT 50")
    failures = cursor.fetchall()
    conn.close()
    return failures


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


def fetch_recommendation_evidence(rec_id):
    """Fetch evidence details for a recommendation (gap information, affected pages)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.gap_id, r.problem, r.evidence_summary, r.affected_pages,
               g.topic, g.gap_type, g.striim_visibility, g.top_competitor_visibility,
               g.top_competitor_name, g.priority as gap_priority, g.confidence
        FROM recommendations r
        JOIN gaps g ON r.gap_id = g.id
        WHERE r.id = ?
    """, (rec_id,))
    evidence = cursor.fetchone()
    conn.close()
    return evidence


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
    """Render the Visibility Metrics view."""
    st.subheader("Visibility Metrics")

    metrics = fetch_metrics_for_run(run['run_id'])

    if metrics:
        overall = next((m for m in metrics if m['dimension'] == 'overall'), None)

        if overall:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "Mention Rate",
                    f"{overall['striim_mention_rate']:.1%}",
                    f"{overall['num_responses']} responses"
                )

            with col2:
                avg_pos = overall['striim_avg_position']
                subtext = f"Avg Position: {avg_pos:.1f}" if avg_pos is not None else "Avg Position: —"
                st.metric(
                    "Top-3 Placement",
                    f"{overall['striim_top3_rate']:.1%}",
                    subtext
                )

            with col3:
                st.metric(
                    "Citation Rate",
                    f"{overall['striim_citation_rate']:.1%}",
                    f"Recommendation: {overall['striim_recommendation_rate']:.1%}"
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


def render_gaps_recommendations_view(run):
    """Render the Gaps & Recommendations view."""
    st.subheader("Gaps & Recommendations")

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
                        st.markdown(f"**{rec['recommended_action'][:80]}...**")
                        st.caption(f"Priority: {rec['priority']}/10 | "
                                 f"Effort: {rec['estimated_effort']} pts")
                        st.caption(rec['problem'][:150] + "...")

                    with col2:
                        status_label = rec['status'].replace('_', ' ').title()
                        st.caption(f"{status_color.get(rec['status'], '?')} {status_label}")
        else:
            st.info("No recommendations match the selected filters.")
    else:
        st.info("No recommendations generated yet.")


def render_comparison_view(all_runs):
    """Render the Run Comparison view."""
    st.subheader("Run Comparison")

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
                'Responses': overall['num_responses']
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
    st.subheader("Citation Analysis")

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
    st.subheader("Request Logs")

    # Fetch logs data
    summary = fetch_crawler_logs_summary()
    by_path = fetch_crawler_logs_by_path()
    failures = fetch_crawler_log_failures()

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
    st.subheader("Website Access")

    checks = fetch_website_checks_for_run(run['run_id'])

    if checks:
        # Parse result data to count status categories
        publicly_accessible = 0
        blocked_error = 0
        poorly_extractable = 0

        for check in checks:
            result = check['result'] or 'unknown'
            if result == 'accessible':
                publicly_accessible += 1
            elif result in ('blocked', 'error'):
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


def render_recommendations_view(run):
    """Render the Recommendations management view."""
    st.subheader("Recommendations")

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

    for rec in filtered_recs:
        evidence = fetch_recommendation_evidence(rec['id'])

        with st.container(border=True):
            # Header with status badge and priority
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                status_badge = status_colors.get(rec['status'], '❓')
                status_label = rec['status'].replace('_', ' ').title()
                st.markdown(f"**{status_label}**")

            with col2:
                priority_num = rec['priority'] or 0
                st.markdown(f"**Priority:** {priority_num}/10")

            with col3:
                effort_num = rec['estimated_effort'] or 0
                effort_labels = {1: 'Low', 2: 'Medium', 3: 'High'}
                st.markdown(f"**Effort:** {effort_labels.get(effort_num, 'Unknown')}")

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

                with details_col2:
                    if rec['measurement_plan']:
                        st.caption(f"**Measurement Plan:** {rec['measurement_plan']}")
                    if rec['suggested_owner']:
                        st.caption(f"**Suggested Owner:** {rec['suggested_owner']}")
                    if rec['review_notes']:
                        st.caption(f"**Review Notes:** {rec['review_notes']}")


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="AEO Visibility Dashboard",
        page_icon="AEO",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("AEO Visibility Dashboard")

    # Sidebar: Run new evaluation and selection
    with st.sidebar:
        st.header("Evaluation Control")

        # Run new evaluation section
        with st.expander("Run New Evaluation", expanded=False):
            st.markdown("##### Engine Selection")
            engine_choice = st.radio(
                "Choose engine:",
                available_engines(),
                horizontal=True,
                help="Engines come from the provider registry"
            )

            st.markdown("##### Evaluation Parameters")
            num_prompts = st.slider(
                "Number of prompts:",
                1, 240, 5,
                help="How many questions to evaluate"
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

            if st.button("Start Evaluation", type="primary", use_container_width=True):
                with st.spinner(f"Running evaluation with {engine_choice}..."):
                    result = run_evaluation(
                        engine_name=engine_choice,
                        num_prompts=num_prompts,
                        topic=topic_filter,
                        priority=priority_filter
                    )

                    if "error" in result:
                        st.error(f"Evaluation failed: {result['error']}")
                    else:
                        st.success(f"✓ Evaluation complete! Run ID: {result.get('run_id', 'unknown')[-8:]}")
                        st.balloons()
                        st.rerun()

        st.divider()
        st.header("Run Selection")

        # Fetch all runs
        all_runs = fetch_all_runs()

        if not all_runs:
            st.error("No evaluation runs found. Run the pipeline to generate data.")
            st.stop()

        # Create run options with timestamps
        run_options = [
            f"{r['run_id'][-8:]} • {datetime.fromisoformat(r['timestamp']).strftime('%Y-%m-%d %H:%M')} • {r['engine']}"
            for r in all_runs
        ]

        selected_idx = st.selectbox(
            "Select a run:",
            range(len(run_options)),
            format_func=lambda i: run_options[i],
            help="Choose which evaluation run to analyze"
        )

        run = fetch_run_by_id(all_runs[selected_idx]['run_id'])

        st.divider()
        st.subheader("All Runs")
        st.dataframe(
            pd.DataFrame([
                {
                    'Run ID': r['run_id'][-8:],
                    'Timestamp': datetime.fromisoformat(r['timestamp']).strftime('%Y-%m-%d %H:%M'),
                    'Engine': r['engine'],
                    'Prompts': r['num_prompts'],
                    'Cost': f"${r['cost']:.2f}"
                }
                for r in all_runs
            ]),
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        with st.expander("Clear Runs", expanded=False):
            st.warning("This action cannot be undone!")

            delete_option = st.radio(
                "What would you like to delete?",
                ["Delete a specific run", "Delete all runs"],
                key="delete_option"
            )

            if delete_option == "Delete a specific run":
                run_to_delete = st.selectbox(
                    "Select run to delete:",
                    range(len(all_runs)),
                    format_func=lambda i: f"{all_runs[i]['run_id'][-8:]} • {datetime.fromisoformat(all_runs[i]['timestamp']).strftime('%Y-%m-%d %H:%M')} • {all_runs[i]['engine']}",
                    key="run_to_delete"
                )

                st.checkbox("I understand this cannot be undone", key="confirm_delete_single")

                if st.button("Delete Selected Run", type="secondary", use_container_width=True):
                    if st.session_state.get("confirm_delete_single", False):
                        try:
                            delete_run(all_runs[run_to_delete]['run_id'])
                            st.success(f"✓ Run {all_runs[run_to_delete]['run_id'][-8:]} deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete run: {str(e)}")
                    else:
                        st.error("Please check the confirmation box before deleting.")

            else:  # Delete all runs
                st.error(f"This will delete all {len(all_runs)} runs!")
                st.checkbox("I understand this cannot be undone and will delete ALL runs", key="confirm_delete_all")

                if st.button("Delete All Runs", type="secondary", use_container_width=True):
                    if st.session_state.get("confirm_delete_all", False):
                        try:
                            num_deleted = len(all_runs)
                            for run in all_runs:
                                delete_run(run['run_id'])
                            st.success(f"✓ All {num_deleted} runs deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete runs: {str(e)}")
                    else:
                        st.error("Please check the confirmation box before deleting.")

    # Run info header
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Run ID", run['run_id'][-8:])
    with col2:
        st.metric("Engine", run['engine'])
    with col3:
        st.metric("Cost", f"${run['cost']:.2f}")
    with col4:
        st.metric("Prompts", run['num_prompts'])
    with col5:
        run_time = datetime.fromisoformat(run['timestamp'])
        st.metric("Run Time", run_time.strftime("%m/%d %H:%M"))

    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Visibility Metrics",
        "Gaps & Recommendations",
        "Citation Analysis",
        "Run Comparison",
        "Website Access",
        "Request Logs",
        "Recommendations Management"
    ])

    with tab1:
        render_visibility_metrics_view(run)

    with tab2:
        render_gaps_recommendations_view(run)

    with tab3:
        render_citation_analysis_view(run)

    with tab4:
        render_comparison_view(all_runs)

    with tab5:
        render_website_access_view(run)

    with tab6:
        render_request_logs_view(run)

    with tab7:
        render_recommendations_view(run)


if __name__ == "__main__":
    main()
