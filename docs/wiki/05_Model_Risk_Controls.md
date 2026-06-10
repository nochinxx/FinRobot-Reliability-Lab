# 05 Model-Risk Controls

## Current Controls (PR1 state)

- Raw input preservation: HTML reports stored in `finrobot_equity/core/output/`
- Prompt files: extracted to `prompts/` with versioned filenames
- Source response caching: FMP 24h file cache in `reliability_lab/output/fmp_cache/`
- Scorecard generation: `reliability_lab/reliability_metrics.py`
- Fixture-based regression tests: 91 tests in `tests/`
- Backtest data cutoff enforcement: `run_historical_backtest.py` gates FMP data by cutoff_date

## Missing Controls (planned per PR)

### PR2 — Minimum viable for demo
- [ ] Run-level provenance logging (`run_metadata.schema.json` implemented but not wired)
- [ ] Prompt hash logging (detect accidental prompt changes)
- [ ] Model/version logging per LLM call
- [ ] temperature=0 enforcement for all critic calls

### PR3 — Before analyst decision support
- [ ] Source hierarchy enforcement (SOURCE_CONFLICT resolution)
- [ ] Deterministic verification for all quantitative claims (currently partial)
- [ ] Reproducible experiment manifests (`experiment_manifest.schema.json`)
- [ ] Gate decision object (`gate_decision.schema.json`)
- [ ] Clear disclaimers in all output files

### PR4+ — Before portfolio use (not current scope)
- [ ] Independent validation
- [ ] Look-ahead and survivorship bias controls
- [ ] Factor exposure controls (sector, size, beta, momentum)
- [ ] Transaction cost model
- [ ] Human approval workflow
- [ ] Audit logs suitable for model-risk review board

## Default Gate Policy (planned for PR3)

| Decision | Conditions |
|----------|-----------|
| PASS | SCR ≥ 0.80, ICR ≤ 0.05, UCR ≤ 0.15, no HIGH-severity thesis errors |
| HUMAN_REVIEW | SCR 0.50–0.80, or valuation_dispersion > 0.10, or unresolved SOURCE_CONFLICT |
| FAIL | ICR > 0.30, or missing cutoff metadata, or unsupported recommendation, or source hierarchy violation |

## Determinism Requirements

- All LLM calls: temperature=0
- Log: model_name, provider, prompt_version, prompt_hash, input_hash, output_hash
- Ollama fallback: tag output with `provider: "ollama_fallback"` — do NOT mix with Anthropic outputs in aggregate stats
