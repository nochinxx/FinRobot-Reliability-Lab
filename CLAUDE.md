# FinRobot Reliability Lab — Agent Instructions

## What this project is

NOT rebuilding FinRobot. Building a **trust/audit layer on top of it**.

**Positioning:**
> "The existing pipeline is a working prototype. PR1 makes its architecture, prompts, schemas, and tests legible. Quant-validity claims remain preliminary until the backtest and recommendation-capture pipeline are expanded."

**Target audience:** quant / financial risk / model-risk / AI research infrastructure teams at BlackRock, JPM, BofA.
**Direction:** "Auditable reliability and model-risk layer for agentic equity research" — NOT "AI stock picker."

---

## Session Startup Protocol (run in this order every session)

```bash
# 1. Check reply queue for Mario's instructions
ls ~/agent/inbox/replies/*.json 2>/dev/null

# 2. Confirm tests still pass (offline, no API calls)
conda run -n agent python -m pytest tests/ -v

# 3. Check cache health
conda run -n agent python tools/cache_manager.py status

# 4. Read last session log
tail -40 docs/logs/claude_session_log.md

# 5. Print current sprint tasks
grep -A 30 "## Current Sprint" CLAUDE.md
```

Then proceed directly to the current sprint tasks. Do not ask for direction — the sprint checklist is the source of truth.

After completing each task: (a) mark it done in the Sprint Tracker below, (b) append to `docs/logs/claude_session_log.md`.

---

## Sprint Tracker

### PR1 — COMPLETE (Jun 8 2026)
- [x] docs/architecture.md, data_contracts.md, source_hierarchy.md, repo_inventory.md, wiki_update_draft.md
- [x] docs/wiki/00–07 (8 files)
- [x] docs/logs/decision_log.md, experiment_log.md, claude_session_log.md
- [x] prompts/ (9 versioned files: claim_extractor, recommendation_extractor, fact_check_auditor, skeptical_analyst, thesis_synthesizer, quant_risk_reviewer, model_risk_reviewer, disagreement_aggregator, investment_committee_memo)
- [x] schemas/ (9 files: claim, fact_row, reliability_scorecard, recommendation, gate_decision, experiment_manifest, backtest_snapshot, critic_findings, run_metadata)
- [x] tests/conftest.py (DEV_MODE enforced, --live flag for real calls)
- [x] tests/test_claim_extraction.py (37 tests)
- [x] tests/test_scorecard.py (22 tests)
- [x] tests/test_schema_validation.py (32 tests)
- [x] tests/fixtures/ (4 files)
- [x] tools/html_table_parser.py (PoV, not wired)
- [x] tools/cache_manager.py (status/warm/export/purge)
- [x] reliability_lab/verifiers/api_cache.py (DEV_MODE + OFFLINE mode)
- [x] SEC EDGAR caching added to sec_verifier.py (7-day TTL)
- [x] FMP DEV_MODE guard added to fmp_verifier.py

---

### PR2 — COMPLETE (Jun 8 2026)

**Goal:** Fix the three known accuracy bugs and wire up provenance logging.
**Rule:** Do NOT change any CLI interface. Do NOT change scorecard formula outputs.

- [x] **P2-1** Fix `_nearest_year()` in `reliability_lab/claim_extraction.py`
  - Change: split compound sentences before running year search (detect " to " / " from " patterns)
  - Test: `test_multi_year_sentence_attributes_correctly` PASSES
  - File: `reliability_lab/claim_extraction.py:99`

- [x] **P2-2** Fix P/E extraction from co-occurring P/E + EV/EBITDA sentences
  - Change: ±60-char narrow window + distance-based classification (d_pe vs d_ev)
  - Test: `test_pe_ratio_extracted_separately_from_ev_ebitda` and `test_pe_ratio_claim_from_fixture` PASS
  - File: `reliability_lab/claim_extraction.py:244`

- [x] **P2-3** Load prompts from `prompts/` at runtime (not hardcoded in source)
  - Done in `claim_extraction.py` (`_load_prompt()` helper, `_extract_llm()` updated)
  - Done in `critic_agents.py` (skeptic + synthesis load from file; fallback to inline)
  - Test: `TestPromptLoading` (5 tests) all pass

