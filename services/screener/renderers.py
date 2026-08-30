"""Renderer converting ScreenerResult into formatted markdown tables with citations."""

from __future__ import annotations

from services.screener.dsl import ScreenerResult


def render_screener_results_table(result: ScreenerResult) -> str:
    """Renders ScreenerResult rows as a structured markdown table with source citations."""
    if not result.rows:
        return "_No companies matched the specified screening criteria._"

    metrics = [f.metric for f in result.dsl.filters]
    if result.dsl.sort and result.dsl.sort.metric not in metrics:
        metrics.append(result.dsl.sort.metric)

    metric_headers = [m.replace("bank.", "").replace("margin.", "").upper() for m in metrics]
    header_cols = ["Ticker", *metric_headers, "Period", "Basis / Citation"]
    lines = [
        f"| {' | '.join(header_cols)} |",
        f"|:{'---|---:'.join([''] * len(header_cols))}---|",
    ]

    for row in result.rows:
        ticker = row.ticker
        val_cells: list[str] = []
        for m in metrics:
            val = row.metric_values.get(m)
            if val is not None:
                f_val = float(val)
                val_str = f"{f_val * 100:.2f}%" if abs(f_val) <= 1.0 else f"{f_val:,.2f}"
            else:
                val_str = "—"
            val_cells.append(val_str)

        period = str(result.dsl.as_of)
        citation = f"[{ticker}-DERIVED-{period}]"
        row_str = f"| **{ticker}** | {' | '.join(val_cells)} | {period} | {citation} |"
        lines.append(row_str)

    return "\n".join(lines)
