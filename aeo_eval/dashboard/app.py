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
    tab1, tab2, tab3, tab4 = st.tabs([
        "Visibility Metrics",
        "Gaps & Recommendations",
        "Citation Analysis",
        "Run Comparison"
    ])

    with tab1:
        render_visibility_metrics_view(run)

    with tab2:
        render_gaps_recommendations_view(run)

    with tab3:
        render_citation_analysis_view(run)

    with tab4:
        render_comparison_view(all_runs)


if __name__ == "__main__":
    main()