- [x] **P2-4** Add `run_metadata` logging to all LLM calls
  - Done in `claim_extraction.py` (`_make_run_metadata`, `_append_run_metadata`, `_sha256`)
  - Done in `critic_agents.py` (after each `_llm_call()`)
  - `_llm_call()` now returns `(text, provider, model_name)` and sets `temperature=0`
  - Schema updated: added `skeptical_analyst`, `thesis_synthesizer`, `recommendation_extraction` phases
  - Test: `TestRunMetadata` (7 tests) + `test_make_run_metadata_produces_valid_instance` all pass

- [x] **P2-5** Add `recommendation.json` extraction
  - New file: `reliability_lab/recommendation_extractor.py`
  - Uses: `prompts/recommendation_extractor_v1.txt` (`.replace()` for JSON-safe substitution)
  - Output: `output/{TICKER}/{TICKER}_recommendation.json`
  - Wired into: `run_reliability_audit.py` as `--recommendation` flag (Phase 6)
  - Test: `tests/test_recommendation_extractor.py` (6 tests) all pass

- [x] **P2-6** Update tests after fixes
  - Renamed `test_multi_year_sentence_known_attribution_bug` → `test_multi_year_sentence_attributes_correctly`
  - Renamed `test_pe_ratio_window_overlap_known_limitation` → `test_pe_ratio_extracted_separately_from_ev_ebitda`
  - 91 → **111 tests pass**

---

### PR3 — COMPLETE (Jun 9 2026)

**Goal:** SOURCE_CONFLICT resolution, master fact table, gate decisions, experiment manifest, Family 2 signal capture.
**Rule:** Do NOT change any CLI interface. Do NOT change scorecard formula outputs.

- [x] **P3-1** SOURCE_CONFLICT resolution logic
  - EBITDA dual-verified: SEC EDGAR (Tier 1) vs FMP (Tier 3); `SOURCE_CONFLICT` when delta > 15%
  - Added `conflict_details`, `verified_value_alt`, `source_alt`, `source_tier` columns to fact table
  - File: `reliability_lab/fact_table_builder.py` + `schemas/fact_row.schema.json`

- [x] **P3-2** Master Fact Table builder
  - `reliability_lab/master_fact_table.py`
  - Merges per-ticker fact tables into `output/master_fact_table.csv`
  - Status: LOCKED (Tier 1 verified), PROVISIONAL (Tier 3 only), CONFLICT, INCORRECT, UNVERIFIED

- [x] **P3-3** Gate decision object
  - `reliability_lab/scoring/gates.py`
  - PASS / HUMAN_REVIEW / FAIL with hard-failure thresholds and audit reasons
  - Wired into `run_reliability_audit.py` as `--gate` flag (Phase 3b)

- [x] **P3-4** Experiment manifest
  - `reliability_lab/backtesting/experiment_manifest.py`
  - Full reproducibility record: git SHA, prompts, phases, data sources, outputs
  - Wired into `run_reliability_audit.py` as `--manifest` flag (Phase 3c)

- [x] **P3-5** --recommendation now default (Mario approved 2026-06-09)
  - Recommendation extraction runs on every audit; no flag needed; skips gracefully without API key

- [x] **P3-6** HTML table parser injected (Mario approved 2026-06-09)
  - `reliability_lab/ingestion/html_tables.py` — converts year-value pairs → claim dicts
  - `extract_claims_from_report()` now supplements regex/LLM claims with table-parsed ones
  - `tools/html_table_parser.py` updated docstring (no longer standalone-only)

- [x] **P3-7** Tests: 201 total (was 111; +90 new tests)

### PR4 — COMPLETE (Jun 9 2026)
- [x] `reliability_lab/critics/quant_risk_reviewer.py` — Phase 5b: ICR artifact assessment, coverage gaps, source-tier breakdown, quant_risk_verdict (low/medium/high)
- [x] `reliability_lab/critics/model_risk_reviewer.py` — Phase 5c: determinism/input_sensitivity/coverage_gap/prompt_fragility risks, model_risk_verdict
- [x] `schemas/quant_risk_review.schema.json` + `schemas/model_risk_review.schema.json`
- [x] Wired into `run_reliability_audit.py --critic` as Phase 5b + Phase 5c
- [x] `tests/test_critic_reviewers.py` (31 tests covering helpers, offline fallback, schema validation)

