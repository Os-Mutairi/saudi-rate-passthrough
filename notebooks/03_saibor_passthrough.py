# -*- coding: utf-8 -*-
"""
03_saibor_passthrough.py
========================
Objective 2: how are changes in SAMA's policy rate associated with changes
in 3-month SAIBOR, in the same month and the following months?

Baseline specification (monthly, changes in percentage points):

    dSAIBOR_t = a + b0*dP_t + b1*dP_{t-1} + b2*dP_{t-2} + b3*dP_{t-3} + e_t

where P is the SAMA reverse repo rate (monthly average). We report each b,
their SUM (with a 95% confidence interval) and residual diagnostics.

Design rules (agreed in review):
- Main policy measure: reverse repo. Repo = separate robustness model
  (never both in one regression: they move almost together).
- Both timing conventions for SAMA's monthly averages are estimated
  (next-day effective = main, same-day = alternative).
- Every model uses EXACTLY the same months, so differences come from the
  specification or timing convention, not from a different sample.
- Newey-West (HAC) standard errors. They allow for some forms of serial
  correlation and heteroskedasticity, under assumptions; they do not
  guarantee reliable intervals and do not fix omitted dynamics. Bandwidth
  sensitivity (4, 6, 12 months) is reported, not chosen by results.
- Model A (baseline): no lagged SAIBOR. Model B (extension): adds ONE lagged
  SAIBOR change. In model B the sum of policy coefficients is NOT the full
  cumulative response; the implied multiplier is sum(b) / (1 - phi), with a
  delta-method interval that includes the covariance of sum(b) and phi.
  Both are model-based associations, not identified causal effects.
- Model B is EXPLORATORY: with a lagged dependent variable, any remaining
  serial correlation can make that regressor correlated with the error,
  which can bias the coefficients themselves (not only the standard
  errors). HAC cannot fix this. Model B's policy coefficients are also
  CONDITIONAL coefficients, not the month-by-month response (e.g. the
  next-month response is b1 + phi*b0).
- Stability check (section 8): fixed split, before Jan 2020 vs Jan 2020
  onwards, chosen before looking at results (COVID cuts, then the 2022-23
  hiking cycle). Differences are tested with a pooled interaction model,
  not by comparing significance across separate regressions.
- Wording: the lag coefficients show how the ASSOCIATION is distributed
  across the current and following months. SAIBOR is a 3-month market rate
  and can move BEFORE policy changes, in anticipation, so this is not a
  measure of "how long SAIBOR takes to adjust".

Statistics are written out in numpy (no statsmodels needed), so every step
is visible. Results were cross-checked against statsmodels during building.

Outputs
-------
data/processed/passthrough_results.csv
data/processed/passthrough_diagnostics.csv
data/processed/passthrough_bandwidth.csv
charts/03_saibor_vs_policy.png
charts/03_lag_coefficients.png
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

N_LAGS = 3   # current month + 3 lags, as agreed. Not tuned to the data.

panel = pd.read_csv(PROCESSED / "monthly_panel.csv", index_col="date",
                    parse_dates=True)
avg = pd.read_csv(PROCESSED / "sama_policy_monthly_avg.csv", index_col="date",
                  parse_dates=True)

# Join by month. Common sample = the panel's months (Jan 2009 - Jul 2026).
df = panel.join(avg.drop(columns="checked_vs_published"), how="left")
assert df[["sama_reverse_repo_avg", "sama_reverse_repo_avg_sameday",
           "sama_repo_avg", "saibor_3m"]].notna().all().all()
print(f"Joined sample: {df.index.min():%b %Y} to {df.index.max():%b %Y} "
      f"({len(df)} months)")


# %% 1. Descriptive: SAIBOR vs policy rate, and the spread -------------------
# The spread compares a 3-month market rate with an overnight-style policy
# rate. A spread can reflect expectations of future policy, term premia and
# banks' funding conditions; this chart describes it, it does not explain it.
df["spread_bp"] = (df["saibor_3m"] - df["sama_reverse_repo_avg"]) * 100

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True,
                               gridspec_kw={"height_ratios": [3, 2]})
ax1.plot(df.index, df["saibor_3m"], color="#555555", lw=1.4,
         label="3M SAIBOR (monthly avg)")
ax1.plot(df.index, df["sama_reverse_repo_avg"], color="#1f4e8c", lw=1.6,
         label="SAMA reverse repo (monthly avg)")
ax1.plot(df.index, df["sama_repo_avg"], color="#c0504d", lw=1.2,
         label="SAMA repo (monthly avg)")
ax1.set_ylabel("% per year")
ax1.set_title("3M SAIBOR and SAMA policy rates (monthly averages)")
ax1.legend(frameon=False, loc="upper left")
ax2.fill_between(df.index, 0, df["spread_bp"], color="#9db4d6")
ax2.axhline(0, color="#999999", lw=0.8)
ax2.set_ylabel("bp")
ax2.set_title("Spread: 3M SAIBOR minus SAMA reverse repo")
for a in (ax1, ax2):
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "03_saibor_vs_policy.png", dpi=200)
plt.show()

s = df["spread_bp"]
print(f"Spread (bp): mean {s.mean():.0f}, min {s.min():.0f} "
      f"({s.idxmin():%b %Y}), max {s.max():.0f} ({s.idxmax():%b %Y})")
print("Average spread by year:")
print(s.groupby(s.index.year).mean().round(0).to_string())


# %% 2. Why changes, not levels: persistence check ---------------------------
# Lag-one correlation (corr of x_t with x_{t-1}) is a quick persistence
# indicator. It is NOT an estimated AR(1) coefficient and NOT a stationarity
# test. Levels near 1 barely mean-revert, and regressing one such level on
# another can show a strong but spurious relationship, so we use changes.
def lag1_corr(x):
    x = x.dropna()
    return np.corrcoef(x[1:], x[:-1])[0, 1]


for col in ["saibor_3m", "sama_reverse_repo_avg"]:
    print(f"{col:24s} lag-1 corr of level: {lag1_corr(df[col]):.3f}   "
          f"of monthly change: {lag1_corr(df[col].diff()):.3f}")


# %% 3. Statistical tools, written out in numpy -----------------------------
def normal_p(z):
    """Two-sided p-value from the standard normal distribution."""
    return math.erfc(abs(z) / math.sqrt(2))


def chi2_sf(x, k):
    """P(Chi2_k > x), via the regularized incomplete gamma function."""
    a, x = k / 2.0, x / 2.0
    if x <= 0:
        return 1.0
    if x < a + 1:   # series for the lower function
        term, total, n = 1.0 / a, 1.0 / a, 0
        while abs(term) > 1e-12 * abs(total):
            n += 1
            term *= x / (a + n)
            total += term
        return 1 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b, c, d = x + 1 - a, 1e300, 1 / (x + 1 - a)   # continued fraction
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1 / d if d != 0 else 1e300
        c = b + an / c
        delta = c * d
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def ols_hac(y, X, hac_lags):
    """OLS coefficients with Newey-West (Bartlett kernel) covariance."""
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
    r2 = 1 - resid.var() / y.var()
    return beta, cov, resid, r2


def wald(beta, cov, idx):
    """Joint test that the coefficients in idx are all zero."""
    b = beta[idx]
    V = cov[np.ix_(idx, idx)]
    W = float(b @ np.linalg.solve(V, b))
    return W, chi2_sf(W, len(idx))


def ljung_box(resid, lags):
    n = len(resid)
    r = resid - resid.mean()
    denom = (r ** 2).sum()
    q = n * (n + 2) * sum((r[k:] @ r[:-k] / denom) ** 2 / (n - k)
                          for k in range(1, lags + 1))
    return q, chi2_sf(q, lags)


def breusch_godfrey(resid, X, lags):
    """LM test for residual autocorrelation. Unlike Ljung-Box, it stays
    valid when the model includes a lagged dependent variable."""
    n = len(resid)
    R = np.column_stack([np.r_[np.zeros(k), resid[:-k]]
                         for k in range(1, lags + 1)])
    Z = np.column_stack([X, R])
    g = np.linalg.lstsq(Z, resid, rcond=None)[0]
    e = resid - Z @ g
    lm = n * (1 - e.var() / resid.var())
    return lm, chi2_sf(lm, lags)


# %% 4. Build regression data on ONE common set of months -------------------
POLICY = {
    "Reverse repo, next-day timing (MAIN)": "sama_reverse_repo_avg",
    "Reverse repo, same-day timing": "sama_reverse_repo_avg_sameday",
    "Repo, next-day timing (robustness)": "sama_repo_avg",
}

data = pd.DataFrame({"d_saibor": df["saibor_3m"].diff()})
data["d_saibor_lag1"] = data["d_saibor"].shift(1)
for col in POLICY.values():
    dp = df[col].diff()
    for k in range(N_LAGS + 1):
        data[f"{col}_L{k}"] = dp.shift(k)
data = data.dropna()   # ONE common sample for every model, A and B
print(f"Common estimation sample: {data.index.min():%b %Y} to "
      f"{data.index.max():%b %Y}, N = {len(data)} months")

# Newey-West rule-of-thumb bandwidth: floor(4 * (N/100)^(2/9)) -> baseline.
HAC_LAGS = int(4 * (len(data) / 100) ** (2 / 9))
BANDWIDTHS = [HAC_LAGS, 6, 12]
print(f"Baseline HAC bandwidth: {HAC_LAGS}; sensitivity: {BANDWIDTHS}")


def estimate(col, with_lagged_saibor, hac_lags):
    """Model A (baseline) or Model B (adds lagged SAIBOR change)."""
    policy_terms = [f"{col}_L{k}" for k in range(N_LAGS + 1)]
    names = ["const"] + (["phi (lagged dSAIBOR)"] if with_lagged_saibor
                         else []) + [f"lag {k}" for k in range(N_LAGS + 1)]
    cols = (["d_saibor_lag1"] if with_lagged_saibor else []) + policy_terms
    X = np.column_stack([np.ones(len(data)), data[cols].values])
    y = data["d_saibor"].values
    beta, cov, resid, r2 = ols_hac(y, X, hac_lags)
    first_policy = 2 if with_lagged_saibor else 1
    pol_idx = list(range(first_policy, first_policy + N_LAGS + 1))

    out = {"beta": beta, "cov": cov, "names": names, "resid": resid,
           "r2": r2, "X": X}
    w = np.zeros(len(beta))
    w[pol_idx] = 1
    out["sum"], out["sum_se"] = w @ beta, math.sqrt(w @ cov @ w)
    out["wald_lags_1_3"] = wald(beta, cov, pol_idx[1:])

    if with_lagged_saibor:
        phi = beta[1]
        out["phi"] = phi
        # Implied cumulative multiplier and its delta-method SE. The
        # gradient covers BOTH the numerator (sum of b) and phi, so the
        # covariance between them is included.
        g = np.zeros(len(beta))
        g[pol_idx] = 1 / (1 - phi)
        g[1] = out["sum"] / (1 - phi) ** 2
        out["multiplier"] = out["sum"] / (1 - phi)
        out["multiplier_se"] = math.sqrt(g @ cov @ g)
    return out


# %% 5. Estimate Model A (baseline) and Model B (with lagged SAIBOR) --------
MODELS = {"A baseline": False, "B + lagged dSAIBOR": True}
rows, diag, bw_rows = [], [], []
fits = {}
for spec, ldv in MODELS.items():
    for label, col in POLICY.items():
        if ldv and "Repo," in label:
            continue   # model B: reverse repo under both timing conventions
        f = estimate(col, ldv, HAC_LAGS)
        fits[(spec, label)] = f
        se = np.sqrt(np.diag(f["cov"]))
        for i, name in enumerate(f["names"]):
            rows.append({"spec": spec, "policy": label, "term": name,
                         "coef": f["beta"][i], "hac_se": se[i],
                         "ci_low": f["beta"][i] - 1.96 * se[i],
                         "ci_high": f["beta"][i] + 1.96 * se[i],
                         "p_value": normal_p(f["beta"][i] / se[i])})
        rows.append({"spec": spec, "policy": label,
                     "term": "SUM of policy lags 0-3", "coef": f["sum"],
                     "hac_se": f["sum_se"],
                     "ci_low": f["sum"] - 1.96 * f["sum_se"],
                     "ci_high": f["sum"] + 1.96 * f["sum_se"],
                     "p_value": normal_p(f["sum"] / f["sum_se"])})
        if ldv:
            m, mse = f["multiplier"], f["multiplier_se"]
            rows.append({"spec": spec, "policy": label,
                         "term": "IMPLIED MULTIPLIER sum/(1-phi)",
                         "coef": m, "hac_se": mse,
                         "ci_low": m - 1.96 * mse, "ci_high": m + 1.96 * mse,
                         "p_value": normal_p(m / mse)})
        W, pW = f["wald_lags_1_3"]
        lb6, plb6 = ljung_box(f["resid"], 6)
        bg6, pbg6 = breusch_godfrey(f["resid"], f["X"], 6)
        bg12, pbg12 = breusch_godfrey(f["resid"], f["X"], 12)
        diag.append({"spec": spec, "policy": label, "N": len(data),
                     "R2": round(f["r2"], 3),
                     "joint_lags1_3_chi2": round(W, 2),
                     "joint_lags1_3_p": fmt_p(pW),
                     "resid_lag1_corr": round(lag1_corr(
                         pd.Series(f["resid"])), 3),
                     "LjungBox6_p": fmt_p(plb6),
                     "BreuschGodfrey6_p": fmt_p(pbg6),
                     "BreuschGodfrey12_p": fmt_p(pbg12)})
        # HAC bandwidth sensitivity for the headline numbers
        for bw in BANDWIDTHS:
            fb = estimate(col, ldv, bw)
            key, k_se = (("multiplier", "multiplier_se") if ldv
                         else ("sum", "sum_se"))
            bw_rows.append({"spec": spec, "policy": label,
                            "headline": "multiplier" if ldv else "sum 0-3",
                            "hac_bandwidth": bw, "estimate": fb[key],
                            "ci_low": fb[key] - 1.96 * fb[k_se],
                            "ci_high": fb[key] + 1.96 * fb[k_se],
                            "ci_includes_1": (fb[key] - 1.96 * fb[k_se]
                                              <= 1 <= fb[key]
                                              + 1.96 * fb[k_se])})

results = pd.DataFrame(rows)
diagnostics = pd.DataFrame(diag)
bandwidth = pd.DataFrame(bw_rows)
results.to_csv(PROCESSED / "passthrough_results.csv", index=False)
diagnostics.to_csv(PROCESSED / "passthrough_diagnostics.csv", index=False)
bandwidth.to_csv(PROCESSED / "passthrough_bandwidth.csv", index=False)

pd.set_option("display.width", 160)
for (spec, label) in fits:
    r = results[(results["spec"] == spec)
                & (results["policy"] == label)].set_index("term").copy()
    r["p"] = r["p_value"].map(fmt_p)
    print(f"\n=== Model {spec} | {label} ===")
    print(r[["coef", "hac_se", "ci_low", "ci_high", "p"]].round(3)
          .to_string())
print("\nDiagnostics (Breusch-Godfrey is the valid test for model B):")
print(diagnostics.to_string(index=False))
print("\nHAC bandwidth sensitivity of the headline estimate:")
print(bandwidth.round(3).to_string(index=False))


# %% 6. Does the timing convention matter? ----------------------------------
for spec in MODELS:
    a = results[(results["spec"] == spec)
                & results["policy"].str.contains("next-day timing \\(MAIN")]
    b = results[(results["spec"] == spec)
                & results["policy"].str.contains("same-day")]
    cmp_ = pd.DataFrame({"next_day": a.set_index("term")["coef"],
                         "same_day": b.set_index("term")["coef"]})
    cmp_["difference"] = cmp_["same_day"] - cmp_["next_day"]
    print(f"\nModel {spec}: next-day vs same-day timing")
    print(cmp_.drop(index="const").round(3).to_string())


# %% 7. Chart: policy-lag coefficients, model A vs model B (main timing) ----
MAIN = "Reverse repo, next-day timing (MAIN)"
terms = [f"lag {k}" for k in range(N_LAGS + 1)]
fig, ax = plt.subplots(figsize=(10, 4.8))
style = {"A baseline": ("#9db4d6", -0.15), "B + lagged dSAIBOR":
         ("#1f4e8c", 0.15)}
for spec, (color, off) in style.items():
    r = results[(results["spec"] == spec)
                & (results["policy"] == MAIN)].set_index("term")
    head_term = ("IMPLIED MULTIPLIER sum/(1-phi)"
                 if spec.startswith("B") else "SUM of policy lags 0-3")
    rr = r.loc[terms + [head_term]]
    x = np.arange(len(rr)) + off
    ax.errorbar(x, rr["coef"], yerr=[rr["coef"] - rr["ci_low"],
                                      rr["ci_high"] - rr["coef"]],
                fmt="o", color=color, capsize=3,
                label=f"Model {spec}")
ax.axhline(0, color="#999999", lw=0.8)
ax.axhline(1, color="#c0504d", lw=0.8, ls="--")
ax.set_xticks(range(len(terms) + 1))
ax.set_xticklabels(["same month", "1 month later", "2 months later",
                    "3 months later",
                    "cumulative\n(A: sum, B: sum/(1-phi),\nexploratory)"])
ax.set_ylabel("coefficient (SAIBOR change per 1pp policy change)")
ax.set_title("Policy-lag coefficients: model A vs model B (in B these are "
             "conditional on lagged SAIBOR,\nnot the month-by-month "
             f"response). 95% CIs, Newey-West bandwidth {HAC_LAGS}. "
             "Associations, not causal effects.", fontsize=10)
ax.legend(frameon=False, fontsize=8, loc="lower left")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "03_lag_coefficients.png", dpi=200)
plt.show()


# %% 8. Stability check: before Jan 2020 vs Jan 2020 onwards ----------------
# The split date is fixed in advance on economic grounds (COVID-era cuts,
# then the 2022-23 hiking cycle); it is not chosen to maximise a difference.
# This is an EXPLORATORY comparison. Residual autocorrelation alone would
# not show a structural break, and a break here would not identify a cause.
SPLIT = pd.Timestamp("2020-01-01")
post = (data.index >= SPLIT).astype(float)
print(f"Split at {SPLIT:%b %Y}: pre N = {int((1 - post).sum())}, "
      f"post N = {int(post.sum())}")

# How much policy variation does each period contain?
dp_main = data["sama_reverse_repo_avg_L0"]
for name, mask in [("pre-2020", post == 0), ("2020 onwards", post == 1)]:
    x = dp_main[mask]
    print(f"  {name:13s} months with a policy change: {(x != 0).sum():3d}  "
          f"sum of |changes|: {x.abs().sum():.2f}pp  "
          f"std of monthly change: {x.std():.3f}pp")


def num_grad(f, b, eps=1e-6):
    """Numerical gradient, for delta-method standard errors."""
    g = np.zeros(len(b))
    for i in range(len(b)):
        up, dn = b.copy(), b.copy()
        up[i] += eps
        dn[i] -= eps
        g[i] = (f(up) - f(dn)) / (2 * eps)
    return g


def stability(col, with_lagged_saibor, hac_lags):
    """Pooled model: every slope gets a post-2020 interaction term.
    Pre-2020 slope = b; post-2020 slope = b + d. Testing d = 0 tests the
    DIFFERENCE directly."""
    base = (["d_saibor_lag1"] if with_lagged_saibor else []) + \
        [f"{col}_L{k}" for k in range(N_LAGS + 1)]
    Z = data[base].values
    X = np.column_stack([np.ones(len(data)), post, Z, Z * post[:, None]])
    beta, cov, resid, _ = ols_hac(data["d_saibor"].values, X, hac_lags)
    k = len(base)
    pre_i, post_i = list(range(2, 2 + k)), list(range(2 + k, 2 + 2 * k))
    o = 1 if with_lagged_saibor else 0   # position of the first policy term

    def cumulative(b, period):
        slopes = b[pre_i] + (b[post_i] if period == "post" else 0)
        total = slopes[o:].sum()
        return total / (1 - slopes[0]) if with_lagged_saibor else total

    out = {}
    for period in ("pre", "post"):
        f = lambda b, p=period: cumulative(b, p)
        g = num_grad(f, beta)
        out[period] = (f(beta), math.sqrt(g @ cov @ g))
    fd = lambda b: cumulative(b, "post") - cumulative(b, "pre")
    g = num_grad(fd, beta)
    out["diff"] = (fd(beta), math.sqrt(g @ cov @ g))
    out["joint_all_slopes"] = wald(beta, cov, post_i)   # every slope equal?
    return out


rows = []
for spec, ldv in MODELS.items():
    for label, col in list(POLICY.items())[:2]:   # reverse repo, both timings
        for bw in BANDWIDTHS:
            r = stability(col, ldv, bw)
            W, pW = r["joint_all_slopes"]
            row = {"spec": spec, "timing": label.split(",")[1].strip(),
                   "hac_bandwidth": bw}
            for part in ("pre", "post", "diff"):
                est, se = r[part]
                row[f"{part}"] = est
                row[f"{part}_ci"] = (f"{est - 1.96 * se:.2f} to "
                                     f"{est + 1.96 * se:.2f}")
            row["diff_p"] = fmt_p(normal_p(r["diff"][0] / r["diff"][1]))
            row["all_slopes_equal_p"] = fmt_p(pW)
            rows.append(row)
stab = pd.DataFrame(rows)
stab.to_csv(PROCESSED / "passthrough_stability.csv", index=False)
print("\nCumulative association (A: sum, B: multiplier) by period, "
      "and the tested difference (post minus pre):")
print(stab.round(3).to_string(index=False))


# %% 9. Chart: cumulative association by period ------------------------------
main_bw = stab[(stab["hac_bandwidth"] == HAC_LAGS)
               & stab["timing"].str.startswith("next-day")]
fig, ax = plt.subplots(figsize=(8, 4.2))
for i, (_, r) in enumerate(main_bw.iterrows()):
    for j, (part, color) in enumerate([("pre", "#9db4d6"),
                                       ("post", "#1f4e8c")]):
        lo, hi = [float(v) for v in r[f"{part}_ci"].split(" to ")]
        x = i + (j - 0.5) * 0.3
        ax.errorbar(x, r[part], yerr=[[r[part] - lo], [hi - r[part]]],
                    fmt="o", color=color, capsize=4,
                    label=(("May 2009 - Dec 2019" if part == "pre"
                            else "Jan 2020 - Jul 2026") if i == 0 else None))
    ax.text(i, ax.get_ylim()[0] if False else -0.25,
            f"difference p = {r['diff_p']}", ha="center", fontsize=8)
ax.axhline(1, color="#c0504d", lw=0.8, ls="--")
ax.axhline(0, color="#999999", lw=0.8)
ax.set_xticks(range(len(main_bw)))
ax.set_xticklabels(["Model A: sum of lags 0-3",
                    "Model B: sum/(1-phi), exploratory"])
ax.set_ylabel("cumulative association")
ax.set_title("Stability check: before vs from January 2020 (fixed split)\n"
             f"95% CIs, Newey-West bandwidth {HAC_LAGS}; pooled interaction "
             "test for the difference", fontsize=10)
ax.legend(frameon=False, fontsize=8, loc="lower center", ncol=2)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CHARTS / "03_stability.png", dpi=200)
plt.show()
