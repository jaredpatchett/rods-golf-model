#!/usr/bin/env python3
"""
Rod's Golf Model -- Birdie/Bogey Count Engine (module 2)
==========================================================
Answers "is our model data good enough for Birdies Or Better / Bogeys or
Worse fantasy-points lines" with an actual model instead of "no." Same
two-stage approach as course_fit_engine.py (module 1): real, tested math
now, wired to real data once the real field names are confirmed.

WHY THIS EXISTS: PrizePicks (confirmed live via the Apify scraper --
"PrizePicks Player Props Scraper - Real-Time Lines", run eD3YvU2FGDinUMpI3)
prices real "Birdies Or Better 3.5" / "Bogeys Or Worse 2.5" round props for
TPC Southwind. Nothing in this codebase could put a probability on those
before now -- sim_engine.py models total round SCORE (mean + variance +
blowup skew), not hole-by-hole birdie/bogey COUNTS, a genuinely different
kind of distribution.

THE MODEL: birdie-or-better count and bogey-or-worse count per round are
each modeled as Binomial(18, p) -- 18 holes, each an independent
birdie-or-better / bogey-or-worse "success" with probability p. This is a
deliberately simple starting point, not the final word:
  - Real birdie-making isn't perfectly hole-independent (hot/cold streaks,
    round-to-round variance) -- a Beta-Binomial (letting p itself vary
    round to round around a player's true average) would fit real data
    better, with fatter tails than plain Binomial. Not implemented yet --
    there's no real per-round birdie/bogey count data to fit its dispersion
    parameter against. Flagging this rather than quietly baking in a false
    precision.
  - p_birdie and p_bogey are currently derived from PUBLICLY-KNOWN, ROUGH
    PGA TOUR AVERAGES (see BASELINE_BIRDIES_PER_ROUND / BASELINE_BOGEYS_
    PER_ROUND below) shifted by the player's own projected strokes-gained-
    vs-field for that round, via a simple linear conversion
    (STROKES_PER_BIRDIE_SHIFT / STROKES_PER_BOGEY_SHIFT). These conversion
    constants are estimates, not fit from real data -- same caveat
    DEFAULT_BASELINE_ROUND_SCORE carried in rods_pipeline.py before it got
    real course-specific calibration.

WHAT WOULD MAKE THIS REAL: DataGolf's changelog (2025-02-14) says "hole
score counts (birdies, pars, bogeys, etc)" were added to their raw
round-level data for PGA/EUR/KFT/LIV tours -- but the exact field names
aren't in their published data dictionary. discover_round_shape.py
(already in this repo, already wired to the "Discover Open Championship
history" GitHub Action) hits that same endpoint and prints every field
name it sees -- it just hasn't actually been run and shared yet. Once it
has, and IF a birdie/bogey/par count field shows up there, the baseline
constants and the SG-to-rate conversion below get replaced with real
fitted numbers instead of Tour-average estimates, and ideally the Binomial
model gets upgraded to Beta-Binomial using the real dispersion in that
data.

Stdlib only -- same reasoning as course_fit_engine.py: the math here
(18-trial binomial survival function) is small enough not to need
numpy/scipy.
"""
import math

# ------------------------------------------------------------------
# Baseline rates -- rough PGA Tour averages, NOT derived from real
# per-player/per-course data yet. Commonly cited Tour-wide figures run
# roughly 3.5-4.0 birdies/round and 2.5-3.0 bogeys-or-worse/round for an
# average field; using the midpoints below as neutral defaults until real
# data replaces them.
# ------------------------------------------------------------------
BASELINE_BIRDIES_PER_ROUND = 3.75
BASELINE_BOGEYS_PER_ROUND = 2.75
BASELINE_BIRDIE_RATE = BASELINE_BIRDIES_PER_ROUND / 18
BASELINE_BOGEY_RATE = BASELINE_BOGEYS_PER_ROUND / 18

# Rough conversion: how much does 1 stroke of projected strokes-gained-vs-
# field shift birdie/bogey rate? A player projected 1 stroke better than
# the field baseline should make noticeably more birdies and noticeably
# fewer bogeys than average -- these constants are estimates (picked to
# keep the swing plausible across the +/-3 stroke range real player
# projections actually span), not fit from real hole-by-hole data.
STROKES_PER_BIRDIE_SHIFT = 0.55   # +1 stroke gained -> ~0.55 more expected birdies/round
STROKES_PER_BOGEY_SHIFT = 0.45    # +1 stroke gained -> ~0.45 fewer expected bogeys/round