### PR5 — COMPLETE (Jun 9 2026)
- [x] Investment committee memo: `reliability_lab/critics/investment_committee_memo.py` — Phase 7, `--memo` flag
- [ ] Annotated HTML report — deferred to PR6
- [x] Paper section swap: 5.7 (Backtesting) moved before 5.8 (Adversarial Critic); sections now in correct order
- [x] Phase 2 ticker list fix: ROKU "🔄 in progress" → "✅ report generated"

### F1–F4 Final Polish Sprint (Jun 10 2026)

#### F1 — Paper Fixes — COMPLETE (Jun 10 2026)
- [x] Fix 3 stale "within 0.15%" references (L251 footnote, L539 Section 6.1, L648 Conclusion)
- [x] Section 6.1: update with 37-claim accuracy finding (GPT-4 0.12%, Gemma4 0.76%)
- [x] Section 6.2: rewrite failure mode taxonomy with actual v0.4 measurements
- [x] README: add run_batch_audit.py, run_master_fact_table.py, fix test count (225→389), fix stale 0.15% claim

#### F2 — Test Coverage (4 untested core modules) — COMPLETE (Jun 10 2026)
- [x] `tests/test_fact_table_builder.py` — _verify_claim routing, SOURCE_CONFLICT, FACT_TABLE_COLUMNS, save_fact_table (33 tests)
- [x] `tests/test_fmp_verifier.py` — verifier functions with mocked HTTP (_find_by_year, verify_eps, verify_pe_ratio, etc.) (31 tests)
- [x] `tests/test_sec_verifier.py` — get_revenue, get_company_facts with mocked SEC responses
- [x] `tests/test_api_cache.py` — DEV_MODE, OFFLINE, cache hit/miss logic (3 test fixes Jun 10)

#### F3 — Discussion Section Expansion — COMPLETE (Jun 10 2026)
- [x] Section 6 word count: grew from 994 → 2368 words (vs Results 4057)
- [x] Quantify Tier 2 impact: 35pp SCR unlock (253/723 guidance claims) → medium-term ~58% achievable
- [x] Deployment readiness checklist with 8 concrete thresholds and current state column

#### F4 — Final commit + push, regenerate PDF — COMPLETE (Jun 10 2026)
- [x] 453 offline tests passing — committed b53ae20 and pushed
- [x] Paper HTML regenerated (paper/reliability_audit_paper.html)
- [ ] PDF regeneration blocked (pango library missing on this machine); paper exists as .html + .md

### G1 — 100-Stock Expansion (IN PROGRESS — Jun 10 2026)

**Goal:** Validate the verification layer at scale. Current benchmark = 10 stocks. Target = 100.

**FMP free tier constraint:** 250 calls/day. Each ticker = ~6 FMP calls + 1 SEC call. Max 40 new tickers/day.
**Report generation:** Gemma4 via Ollama (running locally, `gemma4:12b-mlx`). Each report takes ~3-10 min.

**Deliverables:**
- [x] G1-1: Curate 90 new tickers → `docs/ticker_universe.md` (90 S&P 500 + mid-cap in 3 batches; sector-diverse; peer sets included)
- [x] G1-0: `run_batch_report_generator.py` written — generates FinRobot reports via Gemma4/Ollama; dry-run verified; `--batch A/B/C` flags
- [ ] G1-0-run: Actually generate 90 reports — run `python run_batch_report_generator.py --batch A` overnight (30 tickers × ~5min = ~2.5h)
- [ ] G1-2: Warm FMP/SEC cache for all 90 new tickers in 3 daily batches (cache_manager.py warm)
- [ ] G1-3: Run batch audit: `run_batch_audit.py` on all 100 tickers (no API after cache warm)
- [ ] G1-4: Rebuild master fact table: `run_master_fact_table.py` — expect 5,000-8,000 rows
- [ ] G1-5: Re-run historical backtest on full 100-ticker universe (3 cutoff dates = 300 observations)
- [ ] G1-6: Update paper Section 4 (experiment design) and Section 5 (results) with expanded benchmark
- [ ] G1-7: Statistical significance — with 300 obs, Mann-Whitney and bootstrap CI on BUY vs HOLD spread will be meaningful

