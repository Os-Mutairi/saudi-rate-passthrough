# Data dictionary

Sample: Jan 2009 to Jul 2026, monthly (211 observations). Downloaded 19 Oct 2026. Raw files in `data/raw/` are unmodified.

**Date convention:** each `date` (e.g. `2009-01-01`) labels the whole calendar month. It does not mean the value was observed on the 1st. See the treatment column for whether a value is a month-end observation or a monthly average.

| Variable | Description | Units | Source | Frequency / treatment |
|---|---|---|---|---|
| `fed_upper` | Fed funds target range, upper limit | % p.a. | FRED DFEDTARU | Daily -> month-end value |
| `fed_lower` | Fed funds target range, lower limit | % p.a. | FRED DFEDTARL | Daily -> month-end value |
| `fed_mid` | Fed target range midpoint, month-end (for charts) | % p.a. | Derived: (DFEDTARU + DFEDTARL) / 2 | Daily -> month-end value |
| `fed_mid_avg` | Fed target range midpoint, monthly average (additional prepared measure; not used in V1 regressions) | % p.a. | Derived: (DFEDTARU + DFEDTARL) / 2 | Daily -> monthly average |
| `sama_repo` | SAMA repo rate (RR) | % p.a. | SAMA Monetary Indicators: Interest Rates | Monthly, end of month |
| `sama_reverse_repo` | SAMA reverse repo rate (RRR) | % p.a. | SAMA Monetary Indicators: Interest Rates | Monthly, end of month |
| `saibor_3m` | 3-month SAIBOR, monthly average | % p.a. | SAMA Monetary Indicators: Interest Rates | Monthly average |
| `diff_sar_usd_3m` | 3M SAR minus USD interbank deposit rate spread. Descriptive only, NOT used in core regressions; does not by itself verify the exchange-rate peg | pp | SAMA Interest Rate Differentials | Monthly. USD leg moved from LIBOR to SOFR after Jul 2023 (break) |
| `credit_loans_advances` | Bank credit to private sector: loans, advances & overdrafts | SAR mn | SAMA Bank Claims On Private Sector | Monthly, end of month stock |
| `credit_bills_discounted` | Bank credit to private sector: bills discounted | SAR mn | SAMA Bank Claims On Private Sector | Monthly, end of month stock |
| `credit_total` | Bank credit to private sector, total (MAIN credit series) | SAR mn | SAMA Bank Claims On Private Sector | Monthly, end of month stock |
| `credit_total_yoy` | Year-on-year growth of private-sector bank credit (MAIN credit growth measure) | % | Derived from credit_total | Computed on full history from 1993, then trimmed |
| `private_securities` | Bank investments in private securities (excluded from lending analysis) | SAR mn | SAMA Bank Claims On Private Sector | Monthly |
| `claims_grand_total` | Total bank claims on private sector (credit + securities) | SAR mn | SAMA Bank Claims On Private Sector | Monthly |
| `brent_usd` | Brent crude, monthly average (main oil control) | USD/bbl | FRED POILBREUSDM (IMF) | Monthly average |
| `dubai_usd` | Dubai crude, monthly average (robustness check) | USD/bbl | FRED POILDUBUSDM (IMF) | Monthly average |

**Optional extension:** `real_estate_quarterly.csv`: real estate loans by banks (retail, corporate, total), SAR mn, quarterly only (SAMA does not publish this series monthly).

**Notes**
- Fed policy is measured by the target range, not the effective fed funds rate.
- Both SAMA policy rates are kept: the repo rate was unchanged at 2% from 2009 to Feb 2018 while the reverse repo rate moved with the Fed from Dec 2015.
- SAMA data end in Aug 2026, so the Fed hike of 17 Sep 2026 is not yet reflected in Saudi series.
- Timing: SAMA policy rates are month-end observations, while SAIBOR and `fed_mid_avg` are monthly averages. This dataset therefore supports alignment BY MONTH only, and a SAMA-to-SAIBOR comparison mixes month-end and average values. Decision-level timing, and monthly-average SAMA rates, require dated announcements (built separately in notebook 02).
- SAR-USD spread break: SAMA's own footnote to this table states that the USD reference rate moved from LIBOR to SOFR as of July 2023, so the spread is not like-for-like across that date. Source: SAMA Statistical Report, Monetary Indicators: Interest Rates, footnote (2).
- Oil, Mar 2026: Dubai (~$127) is far above Brent (~$99). The values match the raw FRED/IMF files, so this is not a parsing error. Contemporary market reports describe a record Dubai premium over Brent in March 2026: S&P Global Commodity Insights, 'Platts cash Dubai crosses $100/b mark' (6 Mar 2026), https://www.spglobal.com/energy/en/news-research/latest-news/crude-oil/030626-middle-east-crude-benchmark-platts-cash-dubai-crosses-100b-mark ; QCintel, 'Dubai crude nears $170/b, record premium over Brent at $55/b', https://www.qcintel.com/article/dubai-crude-nears-170-b-record-premium-over-brent-at-55-b-61306.html . The cause of the premium is not established by this dataset. Brent is the main control; results are re-checked with Dubai.