# 00 Project Brief

## Project Name
FinRobot Reliability Audit Layer

## Positioning

This project is an **institutional reliability and model-risk layer for agentic equity research**, not an autonomous stock picker. The goal is to convert AI-generated equity reports into auditable, source-ranked, reliability-gated research artifacts.

> "The existing pipeline is a working prototype. PR1 makes its architecture, prompts, schemas, and tests legible. Quant-validity claims remain preliminary until the backtest and recommendation-capture pipeline are expanded."

## Core Thesis

LLM financial reports can look institutionally credible while containing unsupported or misattributed claims. A serious financial firm cares less about a polished report and more about traceability, reproducibility, source hierarchy, failure modes, and gating controls.

## Primary Users
- Quant developer / research platform engineer
- Financial risk engineer
- AI model-risk reviewer
- Equity research tooling team
- Applied AI team inside an asset manager or bank

## Non-Goals (Current Phase)
- Fully automated trading or portfolio management
- Claiming proven alpha from small samples (n=27 observations)
- Treating FMP as a primary source of truth
- Letting an LLM be the final authority on financial facts

## Near-Term Objective

Build a non-breaking institutional skeleton that makes the existing project easier for Claude and future agents to extend incrementally. Each PR adds capability without breaking what works.

## Key Results (paper v0.4, preliminary)
- SEC EDGAR alone: source coverage 2–4%
- With FMP: coverage 16–51% (7–25x improvement)
- Revenue accuracy: within 0.15% of SEC 10-K for correctly-attributed claims
- Backtest (27 obs): BUY +16.5% 6m / HOLD −16.4% 6m (+32.9pp spread) — **preliminary**
- Adversarial critic: thesis stability 0.15–0.25; TSLA HOLD→SELL post-critique

## PR Status (as of Jun 2026)
| PR | Status | Focus |
|----|--------|-------|
| PR1 | COMPLETE Jun 8 2026 | docs, prompts, schemas, fixture tests, HTML table parser PoV |
| PR2 | Next | Fix _nearest_year(), load prompts from files, run_metadata logging |
| PR3 | Planned | Disagreement layer, SOURCE_CONFLICT, master fact table |
| PR4 | Planned | quant_risk_reviewer + model_risk_reviewer critics |
| PR5 | Planned | annotated_report, investment committee memo, dashboard_export |