### G2 — Multi-Agent Verification Layer (Jun 10 2026)

**Goal:** Port the PRs-on-edge specialist-agent pattern to FinRobot. Each agent examines the audit data from a distinct domain angle, feeding a synthesis node. Pitch artifact for BlackRock/quant roles.

**Architecture (inspired by PRs-on-edge view-mode agents):**
- `reliability_lab/critics/earnings_analyst.py` — checks EPS/revenue/margin consistency vs. verified fact table; flags ICR inflation in financials
- `reliability_lab/critics/valuation_agent.py` — checks P/E, EV/EBITDA, price targets for internal consistency and sector reasonableness
- `reliability_lab/critics/catalyst_evaluator.py` — assesses whether stated catalysts are specific, timely, and supported
- `reliability_lab/critics/coherence_agent.py` — checks if thesis + recommendation + data are internally consistent (BUY with high ICR = red flag)
- `reliability_lab/critics/multi_agent_synthesizer.py` — aggregates all 5+ agent outputs into a structured `multi_agent_review.json`
- `run_reliability_audit.py --agents` flag wires the new pipeline
- Schemas: `schemas/multi_agent_review.schema.json`

**Deliverables:**
- [x] G2-1: `reliability_lab/critics/earnings_analyst.py` + prompt + 7 tests
- [x] G2-2: `reliability_lab/critics/valuation_agent.py` + prompt + 4 tests
- [x] G2-4: `reliability_lab/critics/coherence_agent.py` + prompt + 3 tests
- [x] G2-5: `reliability_lab/critics/multi_agent_synthesizer.py` — aggregates 3 agents; panel verdict: CONCERN/REVIEW/ACCEPTABLE
- [x] G2-6: `--agents` flag wired in `run_reliability_audit.py` as Phase 8
- [ ] G2-3: `reliability_lab/critics/catalyst_evaluator.py` + schema + tests (next session)
- [ ] G2-7: Paper Section 5 update: multi-agent panel results on 10-ticker benchmark
- [ ] G2-8: Verify test_multi_agent_critics.py passes (20 tests written, pending sandbox verification)

### P1–P5 Final Sprint Plan (Jun 9 2026 — near-final stage)

#### P1 — Paper Accuracy (critical fixes) — COMPLETE
- [x] Section 1.3: fix "9-metric" claim → "5-metric implemented, 4 planned"
- [x] Section 1.3: fix claim type taxonomy (quantitative/qualitative/predictive/comparative → actual 8 types)
- [x] Section 1.3: fill in GitHub URL
- [x] Section 4.1: "Three-Stock Pilot" → "Five-Stock Pilot"
- [x] Section 6.2: "Phase 6" → "Phase 5"
- [x] Duplicate Section 6.4 → renumber as 6.4/6.5/6.6
- [x] Conclusion: ICR is ALSO genuine hallucination (not just artifact); coverage 16–56%
- [x] Conclusion: add PR3–PR7 additions (gate, manifest, critic panel, IC memo, table parser)
- [x] Draft version line: v0.5 / 2026-06-09

#### P2 — Statistical Rigor — COMPLETE
- [ ] New: `reliability_lab/statistics/__init__.py`
- [ ] New: `reliability_lab/statistics/backtest_stats.py`
  - `compute_group_stats(returns)` → mean, median, std, min, max, win_rate, sharpe_6m, max_drawdown
  - `bootstrap_ci(returns, n_boot=10000, ci=0.95)` → (lower, upper)
  - `mann_whitney_test(group1, group2)` → U, p-value, direction
  - `welch_t_test(group1, group2)` → t, p-value, df
  - `cohens_d(group1, group2)` → effect size
  - `information_ratio(alphas)` → alpha_mean / alpha_std
  - `format_stats_table(results)` → markdown table for paper
- [ ] Update `run_historical_backtest.py` — call stats module after computing returns, add stat table to paper_table.md
- [ ] Update paper Section 5.7 with full statistical table (bootstrap CIs, Mann-Whitney, effect size, Sharpe, win rate)
- [ ] Tests: `tests/test_backtest_stats.py` (20+ tests)

