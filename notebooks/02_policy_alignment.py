# -*- coding: utf-8 -*-
"""
02_policy_alignment.py
======================
Objective 1: how closely do SAMA's policy rates track the Fed, and when
do they differ?

Two levels of evidence, kept separate on purpose:
  A. DECISION level - a dated table of every Fed and SAMA rate decision
     since 2009, built from official announcements (SAMA, Federal Reserve)
     and, where needed, Argaam/press reports. Each row records its source.
  B. MONTHLY level - month-by-month changes in the SAMA rates and the Fed
     target, from the monthly panel built in notebook 01.

Outputs
-------
data/processed/policy_decisions.csv     <- dated decision table + sources
data/processed/sama_policy_daily.csv    <- daily SAMA rates rebuilt from it
data/processed/sama_policy_monthly_avg.csv
data/processed/monthly_changes.csv
charts/02_rrr_minus_fed_upper.png
charts/02_decision_comparison.png

Run in Spyder cell by cell (Shift + Enter) or all at once (F5).
Notebook 01 must have been run first.
"""

# %% 0. Setup ---------------------------------------------------------------
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

PROJECT = Path.home() / "saudi-rate-passthrough"
# Last day covered by the downloads (FRED files end 19 Oct 2026). Nothing
# is extrapolated beyond this date.
DATA_CUTOFF = pd.Timestamp("2026-10-19")
RAW = PROJECT / "data" / "raw"
PROCESSED = PROJECT / "data" / "processed"
CHARTS = PROJECT / "charts"

panel = pd.read_csv(PROCESSED / "monthly_panel.csv", index_col="date",
                    parse_dates=True)
print(f"Panel loaded: {panel.index.min():%b %Y} to {panel.index.max():%b %Y}")


# %% 1. Fed decisions -------------------------------------------------------
# Announcement dates are the FOMC statement dates (Federal Reserve press
# releases). FRED records the date the new range takes EFFECT, which is
# usually the next day, so we keep both. The new upper limit is checked
# against FRED below rather than typed in by hand.
FED_ANNOUNCED = [
    "2015-12-16", "2016-12-14", "2017-03-15", "2017-06-14", "2017-12-13",
    "2018-03-21", "2018-06-13", "2018-09-26", "2018-12-19",
    "2019-07-31", "2019-09-18", "2019-10-30",
    "2020-03-03", "2020-03-15",          # two emergency (unscheduled) cuts
    "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21",
    "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-07-26",
    "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-09-16",
]

fed_upper_daily = pd.read_csv(RAW / "DFEDTARU.csv", parse_dates=[0],
                              index_col=0)["DFEDTARU"]
fed_changes = fed_upper_daily.diff()
fed_changes = fed_changes[fed_changes != 0].dropna()

fed = pd.DataFrame({
    "fed_announced": pd.to_datetime(FED_ANNOUNCED),
    "fed_effective": fed_changes.index,
    "fed_change_bp": (fed_changes.values * 100).round().astype(int),
    "fed_upper_new": fed_upper_daily[fed_changes.index].values,
})
# Check: every effective date is 0-1 days after its announcement
lag = (fed["fed_effective"] - fed["fed_announced"]).dt.days
assert lag.between(0, 1).all(), "Fed announcement/effective dates misaligned"
print(f"{len(fed)} Fed rate CHANGES since 2009 (meetings that left rates "
      "unchanged are not included); all match FRED.")

# One timezone convention throughout: dates are RIYADH local dates (UTC+3).
# Scheduled Fed statements come at 2pm Washington time = 9-10pm Riyadh, the
# same calendar day. The one exception is the emergency cut announced on
# Sunday 15 Mar 2020 at 5pm Washington time (EDT, UTC-4) = 00:00 on Monday
# 16 Mar in Riyadh.
fed["fed_announced_riyadh"] = fed["fed_announced"].where(
    fed["fed_announced"] != "2020-03-15", pd.Timestamp("2020-03-16"))


