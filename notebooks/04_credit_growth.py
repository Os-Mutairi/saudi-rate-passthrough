# -*- coding: utf-8 -*-
"""
04_credit_growth.py
===================
Objective 3: how did private-sector bank credit behave across SAMA rate
cycles, and how are policy-rate changes associated with subsequent monthly
credit growth?

Two parts, kept separate on purpose:
  A. DESCRIPTIVE (the economic story): year-on-year (YoY) credit growth,
     rate-cycle shading, regime averages, lag correlations 0-12.
  B. REGRESSION (fixed before seeing results):

     g_t = a + sum_{j=0..12} b_j * dP_{t-j} + c0*dOil_t + c1*dOil_{t-1}
             + calendar-month dummies + e_t

     g_t   = monthly log credit growth = 100 * [ln(C_t) - ln(C_{t-1})]
             (no overlapping annual windows)
     dP    = monthly change in the SAMA reverse repo (monthly average, pp)
     dOil  = 100 * monthly log change in oil price (Brent main, Dubai
             robustness)

Interpretation: the sum b_0+...+b_k is approximately the % difference in
the credit STOCK after k months associated with a 1pp higher policy rate,
under this model. It is not a change in YoY growth in pp, and it is NOT a
causal effect: credit demand, government spending, Vision 2030 projects
and housing programmes also drive lending and are not controlled for.

Rules carried over from notebook 03: lags fixed in advance and not chosen
from the correlations; one common sample for all variants; Newey-West
bandwidths 12 (baseline), 18 and 24 as sensitivity checks; residual
diagnostics. None of these guarantees valid inference. Thirteen policy
coefficients from a few rate cycles: individual lags are expected to be
imprecise and no terms are added in response to significance.

Outputs
-------
data/processed/credit_regimes.csv, credit_regime_summary.csv
data/processed/credit_lag_correlations.csv
data/processed/credit_results.csv, credit_diagnostics.csv
charts/04_credit_cycles.png, 04_lag_correlations.png, 04_cumulative.png
"""

# %% 0. Setup ---------------------------------------------------------------
import math
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

PROJECT = Path.home() / "saudi-rate-passthrough"
PROCESSED = PROJECT / "data" / "processed"
CHARTS = PROJECT / "charts"

N_LAGS = 12                    # fixed in advance
HORIZONS = [3, 6, 12]          # cumulative sums over lags 0-3, 0-6, 0-12
BANDWIDTHS = [12, 18, 24]      # Newey-West; 12 = baseline

panel = pd.read_csv(PROCESSED / "monthly_panel.csv", index_col="date",
                    parse_dates=True)
avg = pd.read_csv(PROCESSED / "sama_policy_monthly_avg.csv", index_col="date",
                  parse_dates=True)
decisions = pd.read_csv(PROCESSED / "policy_decisions.csv",
                        parse_dates=["sama_date"])
df = panel.join(avg.drop(columns="checked_vs_published"), how="left")

df["g"] = 100 * np.log(df["credit_total"]).diff()     # monthly log growth
df["dP"] = df["sama_reverse_repo_avg"].diff()
df["dP_sameday"] = df["sama_reverse_repo_avg_sameday"].diff()
df["dOil_brent"] = 100 * np.log(df["brent_usd"]).diff()
df["dOil_dubai"] = 100 * np.log(df["dubai_usd"]).diff()
print(f"Panel: {df.index.min():%b %Y} to {df.index.max():%b %Y}")


# %% 1. Rate-cycle regimes, defined mechanically ------------------------------
# Two separate classifications, so that a quiet month inside a hiking cycle
# is not mistaken for a 'stable regime':
#  (a) DECISION-MONTH DIRECTION: the sign of that month's change in SAMA's
#      published month-end reverse repo (hike / cut / no change).
#  (b) MULTI-MONTH CYCLE: a cycle is a maximal run of consecutive SAMA
#      reverse-repo decisions with the same sign. It runs from the month of
#      the first decision to the month of the last one, INCLUDING pauses in
#      between (e.g. the Dec 2015-Dec 2018 hiking cycle contains a 12-month
#      pause in 2016). All other months are 'between cycles'.
# Cycle boundaries use ASSUMED EFFECTIVE DATES (announcement + 1 day, the
# working convention from notebook 02), so both classifications count a
# late-evening decision in the same month. The original announcement dates
# stay in policy_decisions.csv as the source record.
# Caveats for the README:
#  - These are RETROSPECTIVE classifications: knowing which decision was the
#    last in a run uses later history, so they are not real-time signals.
#  - 'Between cycles' means outside the first-to-last-decision spans, NOT
#    necessarily neutral policy: it includes long periods of very low rates
#    (2009-15, 2020-22) and of high rates (Aug 2023 - Aug 2024).
d = decisions.dropna(subset=["sama_date"]).sort_values("sama_date")
d = d[d["rrr_change_bp"] != 0][["sama_date", "rrr_change_bp"]]
d["sign"] = np.sign(d["rrr_change_bp"])
d["run"] = (d["sign"] != d["sign"].shift()).cumsum()
d["cycle_date"] = d["sama_date"] + pd.Timedelta(days=1)   # assumed effective
cycles = d.groupby("run").agg(start=("cycle_date", "min"),
                              end=("cycle_date", "max"),
                              sign=("sign", "first"),
                              n_decisions=("sign", "size"))
