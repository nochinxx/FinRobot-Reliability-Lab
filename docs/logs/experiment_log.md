# Experiment Log

## 2026-06-08 — HTML Table Parser PoV — all 10 tickers

**Objective:** Verify that structured table extraction (preserving year-column mapping) is feasible across all 10 existing reports.

**Tickers:** COP, MSFT, META, NVDA, TSLA, ETSY, ROKU, RIVN, RBLX, LCID

**Cutoff dates:** N/A (PoV only — no data cutoff enforced for preview)

**Models / prompts:** None — pure BeautifulSoup structural parsing, no LLM.

**Data sources:** Local HTML files in `finrobot_equity/core/output/`

**Commands run:**
```bash
conda run -n agent python tools/html_table_parser.py --all
```

**Outputs:** `output/table_parse_preview/{TICKER}_tables.json`, `output/table_parse_preview/_summary.json`

**Results:**
- 10/10 tickers successfully parsed
- Phase 1 (COP/MSFT/META/NVDA/TSLA): 5 tables each, 85–101 year-value pairs per ticker
- Phase 2 (ETSY/ROKU/RIVN/RBLX/LCID): 1 table each, 29–38 pairs
- Total: 647 year-value pairs extracted
- Normalization spot-check: NVDA Revenue 2023A = $27.0B → 27,000,000,000 USD ✓

**Known limitations:**
- Phase 2 reports have only 1 table vs 5 for Phase 1 (different report template)
- Parser not injected into main pipeline — preview only
- No deduplication or reconciliation with regex-extracted claims

**Next experiment:** After PR2 fixes _nearest_year(), re-run all 10 tickers and compare:
- ICR before fix vs after fix
- Coverage rates before/after HTML table injection

---

## 2026-05-XX — Historical backtest, Phase 1+2 universe (prior session)

**Objective:** Date-gated backtesting of valuation-multiple signal (Family 1) across 9 tickers × 3 cutoff dates.

**Tickers:** COP, MSFT, META, NVDA, TSLA, ETSY, ROKU, RIVN, RBLX (LCID excluded — low FMP coverage)

**Cutoff dates:** 2025-06-01, 2025-09-01, 2025-12-01

**Results:**
- 27 observations
- BUY signal: +16.5% avg 6m return
- HOLD signal: −16.4% avg 6m return
- Spread: +32.9pp

**Known limitations:**
- n=27 is insufficient for statistical significance
- Signal is valuation-multiple rule (Family 1), NOT actual FinRobot BUY/HOLD/SELL (Family 2)
- No risk-adjusted metrics, factor controls, or transaction costs
- Preliminary — do not present as proven alpha