# %% 2. SAMA decisions (hand-collected, each with its source) ---------------
# rr = repo rate, rrr = reverse repo rate, both the NEW level in %.
# verified: 'page' = date and decision read from the source page itself;
#           'listing' = date taken from the source's URL/listing date only.
S = "https://www.sama.gov.sa/en-US/MediaCenter/News/Pages/"
A = "https://www.argaam.com/en/article/articledetail/id/"
sama = pd.DataFrame([
    # date, rr, rrr, source, verified, note
    ("2009-01-19", 2.00, 0.75, "https://dawn.com/news/339411", "page",
     "Not linked to a Fed move"),
    ("2009-04-14", 2.00, 0.50,
     "https://currencythoughts.com/2009/04/14/monetary-policy-eased-in-"
     "saudi-arabia/", "page", "Not linked to a Fed move"),
    ("2009-06-16", 2.00, 0.25, S + "ReverseRepoRate_16_6_2009.aspx",
     "listing", "Not linked to a Fed move"),
    ("2015-12-16", 2.00, 0.50, S + "News16122015.aspx", "page", ""),
    ("2016-12-14", 2.00, 0.75, S + "news14122016.aspx", "listing", ""),
    ("2017-03-15", 2.00, 1.00, S + "news15032017.aspx", "listing", ""),
    ("2017-06-14", 2.00, 1.25, S + "news140062017.aspx", "page", ""),
    ("2017-12-14", 2.00, 1.50, A + "519420", "page",
     "Secondary source; dated the morning after the Fed (Riyadh time)"),
    ("2018-03-15", 2.25, 1.75, S + "news0015032018.aspx", "page",
     "SAMA moved 6 days BEFORE the Fed"),
    ("2018-06-13", 2.50, 2.00, S + "news13062018.aspx", "listing", ""),
    ("2018-09-26", 2.75, 2.25, S + "news026102018.aspx", "page", ""),
    ("2018-12-19", 3.00, 2.50, S + "news19122018.aspx", "listing", ""),
    ("2019-07-31", 2.75, 2.25, S + "news31072019.aspx", "listing", ""),
    ("2019-09-18", 2.50, 2.00, S + "news-18092019.aspx", "listing", ""),
    ("2019-10-30", 2.25, 1.75, S + "News30102019.aspx", "listing", ""),
    ("2020-03-03", 1.75, 1.25, A + "1353454", "listing", ""),
    ("2020-03-16", 1.00, 0.50, S + "news-518.aspx", "page",
     "Fed cut 100bp (Sunday 15 Mar, US time); SAMA cut 75bp"),
    ("2022-03-16", 1.25, 0.75, A + "1543878", "listing", ""),
    ("2022-05-04", 1.75, 1.25, A + "1556999", "listing", ""),
    ("2022-06-15", 2.25, 1.75, A + "1568040", "listing",
     "Fed +75bp, SAMA +50bp"),
    ("2022-07-27", 3.00, 2.50, S + "news-768.aspx", "page",
     "SAMA release timestamped 10:00 PM"),
    ("2022-09-21", 3.75, 3.25, S + "news-781.aspx", "page",
     "SAMA release timestamped 10:15 PM"),
    ("2022-11-02", 4.50, 4.00, S + "news-795.aspx", "page",
     "SAMA release timestamped 9:45 PM"),
    ("2022-12-14", 5.00, 4.50, A + "1609202", "page", ""),
    ("2023-02-01", 5.25, 4.75, A + "1618827", "page", ""),
    ("2023-03-22", 5.50, 5.00, A + "1630943", "page", ""),
    ("2023-05-03", 5.75, 5.25, A + "1640427", "page", ""),
    ("2023-07-26", 6.00, 5.50, A + "1659395", "listing", ""),
    ("2024-09-18", 5.50, 5.00, A + "1755520", "page", ""),
    ("2024-11-07", 5.25, 4.75, A + "1767490", "listing", ""),
    ("2024-12-18", 5.00, 4.50, A + "1776945", "page", ""),
    ("2025-09-17", 4.75, 4.25, A + "1843919", "page", ""),
    ("2025-10-29", 4.50, 4.00, A + "1854079", "page", ""),
    ("2025-12-10", 4.25, 3.75, A + "1865280", "page", ""),
    ("2026-09-16", 4.50, 4.00, "https://www.spa.gov.sa/en/N2678377", "page",
     "After the end of SAMA's monthly data (Aug 2026)"),
], columns=["sama_date", "rr_new", "rrr_new", "source", "verified", "note"])
sama["sama_date"] = pd.to_datetime(sama["sama_date"])
# Where the only dated source is a news article, its publication date may
# differ from the decision date. Dec 2017 is the one such case that matters.
sama["date_status"] = "as stated by source"
sama.loc[sama["sama_date"] == "2017-12-14", "date_status"] = (
    "UNCERTAIN: news publication date; decision may have been 13 Dec")

# Levels in force on 1 Jan 2009 (set on 16 Dec 2008, Arab News, 17 Dec 2008)
START_RR, START_RRR = 2.50, 1.50

