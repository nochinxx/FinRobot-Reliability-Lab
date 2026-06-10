"""
Annotated HTML audit report generator — Phase 4b.

Produces a self-contained HTML file showing:
  - Reliability scorecard (color-coded PASS/FAIL)
  - Gate decision banner (PASS / HUMAN_REVIEW / FAIL)
  - Full fact table with status-coded rows
  - SOURCE_CONFLICT detail panel
  - Methodology notes

Output: output/{TICKER}/{TICKER}_annotated_report.html
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


_STATUS_COLORS = {
    "verified":               ("#d4edda", "#155724", "✅ VERIFIED"),
    "incorrect":              ("#f8d7da", "#721c24", "❌ INCORRECT"),
    "SOURCE_CONFLICT":        ("#fff3cd", "#856404", "⚠ CONFLICT"),
    "unsupported":            ("#e2e3e5", "#383d41", "— UNSUPPORTED"),
    "not_machine_verifiable": ("#e2e3e5", "#383d41", "○ NMV"),
}

_GATE_COLORS = {
    "PASS":         ("#d4edda", "#155724"),
    "HUMAN_REVIEW": ("#fff3cd", "#856404"),
    "FAIL":         ("#f8d7da", "#721c24"),
}

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       font-size: 13px; color: #212529; background: #f8f9fa; padding: 24px;
       color-scheme: light only; }
h1 { font-size: 22px; margin-bottom: 4px; }
h2 { font-size: 15px; margin: 20px 0 8px; color: #343a40; }
.subtitle { color: #6c757d; font-size: 12px; margin-bottom: 20px; }
.card { background: white; border: 1px solid #dee2e6; border-radius: 6px;
        padding: 16px; margin-bottom: 16px; }
.gate-banner { padding: 12px 16px; border-radius: 6px; font-size: 16px;
               font-weight: 700; margin-bottom: 16px; }
.score-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
              gap: 10px; margin-bottom: 4px; }
.score-card { padding: 10px 14px; border-radius: 5px; }
.score-card .metric { font-size: 11px; color: #6c757d; text-transform: uppercase;
                      letter-spacing: .5px; }
.score-card .value { font-size: 18px; font-weight: 700; margin: 2px 0; }
.score-card .target { font-size: 11px; }
.pass  { background: #d4edda; color: #155724; }
.fail  { background: #f8d7da; color: #721c24; }
.warn  { background: #fff3cd; color: #856404; }
.info  { background: #e2e3e5; color: #383d41; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead tr { background: #343a40; color: white; }
th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #dee2e6;
          vertical-align: top; max-width: 280px; word-break: break-word; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px;
         font-size: 10px; font-weight: 600; white-space: nowrap; }
.conflict-detail { background: #fffbea; border-left: 3px solid #ffc107;
                   padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0; font-size: 11px; }
.by-metric table td:first-child { font-weight: 600; }
.note { color: #6c757d; font-size: 11px; margin-top: 6px; }
a { color: #0066cc; }
"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _badge(status: str) -> str:
    bg, fg, label = _STATUS_COLORS.get(
        status,
        ("#e2e3e5", "#383d41", status.upper())
    )
    return f'<span class="badge" style="background:{bg};color:{fg}">{label}</span>'


def _scorecard_cards(scorecard: dict) -> str:
    m = scorecard.get("metrics", {})
    t = scorecard.get("thresholds", {})
    s = scorecard.get("summary", {})
    cards = []

    metric_labels = {
        "source_coverage_rate":         ("SCR", "Source Coverage Rate"),
        "primary_source_coverage_rate": ("PSCR", "Primary Source Coverage"),
        "unsupported_claim_rate":       ("UCR", "Unsupported Claim Rate"),
        "incorrect_claim_rate":         ("ICR", "Incorrect Claim Rate"),
    }

    for key, (abbr, label) in metric_labels.items():
        val  = m.get(key, 0.0) or 0.0
        thr  = t.get(key, {})
        passed = thr.get("pass", True)
        cls  = "pass" if passed else "fail"
        target = thr.get("target", "")
        cards.append(
            f'<div class="score-card {cls}">'
            f'<div class="metric">{label}</div>'
            f'<div class="value">{val:.3f}</div>'
            f'<div class="target">Target {target} — {"PASS" if passed else "FAIL"}</div>'
            f'</div>'
        )

    vd = m.get("valuation_dispersion")
    if vd is not None:
        cls = "pass" if vd <= 0.10 else "warn"
        cards.append(
            f'<div class="score-card {cls}">'
            f'<div class="metric">Valuation Dispersion</div>'
            f'<div class="value">{vd:.3f}</div>'
            f'<div class="target">Target ≤0.10</div>'
            f'</div>'
        )

    cards.append(
        f'<div class="score-card info">'
        f'<div class="metric">Claims Extracted</div>'
        f'<div class="value">{s.get("total_claims", 0)}</div>'
        f'<div class="target">MV: {s.get("machine_verifiable_claims", 0)} &nbsp;'
        f'✅ {s.get("verified_count", 0)} &nbsp; ❌ {s.get("incorrect_count", 0)}</div>'
        f'</div>'
    )
    return '<div class="score-grid">' + "\n".join(cards) + "</div>"


def _fact_table_html(fact_rows: list[dict]) -> str:
    rows_html = []
    for r in fact_rows:
        status = r.get("verification_status", "unsupported")
        bg, _, _ = _STATUS_COLORS.get(status, ("#fff", "#000", ""))
        vv   = _esc(r.get("verified_value", ""))
        vv_alt = _esc(r.get("verified_value_alt", ""))
        cd   = r.get("conflict_details", "")

        conflict_cell = vv
        if status == "SOURCE_CONFLICT" and vv_alt:
            conflict_cell = (
                f'<b>Tier1:</b> {vv}<br>'
                f'<b>Tier3:</b> {vv_alt}'
            )
            if cd:
                try:
                    cd_parsed = json.loads(cd)
                    delta = cd_parsed.get("delta_pct", "")
                    conflict_cell += f'<br><small>Δ {float(delta)*100:.1f}%</small>'
                except Exception:
                    pass

        tier = _esc(r.get("source_tier", "") or "")
        tier_badge = f'<span style="font-size:10px;color:#6c757d">T{tier}</span>' if tier else ""

        rows_html.append(
            f'<tr style="background:{bg};color:#212529">'
            f'<td>{_esc(r.get("metric",""))}</td>'
            f'<td>{_esc(r.get("period",""))}</td>'
            f'<td>{_esc(r.get("claimed_value",""))}</td>'
            f'<td>{conflict_cell}</td>'
            f'<td>{_esc(r.get("source",""))} {tier_badge}</td>'
            f'<td>{_badge(status)}</td>'
            f'<td style="font-size:11px;color:#6c757d">{_esc((r.get("notes","") or "")[:80])}</td>'
            f'</tr>'
        )

    header = (
        '<thead><tr>'
        '<th>Metric</th><th>Period</th><th>Claimed</th>'
        '<th>Verified</th><th>Source</th><th>Status</th><th>Context</th>'
        '</tr></thead>'
    )
    return f'<table>{header}<tbody>{"".join(rows_html)}</tbody></table>'


def _by_metric_html(scorecard: dict) -> str:
    bm = scorecard.get("by_metric", {})
    if not bm:
        return "<p class='note'>No per-metric breakdown.</p>"
    rows = []
    for metric, counts in sorted(bm.items()):
        rows.append(
            f'<tr><td>{_esc(metric)}</td>'
            f'<td>{counts.get("total",0)}</td>'
            f'<td style="color:#155724">{counts.get("verified",0)}</td>'
            f'<td style="color:#721c24">{counts.get("incorrect",0)}</td>'
            f'<td>{counts.get("unsupported",0)}</td>'
            f'<td>{counts.get("not_machine_verifiable",0)}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>Metric</th><th>Total</th><th>Verified</th>'
        '<th>Incorrect</th><th>Unsupported</th><th>NMV</th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
    )


def generate_annotated_report(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    report_path: str = "",
    gate: Optional[dict] = None,
) -> Path:
    """
    Generate a self-contained annotated HTML audit report.
    Returns path to the written file.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    conflict_rows = [r for r in fact_rows if r.get("verification_status") == "SOURCE_CONFLICT"]

    # Gate banner
    if gate:
        decision = gate.get("decision", "N/A")
        gbg, gfg = _GATE_COLORS.get(decision, ("#e2e3e5", "#383d41"))
        triggers = gate.get("human_review_triggers", [])
        failures = gate.get("hard_failures", [])
        trigger_html = ""
        if triggers:
            trigger_html += f'<br><small>Review triggers: {_esc(", ".join(triggers[:3]))}</small>'
        if failures:
            trigger_html += f'<br><small>Hard failures: {_esc(", ".join(failures[:2]))}</small>'
        gate_html = (
            f'<div class="gate-banner" style="background:{gbg};color:{gfg}">'
            f'Gate Decision: {decision}{trigger_html}</div>'
        )
    else:
        gate_html = '<div class="gate-banner info">Gate decision not run (use --gate)</div>'

    # SOURCE_CONFLICT detail
    conflict_html = ""
    if conflict_rows:
        items = []
        for r in conflict_rows:
            cd = r.get("conflict_details", "")
            delta_str = ""
            if cd:
                try:
                    cd_parsed = json.loads(cd)
                    delta_str = f' | Δ {float(cd_parsed.get("delta_pct",0))*100:.1f}%'
                except Exception:
                    pass
            items.append(
                f'<div class="conflict-detail">'
                f'<b>{_esc(r["metric"])}</b> ({_esc(r["period"])}): '
                f'Tier1 = {_esc(r.get("verified_value",""))} vs '
                f'Tier3 = {_esc(r.get("verified_value_alt",""))}'
                f'{delta_str}<br>'
                f'<small>Sources: {_esc(r.get("source",""))} vs {_esc(r.get("source_alt",""))}</small>'
                f'</div>'
            )
        conflict_html = (
            '<div class="card">'
            f'<h2>SOURCE_CONFLICT Detail ({len(conflict_rows)} rows)</h2>'
            + "".join(items) +
            '</div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>FinRobot Audit — {_esc(ticker)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>FinRobot Reliability Audit — {_esc(ticker)}</h1>
<p class="subtitle">Generated: {ts} | Source report: <code>{_esc(report_path)}</code></p>

{gate_html}

<div class="card">
<h2>Reliability Scorecard</h2>
{_scorecard_cards(scorecard)}
</div>

<div class="card">
<h2>Fact Table ({len(fact_rows)} claims)</h2>
{_fact_table_html(fact_rows)}
<p class="note">Color: green = verified, red = incorrect, yellow = source conflict, grey = unverified/NMV.</p>
</div>

{conflict_html}

<div class="card by-metric">
<h2>Per-Metric Breakdown</h2>
{_by_metric_html(scorecard)}
</div>

<div class="card">
<h2>Methodology Notes</h2>
<ul style="padding-left:18px;line-height:1.8">
  <li>Tier 1 sources: SEC EDGAR XBRL (ground truth)</li>
  <li>Tier 3 sources: FMP free tier (secondary)</li>
  <li>Revenue tolerance: 2% (rounding); EPS/financials: 5%; multiples: 15%</li>
  <li>EBITDA dual-verified: SEC EDGAR (op. income + D&A) vs FMP (net income + D&A)</li>
  <li>SOURCE_CONFLICT: Tier 1 ≠ Tier 3 beyond tolerance — Tier 1 value used</li>
  <li>NMV = Not Machine-Verifiable: guidance, forward projections, peer comparisons</li>
  <li>HTML table claims supplemented via structured table parser (table_parser extraction)</li>
</ul>
</div>

</body>
</html>"""

    out_path = out_dir / f"{ticker}_annotated_report.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
