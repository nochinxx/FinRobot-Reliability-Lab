# Data Contracts

All schemas are formally defined in `schemas/`. This document describes each contract in prose, including field semantics, known limitations, and planned extensions.

---

## 1. `claims.json` — Extracted Claims

**File:** `output/{TICKER}/{TICKER}_claims.json`  
**Schema:** `schemas/claim.schema.json`  
**Produced by:** `reliability_lab/claim_extraction.py`

Each item represents one extracted financial claim from the FinRobot HTML report.

| Field | Type | Description |
|-------|------|-------------|
| `claim_text` | string | 120-char context window around the matched value. This is the surrounding sentence fragment, not the full sentence. |
| `claim_type` | enum | `financial \| valuation \| stock-price \| guidance \| peer-comparison \| catalyst \| risk \| narrative` |
| `metric` | string | `revenue \| ebitda \| eps \| pe_ratio \| ev_ebitda \| revenue_growth \| ebitda_margin \| gross_margin \| net_income \| free_cash_flow \| market_cap \| total_debt \| financial_figure \| growth_rate` |
| `period` | string\|null | Nearest fiscal year string (e.g. `"2023"`). **Known limitation:** `_nearest_year()` searches ±200 chars; in multi-year sentences it may return the wrong year. |
| `value` | number\|null | Normalized numeric value. Dollars normalized to USD (not billions). Percentages stored as raw numbers (e.g. `16.5` for 16.5%). Multiples stored as raw float (e.g. `37.7` for 37.7x). |
| `value_display` | string | Human-readable value as it appears in report text (e.g. `"$60.9 billion"`, `"37.7x"`, `"16.5%"`). |
| `unit` | enum | `USD \| percent \| multiple \| shares` |
| `source_status` | string | Always `"unverified"` at extraction time. Updated in fact table. |
| `confidence` | enum | `high \| medium \| low`. Set by extraction method — LLM assigns confidence; regex defaults to `medium`. |
| `extraction_method` | enum | `regex \| llm` |
| `ticker` | string | Uppercase ticker (e.g. `"NVDA"`) |

**Planned additions (PR2):** `prompt_version`, `prompt_hash`, `model_name`, `provider`, `input_hash`, `output_hash` when extraction_method=llm.

---

## 2. `fact_table.csv` — Verified Fact Rows

**File:** `output/{TICKER}/{TICKER}_fact_table.csv`  
**Schema:** `schemas/fact_row.schema.json`  
**Produced by:** `reliability_lab/fact_table_builder.py`

One row per claim, with verification result added.

| Column | Description |
|--------|-------------|
| `ticker` | Uppercase ticker |
| `claim_type` | From claims.json |
| `metric` | From claims.json |
| `period` | From claims.json (may be wrong — see period attribution artifact) |
| `claimed_value` | `value_display` from claims.json (human-readable string) |
| `verified_value` | String representation of the primary-source value (e.g. `"$26.97B"`, `"37.7x"`). Empty if not verifiable. |
| `source` | Human-readable source label (e.g. `"SEC EDGAR 10-K"`, `"FMP ratios FY2023"`) |
| `verification_status` | `verified \| incorrect \| unsupported \| not_machine_verifiable` (SOURCE_CONFLICT planned for PR3) |
| `notes` | First 200 chars of `claim_text`. Not a structured audit note — raw context from extraction. |

**Verification status semantics:**
- `verified` — claimed value matches primary source within tolerance
- `incorrect` — claimed value differs from primary source beyond tolerance (may be period attribution artifact, not hallucination — check manually)
- `unsupported` — no primary source found; claim cannot be checked
- `not_machine_verifiable` — guidance/forward-looking, peer comparison, period > 2025, or no verifier implemented
- `SOURCE_CONFLICT` (PR3) — multiple sources give different values beyond tolerance; Tier 1 wins but all values recorded

**Tolerances:**
- Revenue / financial figures: 2% (SEC EDGAR) or 5% (FMP)
- Valuation multiples: 10–15% (snapshot-date sensitive)
- EBITDA proxy: 15% (uses op. income + D&A approximation)
- Market cap: 20% (current snapshot only)

---

## 3. `reliability_scorecard.json` — Reliability Scorecard

**File:** `output/{TICKER}/{TICKER}_reliability_scorecard.json`  
**Schema:** `schemas/reliability_scorecard.schema.json`  
**Produced by:** `reliability_lab/reliability_metrics.py`

```json
{
  "summary": {
    "total_claims": 100,
    "machine_verifiable_claims": 30,
    "verified_count": 14,
    "incorrect_count": 16,
    "unsupported_count": 0,
    "not_machine_verifiable": 70
  },
  "metrics": {
    "source_coverage_rate": 0.30,
    "primary_source_coverage_rate": 0.467,
    "unsupported_claim_rate": 0.0,
    "incorrect_claim_rate": 0.533,
    "valuation_dispersion": 0.495
  },
  "thresholds": {
    "source_coverage_rate": {"value": 0.30, "target": "≥0.80", "pass": false},
    ...
  },
  "by_metric": {
    "revenue": {"total": 17, "verified": 3, "incorrect": 2, "unsupported": 0, "not_machine_verifiable": 12},
    ...
  }
}
```

