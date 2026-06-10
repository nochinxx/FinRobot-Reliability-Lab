# FinRobot Reliability Lab — Ticker Universe

## Phase 1 (10 tickers — COMPLETE)
COP, MSFT, META, NVDA, TSLA, ETSY, ROKU, RIVN, RBLX, LCID

## Dropped (FMP 402 errors)
DOCN, ZI, PTON, VFC, ALRM

---

## Phase 3 — G1 Expansion (90 new tickers — Jun 10 2026)

Selection criteria:
- US-listed, S&P 500 or well-covered mid-cap
- FMP free tier coverage confirmed (positive P/E history available)
- Avoid: loss-making startups without ratio history, very recent IPOs
- Sector diversity: Technology, Healthcare, Finance, Consumer, Industrials, Materials, Real Estate, Utilities, Comm.

### Technology — Large Cap (16)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| AAPL | Apple | MSFT, GOOGL |
| GOOGL | Alphabet | META, MSFT |
| AMZN | Amazon | GOOGL, MSFT |
| NFLX | Netflix | DIS, CMCSA |
| AMD | Advanced Micro Devices | NVDA, INTC |
| INTC | Intel | AMD, QCOM |
| ORCL | Oracle | CRM, SAP |
| CRM | Salesforce | NOW, ORCL |
| ADBE | Adobe | CRM, ORCL |
| QCOM | Qualcomm | AVGO, TXN |
| TXN | Texas Instruments | QCOM, ADI |
| AMAT | Applied Materials | LRCX, KLAC |
| MU | Micron Technology | WDC, NAND |
| AVGO | Broadcom | QCOM, AMAT |
| NOW | ServiceNow | CRM, ADBE |
| SNPS | Synopsys | CDNS, ANSS |

### Technology — Cloud/SaaS (8)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| PANW | Palo Alto Networks | CRWD, FTNT |
| CRWD | CrowdStrike | PANW, ZS |
| ZS | Zscaler | PANW, OKTA |
| NET | Cloudflare | AKAM, FSLY |
| DDOG | Datadog | NEWR, DYTR |
| SNOW | Snowflake | DBRKS, DBX |
| MDB | MongoDB | CLDR, ESTC |
| TEAM | Atlassian | MSFT, JIRA |

### Healthcare (14)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| JNJ | Johnson & Johnson | PFE, ABT |
| PFE | Pfizer | MRK, ABBV |
| UNH | UnitedHealth Group | CVS, HUM |
| ABBV | AbbVie | BMY, LLY |
| MRK | Merck | PFE, ABBV |
| BMY | Bristol-Myers Squibb | MRK, ABBV |
| GILD | Gilead Sciences | ABBV, BMY |
| AMGN | Amgen | BIIB, GILD |
| TMO | Thermo Fisher | DHR, A |
| DHR | Danaher | TMO, ABT |
| ABT | Abbott Laboratories | JNJ, MDT |
| MDT | Medtronic | ABT, BSX |
| ISRG | Intuitive Surgical | MDT, SYK |
| LLY | Eli Lilly | PFE, ABBV |

### Finance (12)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| JPM | JPMorgan Chase | BAC, GS |
| BAC | Bank of America | JPM, C |
| GS | Goldman Sachs | MS, JPM |
| MS | Morgan Stanley | GS, BAC |
| BLK | BlackRock | TROW, IVZ |
| V | Visa | MA, AXP |
| MA | Mastercard | V, AXP |
| AXP | American Express | V, MA |
| C | Citigroup | BAC, JPM |
| WFC | Wells Fargo | BAC, JPM |
| SCHW | Charles Schwab | TD, ETSY |
| ICE | Intercontinental Exchange | CME, NDAQ |