def _clamp01(p):
    return max(0.0005, min(0.9995, p))


def binomial_sf(k, n, p):
    """P(X > k) for X ~ Binomial(n, p) -- i.e. P(X >= k+1). Used for lines
    like 'Birdies Or Better 3.5' -> P(count >= 4). Direct summation -- n is
    always 18 here, cheap enough not to need an incomplete-beta shortcut."""
    p = _clamp01(p)
    if k >= n:
        return 0.0
    if k < 0:
        return 1.0
    total = 0.0
    for i in range(k + 1, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return total


def birdie_rate_for_player(strokes_gained_vs_field, baseline_rate=BASELINE_BIRDIE_RATE,
                            shift_per_stroke=STROKES_PER_BIRDIE_SHIFT, holes=18):
    """Player's expected per-hole birdie-or-better probability, shifted from
    the Tour-average baseline by their projected strokes-gained for this
    round. strokes_gained_vs_field > 0 means better than average -- the same
    'fit'-adjusted number rods_pipeline.py / course_fit_engine.py already
    compute per player, feed that straight in here."""
    expected_birdies = baseline_rate * holes + strokes_gained_vs_field * shift_per_stroke
    return _clamp01(expected_birdies / holes)


def bogey_rate_for_player(strokes_gained_vs_field, baseline_rate=BASELINE_BOGEY_RATE,
                           shift_per_stroke=STROKES_PER_BOGEY_SHIFT, holes=18):
    """Same idea, opposite sign -- better strokes-gained means FEWER expected
    bogeys-or-worse."""
    expected_bogeys = baseline_rate * holes - strokes_gained_vs_field * shift_per_stroke
    return _clamp01(expected_bogeys / holes)


def birdies_or_better_prob(line, strokes_gained_vs_field, holes=18):
    """P(birdie-or-better count > line) for a PrizePicks-style '.5' line,
    e.g. line=3.5 -> P(count >= 4). Also works for whole-number lines (uses
    the same survival function with floor(line) as the cutoff)."""
    p = birdie_rate_for_player(strokes_gained_vs_field, holes=holes)
    k = math.floor(line)
    return binomial_sf(k, holes, p)


def bogeys_or_worse_prob(line, strokes_gained_vs_field, holes=18):
    """P(bogey-or-worse count > line)."""
    p = bogey_rate_for_player(strokes_gained_vs_field, holes=holes)
    k = math.floor(line)
    return binomial_sf(k, holes, p)


if __name__ == "__main__":
    # ---- self-test against known reference points, no live data required ----
    avg_birdie_p = birdie_rate_for_player(0.0)
    avg_bogey_p = bogey_rate_for_player(0.0)
    print(f"Average player birdie rate/hole: {avg_birdie_p:.4f} "
          f"(-> {avg_birdie_p*18:.2f} birdies/round, baseline was {BASELINE_BIRDIES_PER_ROUND})")
    print(f"Average player bogey rate/hole:  {avg_bogey_p:.4f} "
          f"(-> {avg_bogey_p*18:.2f} bogeys/round, baseline was {BASELINE_BOGEYS_PER_ROUND})")

    print("\nSG    P(birdies>=4)  P(bogeys>=3)")
    for sg in [-2, -1, 0, 1, 2]:
        p_over = birdies_or_better_prob(3.5, sg)
        p_bogey_over = bogeys_or_worse_prob(2.5, sg)
        print(f"{sg:+.1f}   {p_over:.3f}          {p_bogey_over:.3f}")

    # Sanity checks -- better players (higher strokes-gained) should show
    # monotonically increasing birdie probability and monotonically
    # decreasing bogey probability.
    birdie_probs = [birdies_or_better_prob(3.5, sg) for sg in [-2, -1, 0, 1, 2]]
    bogey_probs = [bogeys_or_worse_prob(2.5, sg) for sg in [-2, -1, 0, 1, 2]]
    assert birdie_probs == sorted(birdie_probs), "birdie prob should rise with strokes-gained"
    assert bogey_probs == sorted(bogey_probs, reverse=True), "bogey prob should fall with strokes-gained"

    # binomial_sf sanity: probabilities must sum to 1 across the full range.
    p = 0.2
    total = sum(math.comb(18, i) * (p ** i) * ((1 - p) ** (18 - i)) for i in range(19))
    assert abs(total - 1.0) < 1e-9, f"binomial pmf should sum to 1, got {total}"

    print("\nAll self-tests passed.")