**Metric definitions:**
- `source_coverage_rate (SCR)` = (verified + incorrect) / total — fraction of claims that could be checked against a source
- `primary_source_coverage_rate (PSCR)` = verified / machine_verifiable — of those checkable, fraction that matched
- `unsupported_claim_rate (UCR)` = unsupported / total
- `incorrect_claim_rate (ICR)` = incorrect / machine_verifiable — **WARNING:** high ICR is likely an extraction artifact (period attribution) not a hallucination rate. Do not report as hallucination without manual review.
- `valuation_dispersion (VD)` = stdev(multiples) / mean(multiples) — spread of valuation multiples claimed in the report

**Current pass/fail thresholds (hardcoded in reliability_metrics.py):**
- SCR ≥ 0.80 (current typical: 0.16–0.51 — threshold not yet achievable)
- PSCR ≥ 0.90
- UCR ≤ 0.15
- ICR ≤ 0.05

These thresholds represent a future target state, not current performance. They will be made configurable in PR2 via `scoring/gates.py`.

---

## 4. `critic_findings.json` — Adversarial Critic Output

**File:** `output/{TICKER}/{TICKER}_critic_findings.json`  
**Schema:** `schemas/critic_findings.schema.json`  
**Produced by:** `reliability_lab/critic_agents.py`

```json
{
  "challenges": [
    {
      "original_claim": "exact phrase from report",
      "challenge": "why this claim is wrong or unsupported",
      "likely_actual": "what the real figure likely is",
      "thesis_impact": "changes_thesis | minor_factual | confirms_thesis",
      "severity": "high | medium | low"
    }
  ],
  "revised_recommendation": "buy | hold | sell | avoid",
  "revised_rationale": "2-3 sentence rationale",
  "thesis_stability_score": 0.25
}
```

**thesis_stability_score:** `1 − (thesis_changing_challenges / total_challenges)`.  
1.0 = thesis unchanged; 0.0 = thesis completely overturned.  
**Important:** This score is LLM self-reported — the model classifies its own challenges as `changes_thesis` or `minor_factual`. It is a proxy, not a ground-truth measurement. Do not cite as objective without this caveat.

**Planned additions (PR2):** `run_metadata` block with model, provider, temperature, prompt_hash, input_hash, output_hash, fallback_used.

---

## 5. `backtest_snapshot.json` — Backtest Window

**File:** `output/historical_backtest/{TICKER}_{YYYY-MM}_snapshot.json`  
**Schema:** `schemas/backtest_snapshot.schema.json`  
**Produced by:** `run_historical_backtest.py`

```json
{
  "ticker": "NVDA",
  "cutoff_date": "2025-06-01",
  "price_at_cutoff": 139.79,
  "valuation": {
    "pe_ratio": 39.9,
    "ev_ebitda": 33.78,
    "mean_pe_history": 65.87,
    "mean_ev_history": 53.25,
    "net_profit_margin": 55.8,
    "gross_profit_margin": 75.0,
    "profitability_score": 6,
    "signal": "buy",
    "rationale": "P/E 39.9x is 39% below historical mean 65.9x | ...",
    "ratio_history_depth": 4
  },
  "fmp_records": {"ratios": 4, "cash_flow": 4, "balance_sheet": 4},
  "returns": {
    "return_3m": 24.32, "alpha_3m": 15.98,
    "return_6m": 30.98, "alpha_6m": 15.55,
    "return_9m": 32.85, "alpha_9m": 16.04,
    "return_12m": 62.23, "alpha_12m": 32.61
  },
  "spy_returns": {"spy_3m": 8.34, "spy_6m": 15.43, "spy_9m": 16.81, "spy_12m": 29.62}
}
```

**Signal logic:** BUY if P/E or EV/EBITDA is ≥15% below historical mean. SELL if ≥30% above. HOLD otherwise.  
**Data gate:** only FMP records with `date ≤ cutoff_date` are used. No forward data leaks.  
**Important:** This signal is independent of FinRobot's recommendations and of the adversarial critic. Do not conflate.

---

## 6. `run_metadata` — Audit Run Provenance

**Not yet implemented.** Planned for PR2.  
**Schema:** `schemas/run_metadata.schema.json`

Every LLM call and audit run will record:

| Field | Description |
|-------|-------------|
| `run_id` | UUID for this specific run |
| `timestamp` | ISO8601 |
| `ticker` | Stock ticker |
| `phase` | `claim_extraction \| fact_verification \| adversarial_critic \| backtest` |
| `model_name` | e.g. `claude-sonnet-4-6`, `gemma4:12b-mlx` |
| `provider` | `anthropic \| ollama_fallback` |
| `temperature` | Float (0.0 for critic calls) |
| `prompt_file` | e.g. `prompts/skeptical_analyst_v1.txt` |
| `prompt_hash` | SHA-256 of prompt file contents |
| `input_hash` | SHA-256 of the actual input sent to the model |
| `output_hash` | SHA-256 of the raw model response |
| `fallback_used` | Boolean — true if Ollama was used instead of Anthropic |
| `source_tier` | Tier of the data source for verification calls |