### Consumer Staples + Discretionary (12)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| WMT | Walmart | COST, TGT |
| COST | Costco | WMT, TGT |
| TGT | Target | WMT, COST |
| HD | Home Depot | LOW, COST |
| NKE | Nike | ADDYY, PUMSY |
| SBUX | Starbucks | MCD, YUM |
| MCD | McDonald's | SBUX, YUM |
| DIS | Walt Disney | CMCSA, NFLX |
| CMCSA | Comcast | DIS, T |
| PEP | PepsiCo | KO, MNST |
| KO | Coca-Cola | PEP, MNST |
| PG | Procter & Gamble | KMB, CL |

### Industrials (9)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| CAT | Caterpillar | DE, CNHI |
| DE | Deere | CAT, AGCO |
| GE | GE Aerospace | HON, RTX |
| HON | Honeywell | GE, MMM |
| RTX | RTX Corp | LMT, NOC |
| LMT | Lockheed Martin | RTX, NOC |
| UPS | United Parcel Service | FDX, ODFL |
| BA | Boeing | RTX, LMT |
| ETN | Eaton | HON, EMR |

### Communication Services (5)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| T | AT&T | VZ, TMUS |
| VZ | Verizon | T, TMUS |
| TMUS | T-Mobile | T, VZ |
| CHTR | Charter Communications | CMCSA, DISH |
| WBD | Warner Bros. Discovery | DIS, NFLX |

### Materials (5)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| LIN | Linde | APD, AIR |
| APD | Air Products | LIN, CE |
| ECL | Ecolab | IFF, RPM |
| NUE | Nucor | STLD, X |
| FCX | Freeport-McMoRan | AA, VALE |

### Real Estate (5)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| AMT | American Tower | EQIX, CCI |
| PLD | Prologis | EXR, SPG |
| EQIX | Equinix | AMT, CCI |
| SPG | Simon Property Group | MAC, PLD |
| PSA | Public Storage | EXR, CUBE |

### Utilities (4)
| Ticker | Company | Peer Set |
|--------|---------|----------|
| NEE | NextEra Energy | DUK, SO |
| DUK | Duke Energy | NEE, SO |
| SO | Southern Company | NEE, DUK |
| AEP | American Electric Power | SO, D |

---

## Batch Processing Order (3 daily batches, ~30 each)

### Batch A (Day 1 — 30 tickers)
AAPL, GOOGL, AMZN, NFLX, AMD, INTC, ORCL, CRM, ADBE, QCOM,
TXN, AMAT, MU, AVGO, NOW, PANW, CRWD, JNJ, PFE, UNH,
ABBV, MRK, BMY, GILD, AMGN, TMO, DHR, ABT, MDT, LLY

### Batch B (Day 2 — 30 tickers)
JPM, BAC, GS, MS, BLK, V, MA, AXP, C, WFC,
SCHW, ICE, WMT, COST, TGT, HD, NKE, SBUX, MCD, DIS,
CMCSA, PEP, KO, PG, ISRG, SNPS, ZS, NET, DDOG, SNOW

### Batch C (Day 3 — 30 tickers)
MDB, TEAM, CAT, DE, GE, HON, RTX, LMT, UPS, BA,
ETN, T, VZ, TMUS, CHTR, WBD, LIN, APD, ECL, NUE,
FCX, AMT, PLD, EQIX, SPG, PSA, NEE, DUK, SO, AEP

---

## Notes
- FMP 250 calls/day limit: each ticker = ~6 FMP calls + 1 SEC EDGAR call.
  Batch A + B cache warm = 60 tickers × 6 = 360 FMP calls → 2 days.
  Cache all 90 before running batch audit.
- Report generation: Gemma4 12B via Ollama (~3-10 min per ticker).
  Generate in same batches; run overnight.
- FinRobot report generation command (per ticker):
  ```bash
  cd finrobot_equity/core/src
  conda run -n agent python generate_financial_analysis.py \
    --company-ticker AAPL --company-name "Apple Inc." \
    --generate-text-sections --output-dir ../output/AAPL/analysis
  ```
