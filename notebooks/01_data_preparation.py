# -*- coding: utf-8 -*-
"""
01_data_preparation.py
======================
From US Rates to Saudi Credit: How Interest-Rate Changes Pass Through
to the Saudi Economy

Step 1 of the methodology: load every raw file, convert to monthly,
align on one date index, check coverage and data quality, and save
clean files to data/processed/.

How to run in Spyder
--------------------
Run it one cell at a time (each "# %%" block) with Shift + Enter,
or run the whole file with F5. Nothing in data/raw/ is ever modified.

Outputs
-------
data/processed/monthly_panel.csv        <- main dataset for notebooks 02-04
data/processed/real_estate_quarterly.csv
data/processed/coverage_table.csv
data/processed/data_dictionary.md
charts/01_policy_rates.png              <- quick sanity-check chart
"""

# %% 0. Setup ---------------------------------------------------------------
import email
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

# Project folder. If you saved the project somewhere else, change this line.
PROJECT = Path.home() / "saudi-rate-passthrough"
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
CHARTS = PROJECT / "charts"
PROCESSED.mkdir(parents=True, exist_ok=True)
CHARTS.mkdir(parents=True, exist_ok=True)

# Common sample agreed in the design: starts when the Fed moved to a
# target *range* (Dec 2008) -> first full month is Jan 2009.
SAMPLE_START = "2009-01-01"

print("Raw files found:")
for f in sorted(RAW.iterdir()):
    print("  ", f.name)


# %% 1. Helper: read SAMA's ".xls" exports ----------------------------------
# SAMA's "Export (Excel)" button does NOT produce a real Excel file. It is a
# web page (HTML) packed inside an email-style container, with one page per
# sheet: Annually, Quarterly, Monthly. So instead of pd.read_excel we unpack
# it ourselves using only Python's standard library (no extra installs).

class _TableParser(HTMLParser):
    """Collects every table row as a list of cell texts."""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._in_cell = [], None, "", False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell = True, ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append(" ".join(self._cell.split()))
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_cell:
            self._cell += data


def read_sama_export(path):
    """Return {sheet_name: list_of_rows} for a SAMA statistical export.
    Returns None if the file is not in SAMA's multi-sheet format."""
    msg = email.message_from_bytes(path.read_bytes())
    names = {"sheet0.htm": "Annually", "sheet1.htm": "Quarterly",
             "sheet2.htm": "Monthly"}
    sheets = {}
    for part in msg.walk():
        loc = part.get("Content-Location", "")
        if loc in names:
            parser = _TableParser()
            parser.feed(part.get_payload(decode=True).decode("utf-8"))
            sheets[names[loc]] = parser.rows
    return sheets or None


def sheet_to_frame(rows, columns, date_format):
    """Keep only rows whose first cell is a date, name the columns,
    and convert text like '2,034,085' into numbers."""
    data = []
    for r in rows:
        if not r:
            continue
        try:
            if date_format == "quarter":   # e.g. "Q1 2009" -> 2009-01-01
                q, year = r[0].split()
                assert q in ("Q1", "Q2", "Q3", "Q4") and year.isdigit()
                date = pd.Timestamp(int(year), 3 * int(q[1]) - 2, 1)
            else:
                date = pd.to_datetime(r[0], format=date_format)
        except (ValueError, TypeError, AssertionError):
            continue  # header, footnote or blank row
        values = [pd.to_numeric(v.replace(",", ""), errors="coerce")
                  for v in r[1:1 + len(columns)]]
        data.append([date] + values)
    df = pd.DataFrame(data, columns=["date"] + columns).set_index("date")
    # SAMA's export repeats some rows; keep one copy of each date
    return df[~df.index.duplicated(keep="first")].sort_index()


# %% 2. Identify which SAMA file is which ------------------------------------
# All SAMA downloads have similar names, so we recognise them by content.
sama = {}
for f in sorted(RAW.glob("SAMA*.xls")):
    sheets = read_sama_export(f)
    if sheets is None:
        print(f"Skipped (not a multi-sheet SAMA export): {f.name}")
        continue
    header_text = " ".join(" ".join(r) for r in sheets["Annually"][:6])
    if "Monetary Indicators" in header_text:
        sama["rates"] = sheets
    elif "Bank Claims On Private Sector" in header_text:
        sama["credit"] = sheets
    elif "Real Estate Loans" in header_text:
        sama["real_estate"] = sheets
    print(f"{f.name}: {header_text[:70]}...")