#### P3 — Test Coverage — COMPLETE
- [ ] `tests/test_historical_backtest.py` — test signal computation, snapshot structure (offline)
- [ ] `tests/test_price_verifier.py` — mock yfinance, test return/verify logic
- [ ] `tests/test_backtest_signal.py` — test signal extraction from claims (offline)

#### P4 — Package Setup — COMPLETE
- [ ] `pyproject.toml` (PEP 517, minimal install)
- [ ] `requirements.txt` pinned for reproducibility

#### P5 — Final Paper + Commit — COMPLETE
- [ ] Regenerate PDF
- [ ] Commit + push all changes

### PR6 — COMPLETE (Jun 9 2026)
- [x] Annotated HTML report: `reliability_lab/report/annotated_report.py` — Phase 4b (`--annotate` flag); color-coded fact table, scorecard cards, gate banner, conflict detail, XSS-safe
- [x] Master fact table CLI: `run_master_fact_table.py` — auto-discovers tickers with fact tables, merges, prints status summary
- [x] Phase 2 rerun: all 5 tickers (ETSY, ROKU, RIVN, RBLX, LCID) re-audited with table parser active
  - MV coverage: 2→6-17 claims per ticker (3-8× improvement)
  - Finding: ICR remains high — NOT purely an artifact; Gemma4 generates hallucinated forward projections (EBITDA margin ~70% claimed vs 9% actual for ETSY/ROKU)
  - Master fact table: 723 rows, 13.6% coverage (60 LOCKED + 38 PROVISIONAL)
- [x] Paper Section 5.6 updated with new Phase 2 results table (pre/post table parser comparison) + master fact table summary
- [x] PDF regenerated (50 KB)
- [x] `tests/test_annotated_report.py`: 24 tests

---

## Offline Development (no API calls)

```bash
# All tests run offline by default (conftest.py sets DEV_MODE=1)
conda run -n agent python -m pytest tests/

# Run live tests (hits FMP + SEC EDGAR, costs quota)
conda run -n agent python -m pytest tests/ --live

# Check what's in cache
conda run -n agent python tools/cache_manager.py status

# Warm cache for a ticker (fetches all 6 endpoints: ratios, key-metrics, cash-flow, balance-sheet, profile, SEC)
conda run -n agent python tools/cache_manager.py warm NVDA

# Warm all 10 tickers (6 endpoints × 10 tickers = 60 FMP calls + 10 SEC calls, all cached 24h/7d)
conda run -n agent python tools/cache_manager.py warm --all

# Export cache to tests/fixtures/api_responses/ for offline fixture use
conda run -n agent python tools/cache_manager.py export

# Force DEV_MODE manually (no API calls even outside pytest)
DEV_MODE=1 conda run -n agent python run_reliability_audit.py --ticker NVDA --mode regex
```

Cache storage:
- FMP: `reliability_lab/output/api_cache/fmp/` (24h TTL)
- SEC EDGAR: `reliability_lab/output/api_cache/sec/` (7-day TTL)
- FMP legacy cache: `reliability_lab/output/fmp_cache/` (also 24h, preserved for backward compat)

---

## How to run an audit

```bash
conda run -n agent python run_reliability_audit.py --ticker TICKER --mode auto
conda run -n agent python run_reliability_audit.py --ticker TICKER --mode auto --critic
```

- `--mode auto` tries LLM first (requires ANTHROPIC_API_KEY), falls back to regex
- `--mode regex` is deterministic, no API key needed — use for batch runs
- Reports auto-discovered from `finrobot_equity/core/output/{TICKER}_Equity_Research_Report.html`

## How to run the historical backtest

```bash
conda run -n agent python run_historical_backtest.py
conda run -n agent python run_historical_backtest.py --ticker NVDA TSLA META
```

- Default: 9 tickers × 3 cutoff dates = 27 observations
- Do NOT re-run with `--ticker-all` unless explicitly requested — uses FMP quota

---

## Environment

- Conda env: `agent` — all Python must be `conda run -n agent python ...`
- Free sources only: SEC EDGAR (no key), FMP free tier (250 calls/day, cached), yfinance
- FMP key in `config_api_keys` — 250 calls/day limit
- Do NOT use paid APIs or services

