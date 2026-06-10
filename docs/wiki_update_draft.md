# Wiki Update Draft — FinRobot Reliability Lab

> This file is for Mario to manually transfer to ~/wiki/. Do not write to the wiki directly from the pipeline.

---

## Entry: wiki/projects/FinRobot-Reliability-Lab.md — Key Update (Jun 8 2026)

Add the following to the existing wiki project page:

### PR1 — Architecture, Prompts, Schemas, Tests (Jun 8 2026)

PR1 was implemented on Jun 8 2026. Changes:

**New directories:**
- `docs/` — architecture.md, data_contracts.md, source_hierarchy.md, repo_inventory.md
- `prompts/` — 5 versioned prompt files extracted from inline code
- `schemas/` — 6 JSON Schema definitions for all data contracts
- `tests/` — fixture-based unit tests (no live API calls)
- `tools/` — html_table_parser.py (proof-of-value, standalone)
- `output/table_parse_preview/` — parser previews for 10 existing reports

**What changed in existing files:**
- `CLAUDE.md` — fully rewritten with current architecture, PR roadmap, determinism requirements, source hierarchy, and known artifacts
- `wiki/projects/FinRobot-Reliability-Lab.md` — status block updated

**What did NOT change:**
- All existing CLIs (run_reliability_audit.py, run_historical_backtest.py, etc.)
- `reliability_lab/` package structure and code
- Output format for all existing data files
- Paper (needs separate fix for section ordering)

### Updated Positioning

> "The existing pipeline is a working prototype. PR1 makes its architecture, prompts, schemas, and tests legible. Quant-validity claims remain preliminary until the backtest and recommendation-capture pipeline are expanded."

### PR Roadmap (for wiki)

| PR | Focus | Timeline |
|----|-------|----------|
| PR1 | Docs, prompts, schemas, fixture tests, HTML table parser PoV | Done Jun 8 2026 |
| PR2 | Fix period attribution, load prompts from files, run_metadata logging | Next |
| PR3 | Disagreement layer (SOURCE_CONFLICT, master fact table) | Planned |
| PR4 | New critics: quant_risk_reviewer, model_risk_reviewer | Planned |
| PR5 | Output layer: annotated_report, dashboard_export | Planned |

---

## Entry: wiki/concepts/ReliabilityAudit.md — New Page

**Title:** Reliability Audit for LLM Financial Research

**Summary:**
A reliability audit layer evaluates LLM-generated equity reports claim-by-claim against primary financial sources. It distinguishes between:
- Claims that can be verified (machine-verifiable)
- Claims that are correct vs. incorrect vs. unsupported
- Claims that are forward-looking or qualitative (not machine-verifiable)

**Key metrics:**
- SCR (Source Coverage Rate): fraction of claims that could be checked
- ICR (Incorrect Claim Rate): fraction of machine-verifiable claims that were wrong
- VD (Valuation Dispersion): spread of valuation multiples in the report

**Important caveat on ICR:** High ICR (e.g. NVDA 53%) is often an extraction artifact, not a true hallucination rate. The regex period-attribution error assigns both "$27B in 2021" and "$60B in 2022" to period=2021 when scanning a multi-year sentence. This counts as incorrect when the earlier figure doesn't match the later year's actual value. Manual review required to separate true errors from extraction artifacts.

**Source hierarchy for verification:**
1. SEC EDGAR XBRL (revenue, net income, EBITDA proxy)
2. Exchange price feeds / yfinance (prices, returns)
3. FMP free tier (P/E, EV/EBITDA, margins, FCF)

**Connection to Burry / value investing:**
A reliability audit is essentially Burry's "read the actual 10-K" practice implemented as code. Burry verified his own claims against primary sources before building a thesis. The audit layer automates this check for LLM-generated research.

---

## Entry: wiki/career/applications/BlackRock-Prep.md — Update

Add under "Technical Artifacts":

**FinRobot Reliability Lab v0.4 (Jun 2026)**
- 10-stock benchmark across 9 metrics
- FMP integration raises source coverage from 2–4% to 16–51%
- Date-gated backtest: BUY signals +16.5% 6m vs. HOLD −16.4% 6m (+32.9pp spread)
- Adversarial critic: thesis stability 0.15–0.25 across NVDA/TSLA/META
- Published paper (draft): "Auditing LLM-Generated Financial Reports: A Reliability Framework for Multi-Agent Equity Research"

**Pitch framing for BlackRock:**
The reliability-as-harness insight is directly applicable to Aladdin Engineering: any LLM system deployed on financial data needs exactly this kind of verification layer. PR1 adds the architecture legibility (schemas, prompts, tests) that makes it readable to an engineering team.