sama["rr_change_bp"] = (sama["rr_new"].diff().fillna(
    sama["rr_new"].iloc[0] - START_RR) * 100).round().astype(int)
sama["rrr_change_bp"] = (sama["rrr_new"].diff().fillna(
    sama["rrr_new"].iloc[0] - START_RRR) * 100).round().astype(int)
print(sama[["sama_date", "rr_new", "rrr_new", "rr_change_bp",
            "rrr_change_bp", "verified"]].to_string(index=False))


# %% 3. Check the hand-collected table against SAMA's own monthly data ------
# Rebuild a DAILY series from the decisions and compare each month-end value
# with SAMA's published month-end rates.
# What this check DOES confirm: the rate LEVELS and the MONTH of each change.
# What it does NOT confirm: the exact day. A decision moved by a few days
# within the same month would leave the month-end rate unchanged. Exact
# dates rest on the sources listed in the table.
days = pd.date_range("2009-01-01", DATA_CUTOFF, freq="D")


def rebuild(effective_lag_days):
    """Daily SAMA rates if each decision takes effect N days after the
    announcement date."""
    out = pd.DataFrame(index=days, columns=["sama_repo", "sama_reverse_repo"],
                       dtype=float)
    out.iloc[0] = [START_RR, START_RRR]
    for _, r in sama.iterrows():
        eff = r["sama_date"] + pd.Timedelta(days=effective_lag_days)
        if eff <= DATA_CUTOFF:
            out.loc[eff, :] = [r["rr_new"], r["rrr_new"]]
    out = out.ffill()
    out.index.name = "date"
    return out


published = panel[["sama_repo", "sama_reverse_repo"]]


def mismatches(daily_df):
    month_end = daily_df.resample("MS").last().loc[published.index]
    bad = ((month_end - published).abs() > 1e-9).any(axis=1)
    return list(bad[bad].index.strftime("%b %Y"))


# Sensitivity: which effective-date convention fits SAMA's month-end data?
for lag_d in (0, 1, 2):
    m = mismatches(rebuild(lag_d))
    print(f"Effective {lag_d} day(s) after announcement: "
          f"{len(m)} mismatching months {m}")

# Next-day effectiveness is the only convention with zero mismatches, so it
# is our working convention. It is supported directly only by the Jul 2019
# boundary case; for other decisions it remains a PROVISIONAL convention
# (official effective dates were not available).
daily = rebuild(1)
assert not mismatches(daily), "Rebuilt month-end rates differ from SAMA data"
print("Rebuilt month-end LEVELS match SAMA's published data in all",
      len(published), "months. Exact daily dates are not tested by this.")
daily.to_csv(PROCESSED / "sama_policy_daily.csv")

# Monthly AVERAGE SAMA rates (comparable with monthly-average SAIBOR and
# fed_mid_avg). Two versions, so notebook 03 can test whether the timing
# convention matters for the regressions.
avg_next_day = daily.resample("MS").mean().add_suffix("_avg")
avg_same_day = rebuild(0).resample("MS").mean().add_suffix("_avg_sameday")
sama_avg = pd.concat([avg_next_day, avg_same_day], axis=1)

# Keep complete months only: Oct 2026 is cut off at the download date.
last_complete = (DATA_CUTOFF + pd.Timedelta(days=1)).to_period("M")
sama_avg = sama_avg[sama_avg.index.to_period("M") < last_complete]
# Months after SAMA's last published month (Aug 2026) cannot be cross-checked
sama_avg["checked_vs_published"] = sama_avg.index <= published.index.max()
sama_avg.to_csv(PROCESSED / "sama_policy_monthly_avg.csv")

d = (sama_avg["sama_reverse_repo_avg"]
     - sama_avg["sama_reverse_repo_avg_sameday"]).abs()
print(f"Next-day vs same-day convention: monthly averages differ in "
      f"{(d > 1e-9).sum()} of {len(d)} months; largest difference "
      f"{d.max() * 100:.1f} bp")


