# 06 Implementation Roadmap

## Phase 0 — Repo Reconnaissance (COMPLETE)
- Claude inspected repo and produced gap analysis.
- No code changes.

## Phase 1 — Non-Breaking Skeleton (COMPLETE — PR1, Jun 8 2026)
- docs/wiki/, docs/logs/, docs/architecture.md, docs/data_contracts.md, docs/source_hierarchy.md, docs/repo_inventory.md
- prompts/ (9 versioned files)
- schemas/ (9 JSON Schema files)
- tests/ (91 fixture-based tests, 0 live API calls)
- tools/html_table_parser.py (PoV, not wired)
- tools/cache_manager.py (status/warm/export/purge)
- reliability_lab/verifiers/api_cache.py (DEV_MODE + OFFLINE + 7-day SEC cache)
- Existing scripts unchanged. 91/91 tests pass.

## Phase 2 — Bug Fixes, Provenance Logging, Recommendation Capture (COMPLETE — PR2, Jun 8 2026)
- Fixed `_nearest_year()` clause-boundary attribution bug (P2-1)
- Fixed P/E + EV/EBITDA window-overlap bug — both now extracted separately (P2-2)
- Prompts loaded from `prompts/` at runtime via `_load_prompt()` helper (P2-3)
- `run_metadata` JSON provenance logged per LLM call — ticker, phase, model, hashes (P2-4)
- `reliability_lab/recommendation_extractor.py` — structured rating/price-target/catalyst extraction (P2-5)
- `--recommendation` flag wired into `run_reliability_audit.py` (P2-5)
- `_llm_call()` in critic_agents now returns (text, provider, model), enforces temperature=0 (P2-4)
- 20 new tests added. 111/111 tests pass.

## Phase 3 — Structural HTML Table Parser + Disagreement Layer (PR3, planned)
- Inject `tools/html_table_parser.py` into main pipeline (with Mario's approval)
- SOURCE_CONFLICT resolution: Tier 1 wins, record both values
- Master Fact Table builder
- Conflict resolver
- Gate decision object

## Phase 4 — Source Registry + Verification Normalization (PR4, planned)
- Centralize source tiers in `sources/source_registry.py`
- All verifiers return same object shape
- Add `quant_risk_reviewer` and `model_risk_reviewer` critics (prompts exist)

## Phase 5 — Backtest Upgrade (PR5, planned)
- Use actual date-gated FinRobot recommendations (Family 2 signal) — not valuation-multiple rule
- Risk-adjusted metrics, factor exposure controls
- Annotated report output
- Investment committee memo output

## Phase 6 — Paper Rewrite (final phase)
- Reframe as reliability/model-risk infrastructure
- Keep alpha claims preliminary until n ≥ 100 and signal source is clean (Family 2)
- Fix section ordering (5.8 before 5.7) and Phase 2 ticker list in paper v0.4
