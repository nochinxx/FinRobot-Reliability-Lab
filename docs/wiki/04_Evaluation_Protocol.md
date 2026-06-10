# 04 Evaluation Protocol

## Current State (PR1)

Claim-level evaluation uses fixture-based tests only. No large-scale benchmark yet.

## Planned Evaluation Streams

### 1. Extractor Benchmark (PR2+)
- Manually label 100–500 claims across at least 5 tickers.
- Measure: precision, recall, period attribution accuracy, unit accuracy, source-linking accuracy.
- Compare: regex vs LLM vs HTML structural parser vs hybrid.
- Baseline: regex is already running — label its output for Phase 1.

### 2. Reliability Benchmark (PR3+)
- Target: ≥100 tickers, multiple sectors and market caps, multiple report dates.
- Report: source coverage and accuracy by claim type.
- Current state: 10 tickers (Phase 1+2 universe), 27 audit observations.

### 3. Multi-Agent Disagreement Benchmark (PR5+)
- Run 5 independent reports per ticker/date.
- Measure: recommendation agreement, target price dispersion, claim disagreement rate.
- Requires: `disagreement_aggregator_v1.txt` wired into pipeline.

### 4. Critic-Layer Value (PR4+)
- Compare raw vs fact-checked vs adversarial-critic vs full-gate report.
- Measure: errors removed, recommendations changed, thesis-changing challenges surfaced.
- Current state: adversarial critic running on --critic flag, thesis stability tracked.

### 5. Date-Gated Signal Backtest (PR3)
- Requirement: recommendation generated with data strictly before cutoff date.
- Freeze outputs. Log data snapshot. No forward leakage.
- Metrics: 1m/3m/6m/12m forward return vs SPY and sector ETF, hit rate, drawdown.
- Current state: 27 observations (9 tickers × 3 cutoffs), signal is valuation-multiple (Family 1), not FinRobot recommendation (Family 2).

## Core Hypothesis

High-reliability AI-generated BUY recommendations (high SCR, low ICR, PASS gate) outperform
low-reliability AI-generated BUY recommendations on a risk-adjusted basis.

This is NOT yet tested with Family 2 signal (FinRobot recommendation). The current backtest
uses a separate valuation-multiple signal. These must not be conflated.