# %% 4. Match each Fed decision with the SAMA response ----------------------
# Matching rule: a SAMA move is paired with a Fed rate change if it falls
# within a +/-7 calendar-day window (before OR after) of the Fed's
# announcement, using Riyadh local dates for both. A negative lag means SAMA
# moved FIRST. SAMA releases are timestamped around 9:45-10:15pm Riyadh,
# shortly after the Fed's statement, so lag 0 means a near-immediate move.
rows = []
used = set()
for _, f in fed.iterrows():
    window = sama[(sama["sama_date"]
                   - f["fed_announced_riyadh"]).dt.days.abs() <= 7]
    window = window[~window.index.isin(used)]
    if len(window):
        s = window.iloc[0]
        used.add(window.index[0])
        rows.append({**f, "sama_date": s["sama_date"],
                     "lag_days": (s["sama_date"]
                                  - f["fed_announced_riyadh"]).days,
                     "date_status": s["date_status"],
                     "rrr_change_bp": s["rrr_change_bp"],
                     "rr_change_bp": s["rr_change_bp"],
                     "source": s["source"], "verified": s["verified"],
                     "note": s["note"]})
    else:
        rows.append({**f, "sama_date": pd.NaT, "lag_days": None,
                     "rrr_change_bp": 0, "rr_change_bp": 0,
                     "source": "", "verified": "",
                     "note": "No SAMA move within +/-7 days"})

decisions = pd.DataFrame(rows)
# Add SAMA moves that do not correspond to any Fed decision
extra = sama[~sama.index.isin(used)]
for _, s in extra.iterrows():
    decisions = pd.concat([decisions, pd.DataFrame([{
        "sama_date": s["sama_date"], "rrr_change_bp": s["rrr_change_bp"],
        "rr_change_bp": s["rr_change_bp"], "source": s["source"],
        "verified": s["verified"], "note": s["note"],
        "date_status": s["date_status"], "fed_change_bp": 0}])],
        ignore_index=True)

decisions["event_date"] = decisions["fed_announced_riyadh"].fillna(
    decisions["sama_date"])
decisions = decisions.sort_values("event_date").reset_index(drop=True)


def classify(r):
    if pd.isna(r["fed_announced"]):
        return "SAMA only"
    if pd.isna(r["sama_date"]):
        return "Fed only"
    if r["rrr_change_bp"] == r["fed_change_bp"]:
        return "Matched (same size)"
    return "Matched (different size)"


decisions["match"] = decisions.apply(classify, axis=1)
decisions.to_csv(PROCESSED / "policy_decisions.csv", index=False)

cols = ["event_date", "fed_change_bp", "sama_date", "lag_days",
        "rrr_change_bp", "rr_change_bp", "match"]
print(decisions[cols].to_string(index=False))
print()
print(decisions["match"].value_counts().to_string())


# %% 5. Summary statistics ---------------------------------------------------
both = decisions.dropna(subset=["fed_announced", "sama_date"])
n_fed = decisions["fed_announced"].notna().sum()
print(f"Fed rate changes since 2009: {n_fed}")
print(f"  with a SAMA move in the +/-7-day window: {len(both)}")
print(f"  of which SAMA moved BEFORE the Fed:      {(both['lag_days'] < 0).sum()}")
print(f"  same-size reverse-repo move:             "
      f"{(both['rrr_change_bp'] == both['fed_change_bp']).sum()}")
print(f"  lag in days (Riyadh dates):              "
      f"{both['lag_days'].value_counts().sort_index().to_dict()}")
print(f"  ...of which date flagged UNCERTAIN:      "
      f"{both['date_status'].str.startswith('UNCERTAIN').sum()}")
print(f"SAMA moves with no Fed change in the window: "
      f"{(decisions['match'] == 'SAMA only').sum()}")
print(f"Sources: {(sama['verified'] == 'page').sum()} read from the source "
      f"page, {(sama['verified'] == 'listing').sum()} from URL/listing date")


# %% 6. Gap between SAMA reverse repo and the Fed upper limit (daily) -------
# Both series use ANNOUNCEMENT dates in Riyadh local time (same convention as
# the matching table). Effective-date conventions differ between FRED and
# our SAMA rebuild and would create artificial one-day gaps. So day counts
# below describe announcement-to-announcement spells, not verified
# effective-date durations.
def step_series(dates, values, start_value):
    s = pd.Series(float("nan"), index=days)
    s.iloc[0] = start_value
    for d, v in zip(dates, values):
        s.loc[d] = v
    return s.ffill()


gap = pd.DataFrame({
    "rrr": step_series(sama["sama_date"], sama["rrr_new"], START_RRR),
    "fed_upper": step_series(fed["fed_announced_riyadh"],
                             fed["fed_upper_new"], 0.25),
})
gap["gap_bp"] = ((gap["rrr"] - gap["fed_upper"]) * 100).round()
gap = gap.loc[:DATA_CUTOFF]

nonzero = gap["gap_bp"] != 0
spells = (nonzero != nonzero.shift()).cumsum()
print("Periods where SAMA reverse repo != Fed upper limit "
      "(announcement dates):")