cycles["type"] = np.where(cycles["sign"] > 0, "hiking cycle",
                          "easing cycle")
print("Cycles (assumed effective dates):")
print(cycles[["type", "start", "end", "n_decisions"]].to_string(index=False))

df["cycle"] = "between cycles"
for _, c in cycles.iterrows():
    in_c = ((df.index >= c["start"].to_period("M").to_timestamp())
            & (df.index <= c["end"].to_period("M").to_timestamp()))
    df.loc[in_c, "cycle"] = c["type"]

chg = df["sama_reverse_repo"].diff()
df["decision_month"] = np.select([chg > 0, chg < 0], ["hike", "cut"],
                                 "no change")
df.loc[df.index[0], "decision_month"] = np.nan   # no prior month to compare
print(df["cycle"].value_counts().to_string())
df[["cycle", "decision_month", "credit_total_yoy", "g"]].to_csv(
    PROCESSED / "credit_regimes.csv")


# %% 2. Regime averages of YoY credit growth ----------------------------------
summary = []
for col in ["cycle", "decision_month"]:
    s = (df.groupby(col)["credit_total_yoy"]
         .agg(months="count", mean_yoy="mean", median_yoy="median",
              min_yoy="min", max_yoy="max").reset_index()
         .rename(columns={col: "group"}))
    s.insert(0, "classification", col)
    summary.append(s)
summary = pd.concat(summary, ignore_index=True)
summary.to_csv(PROCESSED / "credit_regime_summary.csv", index=False)
print(summary.round(1).to_string(index=False))
print("Note: averages describe what happened in each period; they do not "
      "separate rates from oil, fiscal policy or credit demand.")


# %% 3. Chart: YoY credit growth across rate cycles --------------------------
fig, ax = plt.subplots(figsize=(11, 5))
shade = {"hiking cycle": "#f2c4c3", "easing cycle": "#c9dbef"}
for _, c in cycles.iterrows():
    if c["start"] > df.index.max():
        continue
    ax.axvspan(c["start"].to_period("M").to_timestamp(),
               min(c["end"].to_period("M").to_timestamp()
                   + pd.offsets.MonthEnd(1), df.index.max()),
               color=shade[c["type"]], alpha=0.6, lw=0)
ax.plot(df.index, df["credit_total_yoy"], color="#1f4e8c", lw=1.8,
        label="Private-sector bank credit, YoY growth (%)")
ax2 = ax.twinx()
ax2.step(df.index, df["sama_reverse_repo"], where="post", color="#555555",
         lw=1.2, ls="--", label="SAMA reverse repo (%, right axis)")
ax.set_ylabel("YoY credit growth, %")
ax2.set_ylabel("reverse repo, %")
ax.set_title("Private credit growth across SAMA rate cycles\n(red = hiking "
             "cycle, blue = easing cycle; retrospective, from assumed "
             "effective dates of SAMA decisions)", fontsize=11)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc="lower right",
          bbox_to_anchor=(0.97, 0.02), fontsize=8)
