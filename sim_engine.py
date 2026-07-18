#!/usr/bin/env python3
"""
Rod's Golf Model — Simulation / Variance Engine (module 2)
============================================================
This is the piece the handoff docs flagged as "not built yet." It takes each
player's (mean_fit, var_mult, skew_term) — the three numbers the course-fit
engine (module 1, see course_fit_engine.py) emits per §4 of course_fit_spec.docx
— and turns them into simulated round outcomes. From those simulations it
derives:

  - 2-ball matchup win probabilities (THIS IS THE MODEL NUMBER that should be
    compared against the market, not DataGolf's own model output — comparing
    DG's model to a DG-derived market number tells you nothing about your edge,
    it just tells you whether DG agrees with itself)
  - make-cut / top-N probabilities (stubbed for future use, same simulation core)

Design notes
------------
- Stdlib only (random, math) — consistent with rods_pipeline.py's zero-dependency
  convention, so this drops into the same environment with no pip install.
- Score distribution per round = a two-component mixture:
    (1 - blowup_rate): Normal(mean, sd)
    blowup_rate:       Normal(mean + BLOWUP_SHIFT, sd * 1.4)   <- right-tail/disaster mass
  This directly encodes skew_blowup_rate from the spec (§2.3) rather than
  bolting on a separate skew-normal distribution — simpler, and the fitted
  parameter (blowup_rate) already comes straight out of the course-fit table.
- Ties are voided (excluded from both win totals) — that's how books actually
  settle a push on head-to-head markets, and it keeps the probability honest
  instead of coin-flipping exact ties into 50/50 noise.
- Every matchup gets its own seeded RNG (seed derived from the matchup index)
  so re-runs on the same data are reproducible — useful for debugging when a
  probability looks off.

Usage
-----
    from sim_engine import run_matchup_sim

    players = {
        "Tommy Fleetwood": {"mean": 69.0, "sd": None},   # sd=None -> use course sd
        "Xander Schauffele": {"mean": 69.1, "sd": None},
    }
    course_row = {"scoreSD": 3.8, "blowup": 0.13}   # from the F table, this event
    probs = run_matchup_sim(players, [("Tommy Fleetwood","Xander Schauffele")],
                             course_row=course_row, n_rounds=1)
    # -> {("Tommy Fleetwood","Xander Schauffele"): 0.5231}
"""

import random

TOUR_BASELINE_SD = 2.9   # approx per-round skill-adjusted score SD, tour-wide baseline
DEFAULT_BLOWUP = 0.09    # tour-average right-tail (blow-up) rate, used if course row is missing
BLOWUP_SHIFT = 4.5       # avg strokes added on a blow-up round, on top of the base draw
N_TRIALS = 20000         # Monte Carlo draws per matchup — raise for tighter CIs, costs runtime


def simulate_round(mean, sd, blowup_rate, rng):
    """
    One simulated round score for a player: mean-centered on `mean` (see below
    for why that needed a fix), right-skewed by blowup_rate for realistic
    disaster-round tail risk.

    BUG FIX (confirmed empirically): the naive version of this — draw from
    Normal(mean, sd) normally, or Normal(mean+BLOWUP_SHIFT, sd*1.4) on a
    blow-up round — has a TRUE mean of mean + blowup_rate*BLOWUP_SHIFT, not
    `mean` itself. That's an unwanted systematic bias, not intentional skew.
    It's invisible in head-to-head matchups (both players get the same
    additive shift, so it cancels in the comparison) but directly distorts
    any comparison against an external fixed number — round-score totals,
    outright win markets, anything compared to a real sportsbook line. There
    it doesn't cancel; it just pushes the whole field toward "Over" (or
    "more likely to win/finish well") by a constant amount every time.
    Subtracting blowup_rate*BLOWUP_SHIFT from the input mean before applying
    the mixture keeps the intentional right-skew (blow-up rounds still
    happen, still add tail risk and widen the distribution) while making the
    distribution's actual mean equal to `mean`, as intended.
    """
    adjusted_mean = mean - blowup_rate * BLOWUP_SHIFT
    if rng.random() < blowup_rate:
        return rng.gauss(adjusted_mean + BLOWUP_SHIFT, sd * 1.4)
    return rng.gauss(adjusted_mean, sd)


def player_sd(course_sd, var_mult):
    """Per-player round SD when we don't have a player-specific volatility estimate:
    tour baseline scaled by the course's own variance multiplier."""
    base = course_sd if course_sd else TOUR_BASELINE_SD
    mult = var_mult if var_mult else 1.0
    return base * mult


def matchup_prob(mean_a, mean_b, sd_a, sd_b, blowup_a, blowup_b,
                  n_rounds=1, n_trials=N_TRIALS, seed=None):
    """
    Monte Carlo win probability for player A over player B, summed across
    n_rounds (n_rounds=1 for a single-round 2-ball, higher for 72-hole markets).
    Returns P(A wins | decided) — ties are voided, matching how the book settles.
    """
    rng = random.Random(seed)
    wins_a = 0
    decided = 0
    for _ in range(n_trials):
        sa = sum(simulate_round(mean_a, sd_a, blowup_a, rng) for _ in range(n_rounds))
        sb = sum(simulate_round(mean_b, sd_b, blowup_b, rng) for _ in range(n_rounds))
        if sa < sb:
            wins_a += 1
            decided += 1
        elif sb < sa:
            decided += 1
        # else: exact float tie, essentially never happens, skipped either way
    if decided == 0:
        return 0.5
    return wins_a / decided