missing = {"rates", "credit"} - sama.keys()
assert not missing, f"Missing core SAMA files: {missing}"


# %% 3. SAMA interest rates (monthly) ----------------------------------------
rate_cols = [
    "sama_repo", "sama_reverse_repo", "saibor_3m",
    "sama_bill_1w", "sama_bill_4w", "sama_bill_13w", "sama_bill_26w",
    "sama_bill_52w",
    "sar_dep_1m", "sar_dep_3m", "sar_dep_6m", "sar_dep_12m",
    "usd_dep_1m", "usd_dep_3m", "usd_dep_6m", "usd_dep_12m",
    "diff_sar_usd_1m", "diff_sar_usd_3m", "diff_sar_usd_6m",
    "diff_sar_usd_12m",
]
rates = sheet_to_frame(sama["rates"]["Monthly"], rate_cols, "%Y-%b")

# Keep only what V1 needs; the deposit differential is kept for the
# peg check (Assumption: verify the exchange-rate regime).
rates = rates[["sama_repo", "sama_reverse_repo", "saibor_3m",
               "diff_sar_usd_3m"]]
print(rates.tail())


# %% 4. SAMA private-sector credit (monthly, SAR million) --------------------
credit_cols = ["credit_loans_advances", "credit_bills_discounted",
               "credit_total", "private_securities", "claims_grand_total"]
credit = sheet_to_frame(sama["credit"]["Monthly"], credit_cols, "%b %Y")

# Quality check 1: loans + bills discounted should equal bank credit total
gap = (credit["credit_loans_advances"] + credit["credit_bills_discounted"]
       - credit["credit_total"]).abs().max()
print(f"Max gap, components vs credit total: {gap:.4f} SAR mn")

# Quality check 2: credit total + securities should equal grand total.
# This also documents WHY we use bank credit, not total claims.
gap2 = (credit["credit_total"] + credit["private_securities"]
        - credit["claims_grand_total"]).abs().max()
print(f"Max gap, credit + securities vs grand total: {gap2:.4f} SAR mn")

# Year-on-year credit growth, computed on the FULL history (from 1993)
# BEFORE trimming to 2009, so growth is available from the first month
# of the sample. (Computing it after trimming would lose 12 months.)
credit["credit_total_yoy"] = credit["credit_total"].pct_change(
    12, fill_method=None) * 100
print(credit.tail())


# %% 5. Real estate loans (QUARTERLY only - optional extension) --------------
if "real_estate" in sama:
    real_estate = sheet_to_frame(sama["real_estate"]["Quarterly"],
                                 ["re_loans_retail", "re_loans_corporate",
                                  "re_loans_total"], "quarter")
    real_estate.to_csv(PROCESSED / "real_estate_quarterly.csv")
    print(real_estate.tail())


# %% 6. FRED: Fed target range (daily -> monthly) ----------------------------
def read_fred(name):
    df = pd.read_csv(RAW / f"{name}.csv", parse_dates=["observation_date"])
    return df.set_index("observation_date")[name]


fed_upper = read_fred("DFEDTARU")
fed_lower = read_fred("DFEDTARL")

# Month-END value, to match SAMA's policy rates, which are reported as the
# rate in force at the end of each month.
fed = pd.DataFrame({
    "fed_upper": fed_upper.resample("MS").last(),
    "fed_lower": fed_lower.resample("MS").last(),
})
print("Range width (upper - lower) values seen:",
      (fed["fed_upper"] - fed["fed_lower"]).round(2).unique())

# Two versions of the Fed policy measure, used for different jobs:
#  - fed_mid      : month-END midpoint of the range -> descriptive charts,
#                   comparable with SAMA's end-of-month policy rates
#  - fed_mid_avg  : monthly AVERAGE of the daily midpoint -> an additional
#                   prepared measure, comparable with SAMA's monthly-average
#                   SAIBOR (a late-month hike barely moves a monthly average).
#                   The V1 regressions use SAMA policy-rate changes instead.
fed_mid_daily = (fed_upper + fed_lower) / 2
fed["fed_mid"] = fed_mid_daily.resample("MS").last()
fed["fed_mid_avg"] = fed_mid_daily.resample("MS").mean()


# %% 7. FRED: oil prices (already monthly averages) --------------------------
oil = pd.DataFrame({
    "brent_usd": read_fred("POILBREUSDM"),
    "dubai_usd": read_fred("POILDUBUSDM"),
})


