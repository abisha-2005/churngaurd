import os
import io
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no GUI backend needed — we only save PNGs
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether
)

CHART_DIR = "models/report_charts"


def _safe_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _make_risk_distribution_chart(churn_df: pd.DataFrame, path: str):
    counts = churn_df["risk_level"].value_counts()
    order = ["Low Risk", "Medium Risk", "High Risk"]
    counts = counts.reindex(order).fillna(0)

    fig, ax = plt.subplots(figsize=(6, 4))
    bar_colors = ["#4caf50", "#ff9800", "#f44336"]
    ax.bar(counts.index, counts.values, color=bar_colors)
    ax.set_title("Customer Risk Distribution")
    ax.set_ylabel("Number of Customers")
    for i, v in enumerate(counts.values):
        ax.text(i, v + max(counts.values) * 0.01, str(int(v)), ha="center")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _make_revenue_at_risk_chart(churn_df: pd.DataFrame, path: str):
    df = churn_df.copy()
    df["monetary"] = _safe_num(df.get("monetary", 0))

    revenue_by_risk = df.groupby("risk_level")["monetary"].sum()
    order = ["Low Risk", "Medium Risk", "High Risk"]
    revenue_by_risk = revenue_by_risk.reindex(order).fillna(0)

    fig, ax = plt.subplots(figsize=(6, 4))
    bar_colors = ["#4caf50", "#ff9800", "#f44336"]
    ax.bar(revenue_by_risk.index, revenue_by_risk.values, color=bar_colors)
    ax.set_title("Revenue by Risk Level")
    ax.set_ylabel("Total Revenue (monetary)")
    for i, v in enumerate(revenue_by_risk.values):
        ax.text(i, v + max(revenue_by_risk.values) * 0.01, f"{v:,.0f}", ha="center")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _make_segment_chart(churn_df: pd.DataFrame, path: str):
    if "segment" not in churn_df.columns:
        return False

    counts = churn_df["segment"].value_counts()

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(counts.index, counts.values, color="#2196f3")
    ax.set_title("Customers by Segment")
    ax.set_xlabel("Number of Customers")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def _df_to_table(df: pd.DataFrame, max_rows=15):
    """Converts a dataframe to a reportlab Table, truncating long text and rows."""
    display_df = df.head(max_rows).copy()
    for col in display_df.columns:
        display_df[col] = display_df[col].astype(str).apply(lambda x: x[:40])

    data = [list(display_df.columns)] + display_df.values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def generate_pdf_report(
    churn_df: pd.DataFrame,
    explained_df: pd.DataFrame = None,
    notification_log_df: pd.DataFrame = None,
    model_metrics: dict = None,
    output_path: str = "models/retention_report.pdf",
) -> str:
    """
    Builds a full PDF report covering:
      - Model performance summary
      - Risk distribution chart
      - Revenue-at-risk vs total revenue chart
      - Segment breakdown chart
      - Top high-risk customers table (with reasons, if available)
      - Notification log table (if available)

    Charts are sized and flowed so multiple sections share a page instead of
    forcing a page break after every chart — keeps the report compact instead
    of leaving large blank areas on each page.

    Returns the path to the generated PDF.
    """
    os.makedirs(CHART_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    df = churn_df.copy()
    df["monetary"] = _safe_num(df.get("monetary", 0))

    risk_chart_path = os.path.join(CHART_DIR, "risk_distribution.png")
    revenue_chart_path = os.path.join(CHART_DIR, "revenue_at_risk.png")
    segment_chart_path = os.path.join(CHART_DIR, "segments.png")

    _make_risk_distribution_chart(df, risk_chart_path)
    _make_revenue_at_risk_chart(df, revenue_chart_path)
    has_segment_chart = _make_segment_chart(df, segment_chart_path)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], spaceAfter=6)
    heading_style = styles["Heading2"]
    normal_style = styles["Normal"]

    story = []

    # --- Cover / Summary ---
    story.append(Paragraph("Customer Retention & Churn Report", title_style))
    story.append(Spacer(1, 10))

    total_customers = len(df)
    high_risk_count = int((df["risk_level"] == "High Risk").sum()) if "risk_level" in df.columns else 0
    revenue_at_risk = round(df.loc[df["risk_level"] == "High Risk", "monetary"].sum(), 2) if "risk_level" in df.columns else 0
    total_revenue = round(df["monetary"].sum(), 2)

    summary_lines = [
        f"Total customers analyzed: <b>{total_customers}</b>",
        f"High-risk customers: <b>{high_risk_count}</b>",
        f"Total revenue across all customers: <b>{total_revenue:,.2f}</b>",
        f"Revenue at risk (held by high-risk customers): <b>{revenue_at_risk:,.2f}</b>",
    ]
    if model_metrics:
        summary_lines.append(
            f"Model accuracy: <b>{model_metrics.get('accuracy', 'N/A')}</b>, "
            f"ROC-AUC: <b>{model_metrics.get('roc_auc', 'N/A')}</b>"
        )

    for line in summary_lines:
        story.append(Paragraph(line, normal_style))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))

    # --- Charts ---
    # Sized to ~3.1" tall so two charts comfortably share a single page.
    # Each heading+image pair is wrapped in KeepTogether so a heading never
    # gets orphaned at the bottom of a page with its chart pushed to the next.
    story.append(KeepTogether([
        Paragraph("Risk Distribution", heading_style),
        Image(risk_chart_path, width=4.6 * inch, height=3.1 * inch),
    ]))
    story.append(Spacer(1, 8))

    story.append(KeepTogether([
        Paragraph("Revenue by Risk Level", heading_style),
        Image(revenue_chart_path, width=4.6 * inch, height=3.1 * inch),
    ]))
    story.append(Spacer(1, 8))

    if has_segment_chart:
        story.append(KeepTogether([
            Paragraph("Customer Segments", heading_style),
            Image(segment_chart_path, width=4.6 * inch, height=3.1 * inch),
        ]))
        story.append(Spacer(1, 8))

    # --- High Risk Table ---
    # No forced PageBreak here — let it flow right after the charts if there's
    # room, instead of always starting a fresh page and wasting space above it.
    if "risk_level" in df.columns:
        story.append(Paragraph("Top High-Risk Customers", heading_style))

        source_df = explained_df if explained_df is not None else df
        high_risk = source_df[source_df["risk_level"] == "High Risk"].sort_values(
            "churn_probability", ascending=False
        )

        cols = ["customer_id", "churn_probability", "segment"]
        if "risk_reason" in high_risk.columns:
            cols.append("risk_reason")
        cols = [c for c in cols if c in high_risk.columns]

        if not high_risk.empty:
            display = high_risk[cols].copy()
            if "churn_probability" in display.columns:
                display["churn_probability"] = (display["churn_probability"] * 100).round(1).astype(str) + "%"
            story.append(_df_to_table(display, max_rows=20))
        else:
            story.append(Paragraph("No high-risk customers found.", normal_style))

        story.append(Spacer(1, 10))

    # --- Notification Log ---
    # Only force a new page if there's an actual log to show — avoids an
    # empty trailing page when there's nothing to display.
    if notification_log_df is not None and not notification_log_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("Notification Log", heading_style))
        cols = [c for c in ["customer_id", "channel", "status", "sent_at"] if c in notification_log_df.columns]
        story.append(_df_to_table(notification_log_df[cols], max_rows=25))

    doc = SimpleDocTemplate(output_path, pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    doc.build(story)

    return output_path