for _, g in gap[nonzero].groupby(spells[nonzero]):
    vals = " -> ".join(f"{v:+.0f}" for v in g["gap_bp"].unique())
    flag = ("  <- UNCERTAIN (news publication date)"
            if g.index[0] == pd.Timestamp("2017-12-13") else "")
    print(f"  {g.index[0]:%d %b %Y} to {g.index[-1]:%d %b %Y}"
          f" ({len(g)} days): {vals} bp{flag}")
since_2015 = gap.loc["2015-12-16":, "gap_bp"]
print(f"Share of days with zero gap since the Fed's first hike (Dec 2015): "
      f"{(since_2015 == 0).mean():.1%}")


# %% 7. Chart: reverse repo minus Fed upper limit ---------------------------
# Plotted from 2015, when the Fed started moving again. (In Jan-Jun 2009 the
# gap was +125bp falling to 0 as SAMA cut on its own; see the printout above.)
g = gap.loc["2015-01-01":]
fig, ax = plt.subplots(figsize=(10, 4))
ax.fill_between(g.index, 0, g["gap_bp"], step="post", color="#1f4e8c",
                alpha=0.85)
ax.axhline(0, color="#999999", lw=0.8)
ax.set_title("SAMA reverse repo rate minus Fed target upper limit "
             "(announcement dates, Riyadh time)")
ax.set_ylabel("basis points")
ax.annotate("15-21 Mar 2018: SAMA hikes\n6 days before the Fed",
            xy=(pd.Timestamp("2018-03-18"), 25),
            xytext=(pd.Timestamp("2015-06-01"), 34),
            fontsize=8, arrowprops=dict(arrowstyle="-", color="#555555"))
ax.annotate("Mar 2020: Fed cuts 100bp, SAMA 75bp.\n"
            "Gap closes Jun 2022 (Fed +75bp, SAMA +50bp)",
            xy=(pd.Timestamp("2021-03-01"), 25),
            xytext=(pd.Timestamp("2022-09-01"), 34),
            fontsize=8, arrowprops=dict(arrowstyle="-", color="#555555"))
ax.annotate("13 Dec 2017: -25bp for 1 day.\nUNCERTAIN: SAMA date from a\n"
            "news article's publication date",
            xy=(pd.Timestamp("2017-12-13"), -25),
            xytext=(pd.Timestamp("2018-10-01"), -24), fontsize=8,
            color="#c0504d",
            arrowprops=dict(arrowstyle="-", color="#c0504d"))
ax.set_ylim(-32, 45)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "02_rrr_minus_fed_upper.png", dpi=200)
plt.show()


# %% 8. Chart: size of each Fed move vs SAMA reverse repo move --------------
d = decisions.dropna(subset=["fed_announced"])
x = range(len(d))
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.bar([i - 0.2 for i in x], d["fed_change_bp"], width=0.4,
       color="#9db4d6", label="Fed (target range)")
ax.bar([i + 0.2 for i in x], d["rrr_change_bp"], width=0.4,
       color="#1f4e8c", label="SAMA reverse repo")
ax.axhline(0, color="#999999", lw=0.8)
ax.set_xticks(list(x))
ax.set_xticklabels(d["fed_announced_riyadh"].dt.strftime("%d %b %y"),
                   rotation=90,
                   fontsize=7)
ax.set_ylabel("change, basis points")
ax.set_title("Each Fed rate change since 2015 and SAMA's reverse repo move "
             "(+/-7-day window)")
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "02_decision_comparison.png", dpi=200)
plt.show()


# %% 9. Monthly-level comparison (from SAMA's published monthly data) -------
m = panel[["fed_upper", "sama_repo", "sama_reverse_repo"]].diff() * 100
m.columns = ["fed_upper_chg_bp", "repo_chg_bp", "rrr_chg_bp"]
m = m.dropna().round()
moved = m[(m != 0).any(axis=1)].copy()


def month_label(r):
    if r["fed_upper_chg_bp"] == 0:
        return "SAMA moved, Fed did not"
    if r["rrr_chg_bp"] == 0:
        return "Fed moved, SAMA reverse repo did not"
    if r["rrr_chg_bp"] == r["fed_upper_chg_bp"]:
        return "Both moved, same size"
    return "Both moved, different size"


moved["pattern"] = moved.apply(month_label, axis=1)
moved.to_csv(PROCESSED / "monthly_changes.csv")
print(moved.to_string())
print()
print(moved["pattern"].value_counts().to_string())