def run_matchup_sim(players, matchups, course_row=None, n_rounds=1, n_trials=N_TRIALS):
    """
    players:   dict name -> {"mean": projected_score, "sd": player_sd_or_None}
    matchups:  list of (p1_name, p2_name) pairs needing a model probability
    course_row: dict with at least 'scoreSD' and 'blowup' for this event — applied
                uniformly when a player-level SD isn't known (i.e. Path A; once
                Path B gives you per-player volatility this can be passed via
                players[name]['sd'] and this course-level fallback is skipped)
    n_rounds:  1 for a single-round 2-ball matchup, 4 for a 72-hole matchup
    Returns: dict (p1, p2) -> model_prob_p1, rounded to 4 decimals.
             Pairs missing a projection for either player are silently skipped
             (caller should treat a missing key as "no model number available").
    """
    if course_row:
        course_sd = course_row.get("scoreSD") or TOUR_BASELINE_SD
        var_mult = course_sd / TOUR_BASELINE_SD
        blowup = course_row.get("blowup", DEFAULT_BLOWUP)
    else:
        course_sd, var_mult, blowup = TOUR_BASELINE_SD, 1.0, DEFAULT_BLOWUP

    out = {}
    for i, (p1, p2) in enumerate(matchups):
        d1, d2 = players.get(p1), players.get(p2)
        if not d1 or not d2 or d1.get("mean") is None or d2.get("mean") is None:
            continue
        sd1 = d1.get("sd") or player_sd(course_sd, var_mult)
        sd2 = d2.get("sd") or player_sd(course_sd, var_mult)
        p = matchup_prob(d1["mean"], d2["mean"], sd1, sd2, blowup, blowup,
                          n_rounds=n_rounds, n_trials=n_trials, seed=1000 + i)
        out[(p1, p2)] = round(p, 4)
    return out


def run_finish_sim(players, course_row=None, n_rounds=4, n_trials=10000, top_ns=(5, 10, 20)):
    """
    Full-field simulation: every player draws n_rounds simulated rounds per
    trial (same simulate_round() core as the matchup sim), the field is
    ranked by total simulated score each trial, and win/top-N rates are
    tallied across all trials.

    players: dict name -> {"mean": proj_score, "sd": player_sd_or_None}
             (same shape as run_matchup_sim's players arg)
    course_row: {'scoreSD':, 'blowup':} — same course-level fallback as the
                matchup sim, applied when a player-level SD isn't known.
    Returns: dict name -> {"win": frac, "top5": frac, "top10": frac, "top20": frac}
             Players missing a projection are excluded from the field entirely
             (can't rank someone with no projected score).

    Cost note: n_rounds * n_trials * len(players) gaussian draws — for a
    156-player field at the defaults here that's ~6.2M draws, which runs in
    single-digit seconds in pure Python. Drop n_trials if this needs to be
    faster; win-rate precision degrades gracefully (it's a Monte Carlo SE,
    not a cliff).
    """
    if course_row:
        course_sd = course_row.get("scoreSD") or TOUR_BASELINE_SD
        var_mult = course_sd / TOUR_BASELINE_SD
        blowup = course_row.get("blowup", DEFAULT_BLOWUP)
    else:
        course_sd, var_mult, blowup = TOUR_BASELINE_SD, 1.0, DEFAULT_BLOWUP

    names, means, sds = [], [], []
    for name, d in players.items():
        if d.get("mean") is None:
            continue
        names.append(name)
        means.append(d["mean"])
        sds.append(d.get("sd") or player_sd(course_sd, var_mult))

    n = len(names)
    if n == 0:
        return {}

    wins = [0] * n
    top_counts = {k: [0] * n for k in top_ns}
    max_top = max(top_ns)
    rng = random.Random(42)  # fixed seed: reproducible field-sim results across runs

    for _ in range(n_trials):
        totals = [
            sum(simulate_round(means[i], sds[i], blowup, rng) for _ in range(n_rounds))
            for i in range(n)
        ]
        # rank ascending (lowest total = best); track indices, not just sorted values
        order = sorted(range(n), key=lambda i: totals[i])
        wins[order[0]] += 1
        for k in top_ns:
            for idx in order[:k]:
                top_counts[k][idx] += 1

    out = {}
    for i, name in enumerate(names):
        row = {"win": wins[i] / n_trials}
        for k in top_ns:
            row[f"top{k}"] = top_counts[k][i] / n_trials
        out[name] = row
    return out


if __name__ == "__main__":
    # quick self-test with illustrative numbers — run: python3 sim_engine.py
    demo_players = {
        "Tommy Fleetwood": {"mean": 69.0, "sd": None},
        "Xander Schauffele": {"mean": 69.1, "sd": None},
        "Bryson DeChambeau": {"mean": 69.6, "sd": None},
        "Shane Lowry": {"mean": 69.6, "sd": None},
    }
    demo_course = {"scoreSD": 3.8, "blowup": 0.13}  # Royal Birkdale, links-tuned
    demo_matchups = [
        ("Tommy Fleetwood", "Xander Schauffele"),
        ("Bryson DeChambeau", "Shane Lowry"),
    ]
    probs = run_matchup_sim(demo_players, demo_matchups, course_row=demo_course, n_rounds=1)
    for (a, b), p in probs.items():
        print(f"{a} vs {b}: model P({a}) = {p:.1%}   P({b}) = {1-p:.1%}")
