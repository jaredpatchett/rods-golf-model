#!/usr/bin/env python3
"""
Rod's Golf Model -- OddsPapi discovery script
==============================================
Path C, step 1: OddsPapi (oddspapi.io) claims coverage of PrizePicks odds
alongside 300+ other bookmakers, including player props. This script does
NOT assume anything about golf's sportId, market IDs, or PrizePicks' exact
bookmaker key in their system -- every one of those needs to be confirmed
live before any of it gets wired into rods_pipeline.py. Same discipline as
discover_round_shape.py: guessing field shapes has broken this app before --
the matchup dedup bug, the EV%/Edge% swap, the wind double-count -- all three
came from trusting an assumed shape instead of a confirmed one.

CONFIRMED from real runs so far:
  - Golf sportId = 67
  - "prizepicks" is a real, valid bookmaker key (351 total bookmakers)
  - /v4/tournaments?sportId=67 returns 1300+ rows -- the ENTIRE historical
    catalog, and every row shows futureFixtures/upcomingFixtures/liveFixtures
    = 0 regardless of whether the event is live -- filtering by name/slug is
    the only reliable way to find "this week's event."
  - Even after filtering tournaments down to just EVENT_KEYWORD matches, the
    full run STILL blew past 10k lines -- meaning /v4/markets?sportId=67
    (the full golf market catalog, every market * every outcome, printed as
    nested JSON) is almost certainly the real source of the bloat, not the
    tournament list.

Fix this round: steps 3 and 4 now print ONE COMPACT LINE per entry
(id | name | key flags) instead of full indented JSON with nested arrays.
Full JSON detail is kept ONLY for playerProp=true markets in step 4 (there
should be relatively few of those) and for the final odds payload in step 5,
which was already capped at 8000 chars.

Update EVENT_KEYWORD each week to whatever event is current.

What this script does, in order:
  1. GET /v4/sports              -> confirm golf's sportId (already known: 67)
  2. GET /v4/bookmakers          -> confirm "prizepicks" (already known: real)
  3. GET /v4/tournaments         -> find EVENT_KEYWORD's tournamentId(s), one line each
  4. GET /v4/markets             -> one line per market; full detail only for playerProp ones
  5. GET /v4/odds-by-tournaments -> pull real PrizePicks-tagged odds, capped at 8000 chars

Run this (locally or via the matching discover-oddspapi.yml workflow), paste
the full output back, and the real pipeline/engine integration gets built
against what's actually there -- not against a guess.
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://api.oddspapi.io"

# Change this each week to whatever event is current. Matches against both
# tournamentSlug and categorySlug, case-insensitive substring.
EVENT_KEYWORD = "fedex-st-jude"


def get_key():
    key = os.environ.get("ODDSPAPI_KEY")
    if not key:
        sys.exit('ERROR: set your key first ->  export ODDSPAPI_KEY="your_oddspapi_key"')
    return key


def fetch(endpoint, key, **params):
    params["apiKey"] = key
    url = f"{BASE}{endpoint}?{urllib.parse.urlencode(params)}"
    # Confirmed cause of the original HTTP 403 "error code: 1010": Cloudflare's Browser
    # Integrity Check reacting to urllib's bare "Python-urllib/3.x" User-Agent, not an
    # OddsPapi/key rejection. Normal browser-like headers fixed it.
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise SystemExit(f"HTTP {e.code} on {endpoint}: {body[:500]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error on {endpoint}: {e.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"Non-JSON reply on {endpoint} (first 300 chars): {raw[:300]}")


def as_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []


def section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


def main():
    key = get_key()

    # ---- Step 1: confirm golf's sportId ----
    section("STEP 1 -- GET /v4/sports (confirming golf sportId, already known: 67)")
    sports = as_list(fetch("/v4/sports", key))
    golf_matches = [s for s in sports if "golf" in json.dumps(s).lower() or "pga" in json.dumps(s).lower()]
    print(f"Total sports returned: {len(sports)}  |  golf matches: {golf_matches}")
    if not golf_matches:
        print("\nNo golf match found this time -- stopping here.")
        return
    golf_sport_id = golf_matches[0].get("sportId")

    # ---- Step 2: confirm "prizepicks" is a real bookmaker key ----
    section("STEP 2 -- GET /v4/bookmakers (confirming PrizePicks key, already known: real)")
    bookmakers = as_list(fetch("/v4/bookmakers", key))
    pp_matches = [b for b in bookmakers if "priz" in json.dumps(b).lower()]
    print(f"Total bookmakers returned: {len(bookmakers)}  |  PrizePicks match: {pp_matches}")

    # ---- Step 3: find ONLY this event's tournament(s) -- compact, one line each ----
    section(f"STEP 3 -- GET /v4/tournaments?sportId={golf_sport_id}, filtered to '{EVENT_KEYWORD}'")
    all_tournaments = as_list(fetch("/v4/tournaments", key, sportId=golf_sport_id))
    kw = EVENT_KEYWORD.lower()
    matches = [t for t in all_tournaments
               if kw in (t.get("tournamentSlug") or "").lower()
               or kw in (t.get("categorySlug") or "").lower()]
    print(f"Total golf tournaments in catalog: {len(all_tournaments)}  |  matches for '{EVENT_KEYWORD}': {len(matches)}")
    for t in matches:
        print(f"  id={t.get('tournamentId'):<8} slug={t.get('tournamentSlug'):<35} name={t.get('tournamentName')!r:<45} category={t.get('categorySlug')}")
    if not matches:
        print(f"\nNo match for '{EVENT_KEYWORD}' -- update EVENT_KEYWORD at the top of this script and re-run.")
        return
    main_match = next((t for t in matches if "round" not in (t.get("tournamentName") or "").lower()), matches[0])
    target_id = main_match.get("tournamentId")
    print(f"\nUsing tournamentId={target_id} ({main_match.get('tournamentName')}) for step 5.")

    # ---- Step 4: see every real golf market -- compact, one line each ----
    section(f"STEP 4 -- GET /v4/markets?sportId={golf_sport_id}")
    markets = as_list(fetch("/v4/markets", key, sportId=golf_sport_id))
    print(f"Total golf markets returned: {len(markets)}")
    print("\nCompact list (marketId | playerProp | marketType | period | handicap | marketName):")
    for m in markets:
        print(f"  {m.get('marketId'):<8} prop={str(m.get('playerProp')):<5} type={m.get('marketType','')!s:<12} "
              f"period={m.get('period','')!s:<10} handicap={m.get('handicap')!s:<6} name={m.get('marketName')}")
    prop_markets = [m for m in markets if m.get("playerProp")]
    section(f"STEP 4b -- Full detail for the {len(prop_markets)} playerProp=true markets")
    print(json.dumps(prop_markets, indent=1)[:8000])

    # ---- Step 5: pull real PrizePicks odds for the matched tournament ----
    section(f"STEP 5 -- GET /v4/odds-by-tournaments?bookmaker=prizepicks&tournamentIds={target_id}&oddsFormat=american")
    odds = fetch("/v4/odds-by-tournaments", key, bookmaker="prizepicks",
                 tournamentIds=target_id, oddsFormat="american")
    dumped = json.dumps(odds, indent=1)
    print(dumped[:8000])
    if len(dumped) > 8000:
        print(f"\n(...truncated -- full response was {len(dumped)} chars. Paste what printed above, that's enough to see the shape.)")


if __name__ == "__main__":
    main()
