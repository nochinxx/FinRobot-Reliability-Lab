# 07 Open Questions

Last updated: Jun 9 2026

## Architecture

1. ~~**`_nearest_year()` fix strategy**~~ — **RESOLVED PR2-1.** Clause-boundary detection via `_CLAUSE_SEP` regex (` to ` / ` from ` patterns). Each value searches within its own clause first, falls back to full window.

2. **HTML table parser injection (PR3-6)**: Should it fully replace `_strip_html()` for table-containing HTML, or run in parallel and merge results? **Requires Mario's explicit approval before any code change.**

3. **Phase 2 report template normalization**: Phase 1 reports have 5 tables; Phase 2 reports have 1. Should all reports be regenerated with a consistent template before PR3?

## Signal Families

4. **Family 2 signal capture (PR3-5)**: `recommendation_extractor.py` exists (PR2). Question is whether to make `--recommendation` run by default in the standard audit, or keep it opt-in. **Mario must approve default-on behaviour.**

5. **Family 1 vs Family 2 comparison**: Present both signals side by side once Family 2 data is captured across all 10 tickers, or only present Family 2? Current 27-obs backtest is Family 1 only.

## Data Contracts

6. **Fact table format**: CSV is human-readable but awkward for nested `conflict_details`. Should PR3 migrate to JSONL or add a parallel JSON file?

7. **SOURCE_CONFLICT tolerance**: Current tolerance table in `docs/source_hierarchy.md` — should these be config-file driven (e.g., `config_tolerances.yaml`) so they can be tuned without code changes?

## Model Risk

8. **Ollama fallback policy**: Should fallback outputs ever be included in aggregate metrics (e.g., backtest), or always excluded? Current rule: always label separately via `provider: "ollama_fallback"`. Default is exclude from aggregates.

9. **Gate decision thresholds**: The current targets (SCR ≥ 0.80, ICR ≤ 0.05) are aspirational — current best SCR is 16–51%. Proposal: two threshold sets: `demo` (SCR ≥ 0.20) and `production` (SCR ≥ 0.80). Confirm?

## Paper

10. **Section 5.8/5.7 ordering swap and Phase 2 ticker list**: Cosmetic but needed before submission — planned for PR5. Awaiting Mario approval.