## Stock universe

**Phase 1 (done):** COP, MSFT, META, NVDA, TSLA
**Phase 2 (done):** ETSY, ROKU, RIVN, RBLX, LCID
**Dropped (FMP 402 error):** DOCN, ZI, PTON, VFC, ALRM

## Key results (paper v0.4, preliminary)

- SEC EDGAR alone: source coverage 2–4%
- With FMP: coverage 16–51% (7–25x improvement)
- Revenue accuracy: within 0.15% of SEC EDGAR 10-K for correctly-attributed historical claims
- Backtest (27 obs): BUY +16.5% 6m / HOLD −16.4% 6m (+32.9pp spread) — **signal is Family 1 (valuation-multiple), not Family 2 (FinRobot recommendation)**
- Adversarial critic: thesis stability 0.15–0.25; TSLA HOLD→SELL post-critique

---

## Known artifacts (do not flag as errors)

- **Period attribution error:** FIXED in PR2-1. `_nearest_year()` now uses clause-boundary detection
  (` to ` / ` from ` separators). Pre-fix ICR inflation was an extraction artifact, not hallucinations.
- **P/E window overlap:** FIXED in PR2-2. Narrow ±60-char window + distance comparison now correctly
  separates co-occurring P/E and EV/EBITDA multiples.
- **ICR=53% for NVDA:** Was primarily the period-attribution artifact above. Re-run audit to get updated figure.
- **HTML table linearization:** `_strip_html()` destroys column/row structure. PoV parser at
  `tools/html_table_parser.py` exists but is NOT injected. **Do not inject without Mario's explicit approval.**
  (See PR3-6.)

---

## Source hierarchy

- **Tier 1:** SEC EDGAR XBRL, exchange/price feeds (yfinance) — ground truth
- **Tier 2:** Company IR, earnings releases, transcripts
- **Tier 3:** FMP free tier, yfinance — secondary
- **Tier 4:** News / analyst commentary — not used for verification
- **Tier 5:** LLM-generated text (FinRobot reports) — what we are auditing

When Tier 1 ≠ Tier 3: Tier 1 wins. Record both. If delta > tolerance → `SOURCE_CONFLICT`. Do NOT average.

## Three signal families (track separately — do NOT connect until Mario approves)

1. Valuation-multiple signal → `run_historical_backtest.py`
2. Original FinRobot recommendation → `run_reliability_audit.py`
3. Critic-revised recommendation → `run_reliability_audit.py --critic`

## Determinism requirements

- All LLM calls: temperature=0, log model_name, provider, prompt_version, prompt_hash, input_hash, output_hash
- Ollama fallback: tag `provider: "ollama_fallback"` — do NOT mix with Anthropic outputs
- Prompt files live in `prompts/` — loaded at runtime via `_load_prompt()` in `claim_extraction.py` (DONE PR2)
- For prompt files containing JSON schemas, use `.replace("{var}", val)` not `.format()` — avoids brace conflicts

---

## Session registration (do this at end of every session)

1. Append entry to `docs/logs/claude_session_log.md` — format is in that file
2. Append entry to `~/agent/logs/YYYY-MM-DD.md`
3. Update Sprint Tracker checkboxes above
4. Run `conda run -n agent python -m pytest tests/ -v` — paste final count in session log

---

## Files that must not be modified without Mario's explicit approval

- `run_reliability_audit.py` — existing flags must remain identical; new optional flags may be added (e.g. `--recommendation` added PR2, `--gate` planned PR3)
- `run_historical_backtest.py` — CLI interface must remain identical
- `backtest_signal.py` — experimental, keep as-is
- `finrobot_equity/` — upstream black box; never modify

## After each audit

1. Results go to `output/{TICKER}/`
2. Update `paper/reliability_audit_paper.md` Section 5 with new findings
3. If ICR > 0.10: flag it (but note it may be extraction artifact)

## Wiki and logging

- Do NOT write to `~/wiki/` from pipeline code
- Use `docs/wiki_update_draft.md` for wiki content — Mario transfers manually
- External logs: `~/agent/logs/YYYY-MM-DD.md`
- Internal logs: `docs/logs/` (decision_log.md, experiment_log.md, claude_session_log.md)