# %% 8. Combine into one monthly panel ---------------------------------------
panel = pd.concat([fed, rates, credit, oil], axis=1, sort=True)
panel.index.name = "date"
panel = panel.loc[SAMPLE_START:]

# Trim to the last month where the CORE series are all available.
core = ["fed_upper", "sama_repo", "sama_reverse_repo", "saibor_3m",
        "credit_total", "brent_usd"]
last_complete = panel[core].dropna().index.max()
panel = panel.loc[:last_complete]
print(f"Common sample: {panel.index.min():%b %Y} to {panel.index.max():%b %Y}"
      f" ({len(panel)} months)")
print(panel.tail())


# %% 9. Coverage table -------------------------------------------------------
# Built from the full (untrimmed) series, so it shows true availability.
full = pd.concat([fed, rates, credit, oil], axis=1, sort=True)
coverage = []
for col in full.columns:
    s = full[col].dropna()
    expected = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    coverage.append({
        "series": col,
        "first": f"{s.index.min():%Y-%m}",
        "last": f"{s.index.max():%Y-%m}",
        "months": len(s),
        "missing_months": len(expected) - len(s),
        "missing_in_sample": int(panel[col].isna().sum()),
    })
coverage = pd.DataFrame(coverage)
coverage.to_csv(PROCESSED / "coverage_table.csv", index=False)
print(coverage.to_string(index=False))


# %% 10. Save the clean monthly panel ----------------------------------------
panel.to_csv(PROCESSED / "monthly_panel.csv")
print(f"Saved {PROCESSED / 'monthly_panel.csv'}")


# %% 11. Data dictionary -----------------------------------------------------
dictionary = [
    ("fed_upper", "Fed funds target range, upper limit", "% p.a.",
     "FRED DFEDTARU", "Daily -> month-end value"),
    ("fed_lower", "Fed funds target range, lower limit", "% p.a.",
     "FRED DFEDTARL", "Daily -> month-end value"),
    ("fed_mid", "Fed target range midpoint, month-end (for charts)", "% p.a.",
     "Derived: (DFEDTARU + DFEDTARL) / 2", "Daily -> month-end value"),
    ("fed_mid_avg", "Fed target range midpoint, monthly average "
     "(additional prepared measure; not used in V1 regressions)", "% p.a.",
     "Derived: (DFEDTARU + DFEDTARL) / 2", "Daily -> monthly average"),
    ("sama_repo", "SAMA repo rate (RR)", "% p.a.",
     "SAMA Monetary Indicators: Interest Rates", "Monthly, end of month"),
    ("sama_reverse_repo", "SAMA reverse repo rate (RRR)", "% p.a.",
     "SAMA Monetary Indicators: Interest Rates", "Monthly, end of month"),
    ("saibor_3m", "3-month SAIBOR, monthly average", "% p.a.",
     "SAMA Monetary Indicators: Interest Rates", "Monthly average"),
    ("diff_sar_usd_3m", "3M SAR minus USD interbank deposit rate spread. "
     "Descriptive only, NOT used in core regressions; does not by itself "
     "verify the exchange-rate peg", "pp",
     "SAMA Interest Rate Differentials",
     "Monthly. USD leg moved from LIBOR to SOFR after Jul 2023 (break)"),
    ("credit_loans_advances", "Bank credit to private sector: loans, "
     "advances & overdrafts", "SAR mn", "SAMA Bank Claims On Private Sector",
     "Monthly, end of month stock"),
    ("credit_bills_discounted", "Bank credit to private sector: bills "
     "discounted", "SAR mn", "SAMA Bank Claims On Private Sector",
     "Monthly, end of month stock"),
    ("credit_total", "Bank credit to private sector, total (MAIN credit "
     "series)", "SAR mn", "SAMA Bank Claims On Private Sector",
     "Monthly, end of month stock"),
    ("credit_total_yoy", "Year-on-year growth of private-sector bank credit "
     "(MAIN credit growth measure)", "%", "Derived from credit_total",
     "Computed on full history from 1993, then trimmed"),
    ("private_securities", "Bank investments in private securities "
     "(excluded from lending analysis)", "SAR mn",
     "SAMA Bank Claims On Private Sector", "Monthly"),
    ("claims_grand_total", "Total bank claims on private sector "
     "(credit + securities)", "SAR mn", "SAMA Bank Claims On Private Sector",
     "Monthly"),
    ("brent_usd", "Brent crude, monthly average (main oil control)", "USD/bbl",
     "FRED POILBREUSDM (IMF)", "Monthly average"),
    ("dubai_usd", "Dubai crude, monthly average (robustness check)",
     "USD/bbl", "FRED POILDUBUSDM (IMF)", "Monthly average"),
]
lines = ["# Data dictionary", "",
         f"Sample: {panel.index.min():%b %Y} to {panel.index.max():%b %Y}, "
         f"monthly ({len(panel)} observations). "
         "Downloaded 19 Oct 2026. Raw files in `data/raw/` are unmodified.",
         "",
         "**Date convention:** each `date` (e.g. `2009-01-01`) labels the "
         "whole calendar month. It does not mean the value was observed on "
         "the 1st. See the treatment column for whether a value is a "
         "month-end observation or a monthly average.",
         "",
         "| Variable | Description | Units | Source | Frequency / treatment |",
         "|---|---|---|---|---|"]
