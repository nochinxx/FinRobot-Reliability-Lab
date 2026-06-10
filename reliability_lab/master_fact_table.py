"""
Master fact table builder.

Merges fact rows across all tickers into output/master_fact_table.csv.

Master status mapping (supersedes per-ticker verification_status):
  LOCKED      — verified against Tier 1 (SEC EDGAR / exchange)
  PROVISIONAL — verified against Tier 3 (FMP) only
  CONFLICT    — SOURCE_CONFLICT between Tier 1 and Tier 3
  INCORRECT   — confirmed wrong against primary source
  UNVERIFIED  — unsupported / not_machine_verifiable
"""
import csv
from pathlib import Path


MASTER_STATUSES = ["LOCKED", "PROVISIONAL", "CONFLICT", "INCORRECT", "UNVERIFIED"]

MASTER_COLUMNS = [
    "ticker",
    "claim_type",
    "metric",
    "period",
    "claimed_value",
    "verified_value",
    "source",
    "source_tier",
    "verification_status",
    "master_status",
    "verified_value_alt",
    "source_alt",
    "conflict_details",
    "notes",
]

_TIER1_SOURCES = {
    "SEC EDGAR 10-K",
    "SEC EDGAR 10-K (op. income + D&A)",
    "SEC EDGAR 10-K revenue FY",
}


def _master_status(row: dict) -> str:
    status = row.get("verification_status", "")
    tier   = str(row.get("source_tier", "")).strip()
    source = row.get("source", "")

    if status == "SOURCE_CONFLICT":
        return "CONFLICT"

    if status == "incorrect":
        return "INCORRECT"

    if status == "verified":
        # Tier 1 confirmed → LOCKED; Tier 3 only → PROVISIONAL
        if tier == "1" or any(source.startswith(t) for t in _TIER1_SOURCES):
            return "LOCKED"
        return "PROVISIONAL"

    return "UNVERIFIED"


def load_fact_rows(ticker: str, base_output_dir: str = "output") -> list[dict]:
    path = Path(base_output_dir) / ticker / f"{ticker}_fact_table.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def merge_fact_tables(
    tickers: list[str],
    base_output_dir: str = "output",
) -> list[dict]:
    """Load per-ticker fact tables and merge into master rows with master_status."""
    merged = []
    for ticker in tickers:
        rows = load_fact_rows(ticker, base_output_dir)
        for row in rows:
            master = dict(row)
            master["master_status"] = _master_status(row)
            # Ensure all MASTER_COLUMNS present (fill missing with "")
            for col in MASTER_COLUMNS:
                master.setdefault(col, "")
            merged.append(master)
    return merged


def status_summary(merged_rows: list[dict]) -> dict:
    """Return counts per master_status across all rows."""
    counts = {s: 0 for s in MASTER_STATUSES}
    for row in merged_rows:
        ms = row.get("master_status", "UNVERIFIED")
        if ms in counts:
            counts[ms] += 1
        else:
            counts["UNVERIFIED"] += 1
    counts["total"] = len(merged_rows)
    return counts


def save_master_fact_table(
    merged_rows: list[dict],
    output_dir: str = "output",
) -> Path:
    out = Path(output_dir) / "master_fact_table.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=MASTER_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(merged_rows)
    return out
