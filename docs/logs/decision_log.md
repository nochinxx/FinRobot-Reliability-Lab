# Decision Log

## 2026-06-08 — PR1 scope: docs/prompts/schemas/tests only, no pipeline changes

**Decision:** PR1 adds only new files in new directories. Zero modifications to existing reliability_lab/, run_reliability_audit.py, run_historical_backtest.py, or backtest_signal.py.

**Why:** The existing pipeline has 10 audited reports, a working backtest, and live FMP cache. Breaking it would cost a full FMP rebuild (250 API calls) and invalidate existing outputs. The architecture documentation and schemas are valuable on their own without requiring a refactor.

**Alternatives considered:**
- Option B (moderate refactor): would have improved import structure but risked breaking CLI interfaces and requiring test updates across the board.
- Option C (aggressive cleanup): ruled out — too risky for a first PR.

**Tradeoffs:** Prompts still hardcoded in reliability_lab/ source code (not loaded from prompts/). Will be fixed in PR2 when the code is opened for _nearest_year() fix.

**Files affected:** All new. reliability_lab/ untouched.

**Follow-up tasks:** PR2 must wire prompts/ loading at runtime.

---

## 2026-06-08 — HTML table parser: PoV only, not injected into pipeline

**Decision:** `tools/html_table_parser.py` is standalone. Not imported from reliability_lab/. Outputs go to `output/table_parse_preview/` only.

**Why:** Injecting it would require changes to `_strip_html()` and `extract_claims_from_report()` in claim_extraction.py, which is PR1-off-limits. The PoV confirms the approach works (647 year-value pairs extracted, correct normalization) without risking pipeline stability.

**Follow-up tasks:** PR3 decision: fully replace _strip_html() for table HTML, or run in parallel and merge.

---

## 2026-06-08 — Three signal families must remain separate

**Decision:** Valuation-multiple signal (Family 1), FinRobot recommendation (Family 2), and critic-revised recommendation (Family 3) are tracked independently. No code connecting them until Mario explicitly approves.

**Why:** The current backtest uses Family 1 only. Family 2 signal capture doesn't exist yet (no recommendation_extractor wired). Conflating signals in the paper before they are properly implemented would be scientifically incorrect.

**Follow-up tasks:** PR2 adds recommendation.json capture. PR3 adds date-gated Family 2 backtest.

---

## 2026-06-08 — ICR treated as extraction artifact, not confirmed hallucination rate

**Decision:** High ICR (e.g., NVDA 53%) is labeled as an extraction artifact in all documentation, not as a hallucination rate.

**Why:** The _nearest_year() ±200 char window incorrectly attributes values in compound sentences like "from $27B in 2021 to $60B in 2022" — both values can get period=2021. This inflates incorrect_count without reflecting actual LLM errors.

**Tradeoffs:** We may be understating the true error rate on some claims. But overstating it (calling artifacts "hallucinations") is worse for credibility.

**Follow-up tasks:** PR2 fixes _nearest_year(). After fix, re-run audit on all 10 tickers and compare ICR before/after.