lines += [f"| `{v}` | {d} | {u} | {s} | {t} |" for v, d, u, s, t in dictionary]
lines += ["",
          "**Optional extension:** `real_estate_quarterly.csv`: real estate "
          "loans by banks (retail, corporate, total), SAR mn, quarterly only "
          "(SAMA does not publish this series monthly).",
          "",
          "**Notes**",
          "- Fed policy is measured by the target range, not the effective "
          "fed funds rate.",
          "- Both SAMA policy rates are kept: the repo rate was unchanged at "
          "2% from 2009 to Feb 2018 while the reverse repo rate moved with "
          "the Fed from Dec 2015.",
          "- SAMA data end in Aug 2026, so the Fed hike of 17 Sep 2026 is "
          "not yet reflected in Saudi series.",
          "- Timing: SAMA policy rates are month-end observations, while "
          "SAIBOR and `fed_mid_avg` are monthly averages. This dataset "
          "therefore supports alignment BY MONTH only, and a SAMA-to-SAIBOR "
          "comparison mixes month-end and average values. Decision-level "
          "timing, and monthly-average SAMA rates, require dated "
          "announcements (built separately in notebook 02).",
          "- SAR-USD spread break: SAMA's own footnote to this table states "
          "that the USD reference rate moved from LIBOR to SOFR as of July "
          "2023, so the spread is not like-for-like across that date. "
          "Source: SAMA Statistical Report, Monetary Indicators: Interest "
          "Rates, footnote (2).",
          "- Oil, Mar 2026: Dubai (~$127) is far above Brent (~$99). The "
          "values match the raw FRED/IMF files, so this is not a parsing "
          "error. Contemporary market reports describe a record Dubai "
          "premium over Brent in March 2026: S&P Global Commodity Insights, "
          "'Platts cash Dubai crosses $100/b mark' (6 Mar 2026), "
          "https://www.spglobal.com/energy/en/news-research/latest-news/"
          "crude-oil/030626-middle-east-crude-benchmark-platts-cash-dubai-"
          "crosses-100b-mark ; QCintel, 'Dubai crude nears $170/b, record "
          "premium over Brent at $55/b', https://www.qcintel.com/article/"
          "dubai-crude-nears-170-b-record-premium-over-brent-at-55-b-61306."
          "html . The cause of the premium is not established by this "
          "dataset. Brent is the main control; results are re-checked with "
          "Dubai."]
(PROCESSED / "data_dictionary.md").write_text("\n".join(lines))
print("Saved data_dictionary.md")


# %% 12. Sanity-check chart: Fed range vs SAMA policy rates ------------------
fig, ax = plt.subplots(figsize=(10, 5))
ax.fill_between(panel.index, panel["fed_lower"], panel["fed_upper"],
                step="post", color="#9db4d6", alpha=0.6,
                label="Fed target range")
ax.step(panel.index, panel["sama_reverse_repo"], where="post",
        color="#1f4e8c", lw=1.8, label="SAMA reverse repo")
ax.step(panel.index, panel["sama_repo"], where="post",
        color="#c0504d", lw=1.8, label="SAMA repo")
ax.plot(panel.index, panel["saibor_3m"], color="#555555", lw=1,
        ls="--", label="3M SAIBOR (monthly avg)")
ax.set_title("Fed target range vs SAMA policy rates and 3M SAIBOR")
ax.set_ylabel("% per year")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(frameon=False, loc="upper left")
fig.tight_layout()
fig.savefig(CHARTS / "01_policy_rates.png", dpi=200)
plt.show()
