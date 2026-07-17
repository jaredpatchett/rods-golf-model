#!/usr/bin/env python3
"""
End-to-end pipeline test using MOCK DataGolf responses.

I don't have network access to feeds.datagolf.com from this environment, so
this can't validate against the real API's actual field names — that's still
your shakedown run on the Mac (HANDOFF.md step 3). What this DOES verify:
the pipeline's plumbing (fetch -> build_projections -> merge -> build_matchups
-> sim_engine -> course fit table -> final JSON) runs without errors and
produces a rods_data.json shaped exactly the way the HTML page expects it,
using response shapes modeled on the field names the pick() helpers already
guess for. If DataGolf's real field names differ, you'll see it immediately
as blank columns on the first live run — same as before, that part hasn't
changed.

Run: python3 test_pipeline_mock.py
"""

import json
import sys
from unittest import mock

import rods_pipeline as pipe

MOCK_DECOMP = {
    "players": [
        {"player_name": "Fleetwood, Tommy", "dg_id": 1, "sg_t2g": 1.7, "sg_ott": 0.6,
         "sg_app": 0.8, "sg_putt": 0.4, "sg_arg": 0.5, "course_fit": 2.4},
        {"player_name": "Schauffele, Xander", "dg_id": 2, "sg_t2g": 1.8, "sg_ott": 0.7,
         "sg_app": 0.9, "sg_putt": 0.3, "sg_arg": 0.2, "course_fit": 1.8},
        {"player_name": "Scheffler, Scottie", "dg_id": 3, "sg_t2g": 2.6, "sg_ott": 0.9,
         "sg_app": 1.2, "sg_putt": 0.8, "sg_arg": 0.4, "course_fit": 2.2},
        {"player_name": "Lowry, Shane", "dg_id": 4, "sg_t2g": 1.2, "sg_ott": 0.4,
         "sg_app": 0.6, "sg_putt": 0.3, "sg_arg": 0.5, "course_fit": 2.1},
    ]
}

MOCK_PRETOURN = {
    "baseline": [
        {"player_name": "Fleetwood, Tommy", "proj_score_avg": 69.0},
        {"player_name": "Schauffele, Xander", "proj_score_avg": 69.1},
        {"player_name": "Scheffler, Scottie", "proj_score_avg": 68.4},
        {"player_name": "Lowry, Shane", "proj_score_avg": 69.6},
    ]
}

MOCK_FIELD = {
    "field": [
        {"player_name": "Fleetwood, Tommy", "r1_teetime": "2026-07-16T08:20"},
        {"player_name": "Schauffele, Xander", "r1_teetime": "2026-07-16T08:20"},
        {"player_name": "Scheffler, Scottie", "r1_teetime": "2026-07-16T13:40"},
        {"player_name": "Lowry, Shane", "r1_teetime": "2026-07-16T13:40"},
    ]
}

MOCK_MATCHUPS = {
    "matchups": [
        {"p1_player_name": "Fleetwood, Tommy", "p2_player_name": "Schauffele, Xander",
         "p1_odds": "-115"},
        {"p1_player_name": "Scheffler, Scottie", "p2_player_name": "Lowry, Shane",
         "p1_odds": "-260"},
    ]
}


def fake_fetch(endpoint, key, **params):
    if endpoint == pipe.EP["decomp"]:
        return MOCK_DECOMP
    if endpoint == pipe.EP["pretourn"]:
        return MOCK_PRETOURN
    if endpoint == pipe.EP["field"]:
        return MOCK_FIELD
    if endpoint == pipe.EP["matchups"]:
        return MOCK_MATCHUPS
    raise AssertionError(f"unexpected endpoint {endpoint}")


def main():
    with mock.patch.object(pipe, "fetch", side_effect=fake_fetch), \
         mock.patch.object(pipe, "get_key", return_value="fake-key-for-test"):
        data = pipe.build("pga")

    # ---- shape assertions matching what rods_golf_model.html's JS expects ----
    assert isinstance(data["P"], list) and len(data["P"]) == 4, "P should have 4 mock players"
    assert isinstance(data["F"], list) and len(data["F"]) >= 1, "F should have at least one course row"
    assert isinstance(data["M"], list) and len(data["M"]) == 2, "M should have 2 mock matchups"

    for row in data["P"]:
        assert len(row) == 8, f"P row wrong length: {row}"
    for row in data["M"]:
        assert len(row) == 6, f"M row wrong length: {row}"
        name_a, name_b, wave, model, market, price = row
        assert model is None or 0.0 <= model <= 1.0, f"model% out of range: {row}"
        assert market is None or 0.0 <= market <= 1.0, f"market% out of range: {row}"

    # sanity: Scheffler (proj 68.4) should be strongly favored over Lowry (69.6) by the sim
    scheffler_lowry = next(r for r in data["M"] if r[0] == "Scottie Scheffler")
    assert scheffler_lowry[3] > 0.55, f"expected Scheffler favored by sim, got {scheffler_lowry}"

    print("ALL ASSERTIONS PASSED\n")
    print(json.dumps(data, indent=1))


if __name__ == "__main__":
    main()
