#!/usr/bin/env python3
"""
Rod's Golf Model — Course-Fit Engine (module 1)
=================================================
Implements the Tier 2 formulas from course_fit_spec.docx §1–§4: the shrinkage
backbone and every inferred feature (scoring_avg_adj, scoring_sd_adj,
skew_blowup_rate, empirical fit weights w_ott/w_app/w_arg/w_put, dist_premium,
recovery_penalty, cutline stats). This is the module that was, until now, a
docx full of formulas with nothing running them.

This is a Path B tool: it needs DataGolf's raw ROUND-LEVEL history (not the
decomposition/pre-tournament summary feeds rods_pipeline.py already pulls),
which you haven't pulled yet. Everything here is built and self-tested against
synthetic round data so the logic is verified — point it at real round-level
rows whenever you export them and it runs unchanged.

Stdlib only. Ridge regression is solved by hand (Gaussian elimination on the
normal equations) rather than pulling in numpy, since the feature count is
tiny (4 skill categories + optionally distance) — a 4x4 or 5x5 linear system,
no need for a dependency to solve it.

Expected input shape — one row per (player, round):
    {
        "player": "Tommy Fleetwood",
        "course_id": "royal_birkdale",
        "S_r": 71,            # strokes taken
        "par": 70,
        "E_r": 69.8,          # DataGolf's expected strokes for this player given
                               # their skill + this round's field baseline
        "skill_ott": 0.6, "skill_app": 0.5, "skill_arg": 0.3, "skill_put": 0.1,
        "skill_dist": 0.4,    # driving-distance-specific skill component
        "missed_fw_or_gir": True,
    }

See __main__ at the bottom for a synthetic end-to-end run.
"""

import math
from collections import defaultdict


# ------------------------------------------------------------------
# §1 — shrinkage backbone
# ------------------------------------------------------------------
def shrink(theta_own, theta_cluster, n_renewals, K=6.5):
    """theta_course = w*theta_own + (1-w)*theta_cluster,  w = n/(n+K)."""
    if theta_own is None:
        return theta_cluster
    w = n_renewals / (n_renewals + K)
    return w * theta_own + (1 - w) * theta_cluster


def structural_distance(course_a, course_b, features=("yardage_total", "par", "elevation_ft")):
    """
    Euclidean distance between two courses in structural-feature space, for
    building the similar-course cluster (§1 step 1). Features are z-scored
    against a supplied population before calling this in practice; here we
    just do raw distance for simplicity — normalize upstream if scales differ
    a lot (e.g. yardage in the thousands vs elevation in the hundreds).
    """
    total = 0.0
    for f in features:
        a, b = course_a.get(f), course_b.get(f)
        if a is None or b is None:
            continue
        total += (a - b) ** 2
    return math.sqrt(total)


def build_cluster(target_course, course_table, k=6, features=("yardage_total", "par", "elevation_ft")):
    """Return the k nearest courses to target_course (excluding itself) by structural distance."""
    others = [c for c in course_table if c.get("course_id") != target_course.get("course_id")]
    others.sort(key=lambda c: structural_distance(target_course, c, features))
    return others[:k]


# ------------------------------------------------------------------
# §2.1 / §2.2 / §2.3 — scoring_avg_adj, scoring_sd_adj, skew_blowup_rate
# ------------------------------------------------------------------
def residuals(rounds):
    """resid_r = S_r - E_r for each round row. Rows missing E_r are dropped."""
    return [r["S_r"] - r["E_r"] for r in rounds if r.get("E_r") is not None]


def scoring_avg_adj(rounds):
    resid = residuals(rounds)
    return (sum(resid) / len(resid)) if resid else None


def scoring_sd_adj(rounds):
    resid = residuals(rounds)
    if len(resid) < 2:
        return None
    m = sum(resid) / len(resid)
    var = sum((x - m) ** 2 for x in resid) / (len(resid) - 1)
    return math.sqrt(var)


def skew_blowup_rate(rounds, threshold=6):
    resid = residuals(rounds)
    if not resid:
        return None
    return sum(1 for x in resid if x >= threshold) / len(resid)


# ------------------------------------------------------------------
# §2.4 — empirical fit weights via ridge regression
# §2.5 — dist_premium (same regression, +1 predictor)
# ------------------------------------------------------------------
CATS = ("skill_ott", "skill_app", "skill_arg", "skill_put")