for a in (ax, ax2):
    a.spines[["top"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "04_credit_cycles.png", dpi=200)
plt.show()


# %% 4. Seasonality check and lag correlations (descriptive only) -----------
# SAMA's credit series is not stated to be seasonally adjusted, so the
# regression includes calendar-month dummies. Quick look at the pattern:
print("Mean monthly log credit growth by calendar month (%):")
print(df["g"].groupby(df.index.month).mean().round(2).to_string())

# Correlation of monthly credit growth with policy changes k months
# earlier. Descriptive only: neighbouring policy changes are themselves
# correlated, and these peaks are NOT used to choose regression lags.
lag_corr = pd.DataFrame({
    "lag_months": range(N_LAGS + 1),
    "corr_g_with_dP": [df["g"].corr(df["dP"].shift(k))
                       for k in range(N_LAGS + 1)],
})
lag_corr.to_csv(PROCESSED / "credit_lag_correlations.csv", index=False)
print(lag_corr.round(3).to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 3.8))
ax.bar(lag_corr["lag_months"], lag_corr["corr_g_with_dP"], color="#9db4d6")
ax.axhline(0, color="#999999", lw=0.8)
ax.set_xticks(range(N_LAGS + 1))
ax.set_xlabel("policy change k months earlier")
ax.set_ylabel("correlation")
ax.set_title("Monthly credit growth vs earlier reverse-repo changes "
             "(descriptive; not used to select lags)", fontsize=10)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "04_lag_correlations.png", dpi=200)
plt.show()


# %% 5. Statistical tools (same numpy code as notebook 03) ------------------
def normal_p(z):
    return math.erfc(abs(z) / math.sqrt(2))


def chi2_sf(x, k):
    a, x = k / 2.0, x / 2.0
    if x <= 0:
        return 1.0
    if x < a + 1:
        term, total, n = 1.0 / a, 1.0 / a, 0
        while abs(term) > 1e-12 * abs(total):
            n += 1
            term *= x / (a + n)
            total += term
        return 1 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b, c, dd = x + 1 - a, 1e300, 1 / (x + 1 - a)
    h = dd
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        dd = an * dd + b
        dd = 1 / dd if dd != 0 else 1e300
        c = b + an / c
        delta = c * dd
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def ols_hac(y, X, hac_lags):
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    u = X * resid[:, None]
    S = u.T @ u
    for lag in range(1, hac_lags + 1):
        w = 1 - lag / (hac_lags + 1)
        G = u[lag:].T @ u[:-lag]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    return beta, cov, resid, 1 - resid.var() / y.var()


def wald(beta, cov, idx):
    b = beta[idx]
    W = float(b @ np.linalg.solve(cov[np.ix_(idx, idx)], b))
    return W, chi2_sf(W, len(idx))


def breusch_godfrey(resid, X, lags):
    n = len(resid)
    R = np.column_stack([np.r_[np.zeros(k), resid[:-k]]
                         for k in range(1, lags + 1)])
    Z = np.column_stack([X, R])
    e = resid - Z @ np.linalg.lstsq(Z, resid, rcond=None)[0]
    lm = n * (1 - e.var() / resid.var())
    return lm, chi2_sf(lm, lags)


# %% 6. Regression data on ONE common sample ---------------------------------
VARIANTS = {
    "Next-day timing, Brent (MAIN)": ("dP", "dOil_brent"),
    "Same-day timing, Brent": ("dP_sameday", "dOil_brent"),
    "Next-day timing, Dubai": ("dP", "dOil_dubai"),
}
reg = pd.DataFrame({"g": df["g"]})
for pcol in ["dP", "dP_sameday"]:
    for k in range(N_LAGS + 1):
        reg[f"{pcol}_L{k}"] = df[pcol].shift(k)
for ocol in ["dOil_brent", "dOil_dubai"]:
    reg[f"{ocol}_L0"] = df[ocol]
    reg[f"{ocol}_L1"] = df[ocol].shift(1)
months = pd.get_dummies(df.index.month, prefix="m", drop_first=True,
                        dtype=float)
months.index = df.index
reg = reg.join(months).dropna()
MONTH_COLS = list(months.columns)
print(f"Common estimation sample: {reg.index.min():%b %Y} to "
      f"{reg.index.max():%b %Y}, N = {len(reg)} months")
print(f"Regressors: constant + {N_LAGS + 1} policy lags + 2 oil terms + "
      f"{len(MONTH_COLS)} month dummies = {1 + N_LAGS + 1 + 2 + 11}")


def estimate(pcol, ocol, bw):
    pol = [f"{pcol}_L{k}" for k in range(N_LAGS + 1)]
    oil = [f"{ocol}_L0", f"{ocol}_L1"]
    X = np.column_stack([np.ones(len(reg)), reg[pol + oil + MONTH_COLS]])
    beta, cov, resid, r2 = ols_hac(reg["g"].values, X, bw)
    out = {"beta": beta, "cov": cov, "resid": resid, "r2": r2, "X": X,
           "pol_idx": list(range(1, N_LAGS + 2)),
           "oil_idx": [N_LAGS + 2, N_LAGS + 3]}
    for h in HORIZONS:
        w = np.zeros(len(beta))
        w[1:h + 2] = 1      # lags 0..h
        out[f"sum_0_{h}"] = (w @ beta, math.sqrt(w @ cov @ w))
    return out


