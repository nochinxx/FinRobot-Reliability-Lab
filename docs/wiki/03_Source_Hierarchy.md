# 03 Source Hierarchy

Full documentation: `docs/source_hierarchy.md`

## Tier Definitions

| Tier | Sources | Trust Level |
|------|---------|-------------|
| 1 | SEC EDGAR XBRL company facts, official exchange price feeds | Ground truth for historical facts |
| 2 | Company IR, earnings releases, earnings call transcripts | High quality — direct from company |
| 3 | FMP free tier, yfinance, financial data aggregators | Good for coverage gaps; secondary only |
| 4 | News, analyst commentary, industry reports | Context only — not used for verification |
| 5 | LLM-generated text (FinRobot reports) | The thing being audited — never a source of truth |

## Conflict Resolution Rules

1. When sources agree: use Tier 1 value.
2. When Tier 1 and Tier 3 disagree beyond tolerance: mark `SOURCE_CONFLICT`, record both values in `verified_value` and `verified_value_alt`. Do NOT average. Do NOT mark as `incorrect`.
3. Never use Tier 5 to verify Tier 5.
4. FMP free tier is Tier 3 — may not match SEC EDGAR exactly due to methodology differences.

## Tolerance Reference

| Metric | Tolerance |
|--------|-----------|
| Revenue | ±2% |
| EBITDA | ±5% |
| EPS | ±5% |
| Market cap | ±5% |
| P/E, EV/EBITDA | ±10% |

## Current API Access

- SEC EDGAR: no key required (free, rate-limited)
- FMP free tier: 250 calls/day, 24h file cache — do NOT rebuild cache without cause
- yfinance: no key required
