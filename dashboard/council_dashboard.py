"""
Council Analytics Dashboard — Marimo Notebook

This dashboard visualizes council deliberation results stored in Tower Iceberg.
It shows:
  - Deliberation history with confidence/quality trends
  - Agent performance comparisons
  - Phase distribution analysis
  - Topic domain breakdown

Run with: marimo edit dashboard/council_dashboard.py
"""

import marimo

__generated_with = "0.12.0"
app = marimo.App(width="full")


@app.cell
def _(mo: marimo.ui):
    """Dashboard header and controls."""
    mo.md(
        """
        # 🏛️ Council Analytics Dashboard

        Visualize AI deliberation results from the Council Tower Pipeline.
        """
    )
    return (mo,)


@app.cell
def _():
    """Load deliberation data from Tower Iceberg or local fallback."""
    import json
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Try Tower first, fall back to local
    try:
        import tower
        table = tower.tables("council_deliberations").load()
        df = table.to_polars().collect()
        data_mode = "Tower Iceberg"
    except Exception:
        # Load from local files
        import polars as pl
        data_dir = os.environ.get("COUNCIL_DATA_DIR", "./data")
        json_files = [
            os.path.join(data_dir, f)
            for f in sorted(os.listdir(data_dir))
            if f.endswith(".json")
        ]
        if json_files:
            records = []
            for fp in json_files:
                with open(fp) as f:
                    r = json.load(f)
                    records.append({
                        "topic": r.get("topic", ""),
                        "domain": r.get("domain", "general"),
                        "status": r.get("status", ""),
                        "quality_score": r.get("quality_score", 0),
                        "confidence_score": r.get("confidence_score", 0),
                        "num_posts": r.get("num_posts", 0),
                    })
            df = pl.DataFrame(records)
            data_mode = "Local JSON"
        else:
            # Demo data
            import polars as pl
            df = pl.DataFrame({
                "topic": [
                    "Should the Fed cut rates in Q3 2026?",
                    "Is NVIDIA overvalued at current levels?",
                    "Should Apple acquire a major AI startup?",
                ],
                "domain": ["finance", "finance", "strategy"],
                "status": ["LOCKED", "LOCKED", "LOCKED"],
                "quality_score": [0.78, 0.65, 0.82],
                "confidence_score": [0.78, 0.65, 0.82],
                "num_posts": [11, 11, 11],
            })
            data_mode = "Demo Data"

    data_mode
    return df, data_mode


@app.cell
def _(df, mo):
    """Summary metrics."""
    mo.md(f"**Data Source:** {data_mode} | **Total Deliberations:** {len(df)}")
    return


@app.cell
def _(df, mo):
    """Confidence and quality score visualization."""
    import plotly.express as px

    if len(df) > 0:
        fig = px.bar(
            df.to_pandas(),
            x="topic",
            y=["quality_score", "confidence_score"],
            title="Deliberation Quality & Confidence Scores",
            barmode="group",
            labels={"value": "Score", "topic": "Topic", "variable": "Metric"},
        )
        fig.update_layout(xaxis_tickangle=-30, height=400)
        mo.ui.plotly(fig)
    return (fig,)


@app.cell
def _(df, mo):
    """Domain distribution."""
    import plotly.express as px

    if len(df) > 0:
        domain_counts = df.group_by("domain").len().to_pandas()
        fig = px.pie(
            domain_counts,
            values="len",
            names="domain",
            title="Deliberations by Domain",
        )
        mo.ui.plotly(fig)
    return


@app.cell
def _(df, mo):
    """Posts per deliberation."""
    import plotly.express as px

    if len(df) > 0:
        fig = px.histogram(
            df.to_pandas(),
            x="num_posts",
            title="Posts per Deliberation",
            nbins=20,
        )
        mo.ui.plotly(fig)
    return


@app.cell
def _(df, mo):
    """Detailed deliberation table."""
    import polars as pl

    if len(df) > 0:
        styled = df.to_pandas()[["topic", "domain", "quality_score", "confidence_score", "num_posts"]]
        styled["quality_score"] = styled["quality_score"].round(2)
        styled["confidence_score"] = styled["confidence_score"].round(2)
        mo.ui.table(styled)
    return (styled,)


@app.cell
def _(mo):
    """Footer."""
    mo.md(
        """
        ---
        *Council Tower Pipeline — AI Deliberation Engine*
        *Powered by zhipu GLM-4 Plus | Tower Pipeline Orchestration*
        """
    )
    return


if __name__ == "__main__":
    app.run()