# %% 7. Estimate all variants and bandwidths ----------------------------------
rows, diag = [], []
for label, (pcol, ocol) in VARIANTS.items():
    for bw in BANDWIDTHS:
        f = estimate(pcol, ocol, bw)
        for h in HORIZONS:
            est, se = f[f"sum_0_{h}"]
            rows.append({"variant": label, "hac_bandwidth": bw,
                         "horizon": f"sum lags 0-{h}",
                         "n_coefficients": h + 1, "estimate": est,
                         "se": se, "ci_low": est - 1.96 * se,
                         "ci_high": est + 1.96 * se,
                         "p_value": fmt_p(normal_p(est / se))})
        if bw == BANDWIDTHS[0]:
            Wp, pWp = wald(f["beta"], f["cov"], f["pol_idx"])
            Wo, pWo = wald(f["beta"], f["cov"], f["oil_idx"])
            diag.append({
                "variant": label, "N": len(reg), "R2": round(f["r2"], 3),
                "all_13_policy_lags_zero_p": fmt_p(pWp),
                "oil_terms_zero_p": fmt_p(pWo),
                "resid_lag1_corr": round(np.corrcoef(
                    f["resid"][1:], f["resid"][:-1])[0, 1], 3),
                "BreuschGodfrey12_p": fmt_p(breusch_godfrey(
                    f["resid"], f["X"], 12)[1]),
                "BreuschGodfrey24_p": fmt_p(breusch_godfrey(
                    f["resid"], f["X"], 24)[1])})
results = pd.DataFrame(rows)
diagnostics = pd.DataFrame(diag)
results.to_csv(PROCESSED / "credit_results.csv", index=False)
diagnostics.to_csv(PROCESSED / "credit_diagnostics.csv", index=False)

pd.set_option("display.width", 160)
print("Cumulative association: approx. % difference in the credit stock "
      "after k months\nper 1pp higher reverse repo (model-based, not "
      "causal):")
print(results.round(3).to_string(index=False))
print("\nDiagnostics (baseline bandwidth 12; joint tests use HAC):")
print(diagnostics.to_string(index=False))


# %% 8. Individual policy-lag coefficients, main variant (for reference) ---
f = estimate("dP", "dOil_brent", BANDWIDTHS[0])
se = np.sqrt(np.diag(f["cov"]))
ind = pd.DataFrame({
    "lag": range(N_LAGS + 1),
    "coef": f["beta"][f["pol_idx"]],
    "hac_se": se[f["pol_idx"]],
})
ind["p"] = [fmt_p(normal_p(b / s)) for b, s in zip(ind["coef"],
                                                     ind["hac_se"])]
print("Main variant, individual policy lags (expected to be imprecise):")
print(ind.round(3).to_string(index=False))


# %% 9. Chart: cumulative associations by horizon ----------------------------
fig, ax = plt.subplots(figsize=(9, 4.5))
colors = {"Next-day timing, Brent (MAIN)": "#1f4e8c",
          "Same-day timing, Brent": "#9db4d6",
          "Next-day timing, Dubai": "#c0504d"}
base = results[results["hac_bandwidth"] == BANDWIDTHS[0]]
for i, (label, color) in enumerate(colors.items()):
    r = base[base["variant"] == label]
    x = np.arange(len(HORIZONS)) + (i - 1) * 0.2
    ax.errorbar(x, r["estimate"], yerr=[r["estimate"] - r["ci_low"],
                                         r["ci_high"] - r["estimate"]],
                fmt="o", color=color, capsize=3, label=label)
ax.axhline(0, color="#999999", lw=0.8)
ax.set_xticks(range(len(HORIZONS)))
ax.set_xticklabels([f"after {h} months\n(lags 0-{h})" for h in HORIZONS])
ax.set_ylabel("approx. % difference in credit stock\nper 1pp higher "
              "reverse repo")
ax.set_title("Cumulative association of policy-rate changes with private "
             "credit\n(95% CIs, Newey-West bandwidth 12; model-based, not "
             "causal)", fontsize=10)
ax.legend(frameon=False, fontsize=8)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "04_cumulative.png", dpi=200)
plt.show()
