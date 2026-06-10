# 01 Target Architecture

## High-Level Pipeline

```
1.  FinRobot report generation (or report import)
         ↓
2.  Structured recommendation extraction
         ↓
3.  Claim extraction (regex or LLM)
         ↓
4.  Structural HTML table parsing (preserves year-column mapping)
         ↓
5.  Source retrieval and source-tier ranking
         ↓
6.  Deterministic verification (SEC EDGAR → FMP → yfinance)
         ↓
7.  Multi-agent disagreement analysis (5 runs → Master Fact Table)
         ↓
8.  Adversarial critic panel (skeptical analyst + quant risk + model risk)
         ↓
9.  Reliability scorecard + gate decision (PASS / HUMAN_REVIEW / FAIL)
         ↓
10. Date-gated backtest / risk evaluation
         ↓
11. Annotated report + investment committee memo
```

## Current Implementation (PR1 state)

Steps 1, 3, 5, 6, 8 (partial), 9 (partial), 10 are functional.
Steps 2, 4 (PoV only), 7, 11 are scaffolded but not wired into pipeline.

## Proposed Folder Skeleton (target, not current)

```
finrobot-audit/
  configs/
    sources.yaml           ← source tier config (planned)
    gates.yaml             ← threshold targets (planned)
    tickers.yaml           ← universe definition (planned)
    prompts.yaml           ← prompt version registry (planned)
  docs/
    wiki/                  ← this directory
    logs/                  ← decision_log, experiment_log, claude_session_log
    architecture.md        ← current pipeline diagram
    data_contracts.md      ← per-field contract documentation
    source_hierarchy.md    ← tier definitions and conflict rules
    repo_inventory.md      ← full file inventory
    wiki_update_draft.md   ← content for external wiki (manually transferred)
  prompts/
    claim_extractor_v1.txt
    recommendation_extractor_v1.txt
    fact_check_auditor_v1.txt
    skeptical_analyst_v1.txt
    thesis_synthesizer_v1.txt
    quant_risk_reviewer_v1.txt
    model_risk_reviewer_v1.txt
    disagreement_aggregator_v1.txt
    investment_committee_memo_v1.txt
  schemas/
    claim.schema.json
    fact_row.schema.json
    reliability_scorecard.schema.json
    recommendation.schema.json
    gate_decision.schema.json
    experiment_manifest.schema.json
    backtest_snapshot.schema.json
    critic_findings.schema.json
    run_metadata.schema.json
  reliability_lab/         ← existing core (do not restructure before PR2)
    claim_extraction.py
    fact_table_builder.py
    reliability_metrics.py
    critic_agents.py
    verifiers/
  tests/
    fixtures/
    test_claim_extraction.py
    test_scorecard.py
    test_schema_validation.py
  tools/
    html_table_parser.py   ← PoV, not wired into pipeline
  output/
    {TICKER}/              ← per-run audit outputs
    historical_backtest/   ← backtest outputs
    table_parse_preview/   ← HTML parser PoV outputs
```

## Three Signal Families (track separately)

| Family | Source | Script |
|--------|--------|--------|
| 1. Valuation-multiple signal | P/E + EV/EBITDA vs. historical mean | run_historical_backtest.py |
| 2. Original FinRobot recommendation | BUY/HOLD/SELL from HTML report | run_reliability_audit.py |
| 3. Critic-revised recommendation | Post-adversarial-critique rating | run_reliability_audit.py --critic |

These must not be connected until Mario explicitly approves combining them (planned for PR3+).
