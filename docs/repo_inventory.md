# Repository Inventory

## Active Files and Directories

### Entry Points (CLIs)

| File | Purpose | Status |
|------|---------|--------|
| `run_reliability_audit.py` | Main audit pipeline (phases 1–5) | Active — do not modify |
| `run_historical_backtest.py` | Date-gated backtesting (9 tickers × 3 dates) | Active — do not modify |
| `backtest_signal.py` | Experimental signal backtest using claims-derived target prices | Active (experimental) — do not modify |
| `run_equity_agent.py` | FinRobot HTML report generator (Ollama Gemma4) | Active — do not modify |
| `run_web_app.py` | Flask web app stub | Inactive — not used in production |

### Core Audit Library

| File | Purpose |
|------|---------|
| `reliability_lab/claim_extraction.py` | Regex + LLM claim extractor |
| `reliability_lab/fact_table_builder.py` | Verifier dispatcher → fact table |
| `reliability_lab/reliability_metrics.py` | Scorecard computation + pass/fail thresholds |
| `reliability_lab/critic_agents.py` | Adversarial critic (Skeptical Analyst + Thesis Synthesizer) |
| `reliability_lab/verifiers/sec_verifier.py` | SEC EDGAR XBRL verification |
| `reliability_lab/verifiers/fmp_verifier.py` | FMP multi-metric verifier + date-gated backtest data fetch |
| `reliability_lab/verifiers/price_verifier.py` | yfinance price/return verification |

### Configuration

| File | Contents |
|------|----------|
| `config_api_keys` | JSON with FMP_API_KEY (active), others placeholder |
| `OAI_CONFIG_LIST` | Ollama / OpenAI config for FinRobot agents |
| `configs/save_config_forecaster.json` | FinRobot forecaster config |
| `CLAUDE.md` | Agent operating rules (comprehensive — read before any work) |
| `AGENTS.md` | Git and Python environment rules |

### Upstream FinRobot (Black Box — Do Not Modify)

| Path | Contents |
|------|----------|
| `finrobot_equity/core/src/` | 8 equity agents, financial data processor, HTML renderer |
| `finrobot_equity/core/output/` | Generated HTML reports + analysis CSVs per ticker |
| `finrobot/` | FinRobot library (data sources, toolkits, functional modules) |

### Output Directories

| Path | Contents | Status |
|------|----------|--------|
| `output/COP/` | Phase 1 audit: claims, fact_table, scorecard, summary | Done |
| `output/MSFT/` | Phase 1 audit | Done |
| `output/META/` | Phase 1 audit + Phase 5 critic | Done |
| `output/NVDA/` | Phase 1 audit + Phase 5 critic | Done |
| `output/TSLA/` | Phase 1 audit + Phase 5 critic | Done |
| `output/ETSY/` | Phase 2 audit | Done |
| `output/ROKU/` | Phase 2 audit | Done |
| `output/RIVN/` | Phase 2 audit | Done |
| `output/RBLX/` | Phase 2 audit | Done |
| `output/LCID/` | Phase 2 audit | Done |
| `output/historical_backtest/` | 27 snapshots + results.csv + paper_table.md | Done (v0.4 paper) |
| `output/table_parse_preview/` | HTML table parser PoV output | PR1 (in progress) |

### Empty / Abandoned Output Directories

| Path | Note |
|------|------|
| `output/DOCN/` | DigitalOcean — FMP 402 on free tier; audit not completed |
| `output/ZI/` | ZoomInfo — FMP 402 on free tier; audit not completed |

**Rule:** Do not delete DOCN or ZI without Mario's explicit instruction. Keep as inventory placeholders. If adding new tickers, confirm FMP free tier availability first.

### Paper

| File | Contents |
|------|----------|
| `paper/reliability_audit_paper.md` | v0.4, ~38k chars. Primary deliverable. |

**Two fixes needed before submission:**
1. Section 5.8 (adversarial critic) appears before 5.7 (backtesting) — needs swap
2. Section 4.2 pilot stock list shows wrong tickers — needs update

### Sample Reports (for testing / reference)

| File | Contents |
|------|----------|
| `report/NVDA_report.pdf` | NVDA PDF report sample |
| `report/2023-07-27_10-K_msft-20230630.htm.pdf` | MSFT 10-K PDF |
| `report/Microsoft_Annual_Report_2023.pdf` | MSFT annual report |

### PR1 Additions (Jun 8 2026)

| Path | Contents |
|------|----------|
| `docs/` | architecture.md, data_contracts.md, source_hierarchy.md, repo_inventory.md, wiki_update_draft.md |
| `prompts/` | Versioned LLM prompt files extracted from inline strings |
| `schemas/` | JSON Schema definitions for all data contracts |
| `tests/` | Fixture-based unit tests (no live API calls) |
| `tests/fixtures/` | Sample data files for tests |
| `tools/html_table_parser.py` | Standalone HTML table parser (proof-of-value only) |
| `output/table_parse_preview/` | Parser output previews per ticker |

### Experiments (Not Production)

| File | Purpose |
|------|---------|
| `experiments/investment_group.py` | Multi-agent investment group experiment |
| `experiments/multi_factor_agents.py` | Multi-factor agent experiment |
| `experiments/portfolio_optimization.py` | Portfolio optimization experiment |
| `agent_builder_demo.py` | AutoGen agent builder demo |

### Tutorials (Reference Only)

| Path | Contents |
|------|----------|
| `tutorials_advanced/` | 6 Jupyter notebooks — annual report, forecaster, OpenBB, trade strategist |
| `tutorials_beginner/` | 6 Jupyter notebooks — RAG, Q&A, Ollama basics |

### FMP Cache

| Path | Contents |
|------|----------|
| `reliability_lab/output/fmp_cache/` | ~40 JSON files, 24h TTL. 9 tickers × {ratios, key-metrics, cash-flow-statement, balance-sheet-statement, ratios}. |

**Rule:** Do not delete or invalidate this cache without explicit instruction. Rebuilding costs ~40 FMP API calls.

---

## File Count Summary

| Category | Count |
|----------|-------|
| Python source files | ~35 |
| HTML reports (FinRobot output) | ~15 |
| Audit output JSON/CSV/MD files | ~80+ |
| Backtest snapshots | 27 |
| FMP cache files | ~40 |
| Jupyter notebooks | 12 |