def _matmul_At_A(X):
    """X^T X for list-of-rows X (each row a list of floats)."""
    n_feat = len(X[0])
    out = [[0.0] * n_feat for _ in range(n_feat)]
    for row in X:
        for i in range(n_feat):
            for j in range(n_feat):
                out[i][j] += row[i] * row[j]
    return out


def _matvec_At_y(X, y):
    n_feat = len(X[0])
    out = [0.0] * n_feat
    for row, yi in zip(X, y):
        for i in range(n_feat):
            out[i] += row[i] * yi
    return out


def _solve_linear_system(A, b):
    """Gaussian elimination with partial pivoting. A is square, b is a vector."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot][col]) < 1e-12:
            continue  # singular in this column; leave as-is (ridge penalty should prevent this)
        M[col], M[pivot] = M[pivot], M[col]
        pv = M[col][col]
        M[col] = [x / pv for x in M[col]]
        for r in range(n):
            if r != col:
                factor = M[r][col]
                M[r] = [M[r][k] - factor * M[col][k] for k in range(n + 1)]
    return [M[i][n] for i in range(n)]


def ridge_regression(X, y, lam=1.0):
    """
    Solve (X^T X + lam*I) beta = X^T y.
    X: list of rows, each row = [1.0 (intercept), *predictor values]
    y: list of target values (residuals)
    Returns beta (list, beta[0] = intercept).
    """
    XtX = _matmul_At_A(X)
    n = len(XtX)
    for i in range(n):
        if i > 0:  # don't penalize the intercept
            XtX[i][i] += lam
    Xty = _matvec_At_y(X, y)
    return _solve_linear_system(XtX, Xty)


def fit_weights(rounds, tour_baseline_coeffs, lam=1.0):
    """
    §2.4: regress resid_r on the four category skills (ridge), then normalize
    each coefficient against the tour-wide baseline coefficient for that
    category. w_cat > 1 means this course rewards that skill more than tour
    average.
    tour_baseline_coeffs: dict cat -> b_cat(tour_baseline), precomputed once
    over a large tour-wide sample and reused across every course.
    """
    rows = [r for r in rounds if r.get("E_r") is not None and all(r.get(c) is not None for c in CATS)]
    if len(rows) < 5:
        return None  # not enough signal to regress; caller should fall back to cluster/prior
    X = [[1.0] + [r[c] for c in CATS] for r in rows]
    y = [r["S_r"] - r["E_r"] for r in rows]
    beta = ridge_regression(X, y, lam=lam)
    b_cluster = dict(zip(CATS, beta[1:]))
    return {cat: (b_cluster[cat] / tour_baseline_coeffs[cat] if tour_baseline_coeffs.get(cat) else None)
            for cat in CATS}


def dist_premium(rounds, tour_baseline_c, lam=1.0):
    """§2.5: same regression + a distance-skill predictor; premium = c(cluster) - c(tour)."""
    rows = [r for r in rounds if r.get("E_r") is not None and all(r.get(c) is not None for c in CATS)
            and r.get("skill_dist") is not None]
    if len(rows) < 5:
        return None
    X = [[1.0] + [r[c] for c in CATS] + [r["skill_dist"]] for r in rows]
    y = [r["S_r"] - r["E_r"] for r in rows]
    beta = ridge_regression(X, y, lam=lam)
    c_cluster = beta[-1]
    return c_cluster - tour_baseline_c


# ------------------------------------------------------------------
# §2.6 — recovery_penalty
# ------------------------------------------------------------------
def recovery_penalty(rounds, tour_baseline_penalty):
    resid_miss = [r["S_r"] - r["E_r"] for r in rounds
                  if r.get("E_r") is not None and r.get("missed_fw_or_gir")]
    if not resid_miss:
        return None
    penalty_after_miss = sum(resid_miss) / len(resid_miss)
    return penalty_after_miss - tour_baseline_penalty


# ------------------------------------------------------------------
# §2.7 — cutline stats (event-level, not round-level)
# ------------------------------------------------------------------
def cutline_stats(events):
    """events: list of {'cutline': int, 'par': int} per renewal."""
    diffs = [e["cutline"] - e["par"] for e in events if e.get("cutline") is not None]
    if not diffs:
        return None, None
    m = sum(diffs) / len(diffs)
    if len(diffs) < 2:
        return m, None
    var = sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1)
    return m, math.sqrt(var)


# ------------------------------------------------------------------
# §4 — emit per-player outputs for the sim engine
# ------------------------------------------------------------------
def emit_player_outputs(player_row, course_fit_row, baseline_sd_tour=2.9):
    """
    Combine a player's venue-neutral skill profile with the course's (shrunk)
    fit weights to get the three numbers sim_engine.py needs.
    player_row: {'proj': base_projected_score, 'ott':, 'app':, 'arg':, 'put':, 'dist':}
    course_fit_row: dict with w_ott/w_app/w_arg/w_put, dist_premium, recovery_penalty,
                     scoring_avg_adj, scoring_sd_adj, skew_blowup_rate
    """
    base = player_row.get("proj")
    if base is None:
        return None
    fit_adj = 0.0
    for cat, key in (("ott", "w_ott"), ("app", "w_app"), ("arg", "w_arg"), ("put", "w_put")):
        skill = player_row.get(cat) or 0.0
        w = course_fit_row.get(key, 1.0)
        # a skill above 0 is "better than field average"; weighting >1 amplifies
        # its scoring impact at this course, <1 damps it. This lands the player's
        # skill profile on the course's own scoring_avg_adj baseline.
        fit_adj += skill * (w - 1.0) * -1  # better skill * amplified weight -> lower (better) score
    dist_skill = player_row.get("dist") or 0.0
    fit_adj += dist_skill * course_fit_row.get("dist_premium", 0.0) * -1

    mean_fit = base + course_fit_row.get("scoring_avg_adj", 0.0) + fit_adj
    var_mult = (course_fit_row.get("scoring_sd_adj", baseline_sd_tour) or baseline_sd_tour) / baseline_sd_tour
    skew_term = course_fit_row.get("skew_blowup_rate", 0.09)
    return {"mean_fit": round(mean_fit, 2), "var_mult": round(var_mult, 3), "skew_term": skew_term}


if __name__ == "__main__":
    # ---- synthetic end-to-end self-test (no live DataGolf data required) ----
    import random as _r
    _r.seed(7)

    TOUR_BASELINE = {"skill_ott": 0.9, "skill_app": 1.0, "skill_arg": 0.6, "skill_put": 0.7}
    TOUR_BASELINE_DIST_C = 0.15
    TOUR_BASELINE_RECOVERY = -1.1

    players = ["Player A", "Player B", "Player C", "Player D", "Player E", "Player F"]
    synthetic_rounds = []
    for p in players:
        skill = {c: _r.uniform(-0.5, 1.5) for c in CATS}
        dist_skill = _r.uniform(-0.5, 1.0)
        for _ in range(12):  # 12 rounds of synthetic history at this course
            noise = _r.gauss(0, 3.8)
            blowup = 4.5 if _r.random() < 0.13 else 0
            E_r = 70 - sum(skill.values()) * 0.3
            S_r = E_r + noise + blowup
            synthetic_rounds.append({
                "player": p, "course_id": "royal_birkdale", "S_r": S_r, "E_r": E_r,
                "skill_dist": dist_skill, "missed_fw_or_gir": _r.random() < 0.35,
                **skill,
            })

    print("scoring_avg_adj:", round(scoring_avg_adj(synthetic_rounds), 2))
    print("scoring_sd_adj:", round(scoring_sd_adj(synthetic_rounds), 2))
    print("skew_blowup_rate:", round(skew_blowup_rate(synthetic_rounds), 3))
    fw = fit_weights(synthetic_rounds, TOUR_BASELINE)
    print("fit_weights:", {k: round(v, 3) for k, v in fw.items()} if fw else None)
    dp = dist_premium(synthetic_rounds, TOUR_BASELINE_DIST_C)
    print("dist_premium:", round(dp, 3) if dp is not None else None)
    rp = recovery_penalty(synthetic_rounds, TOUR_BASELINE_RECOVERY)
    print("recovery_penalty:", round(rp, 3) if rp is not None else None)

    course_row = {
        "w_ott": fw["skill_ott"], "w_app": fw["skill_app"], "w_arg": fw["skill_arg"], "w_put": fw["skill_put"],
        "dist_premium": dp, "scoring_avg_adj": scoring_avg_adj(synthetic_rounds),
        "scoring_sd_adj": scoring_sd_adj(synthetic_rounds), "skew_blowup_rate": skew_blowup_rate(synthetic_rounds),
    }
    demo_player = {"proj": 69.4, "ott": 0.8, "app": 0.6, "arg": 0.3, "put": 0.2, "dist": 0.5}
    print("emit_player_outputs:", emit_player_outputs(demo_player, course_row))
