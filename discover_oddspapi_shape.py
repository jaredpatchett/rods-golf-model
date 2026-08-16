#!/usr/bin/env python3
"""
Rod's Golf Model -- OddsPapi discovery script
==============================================
Path C, step 1: OddsPapi (oddspapi.io) claims coverage of PrizePicks odds
alongside 300+ other bookmakers, including player props. This script does
NOT assume anything about golf's sportId, market IDs, or PrizePicks' exact
bookmaker key in their system -- every one of those needs to be confirmed
live before any of it gets wired into rods_pipeline.py.

CONFIRMED from real runs so far:
  - Golf sportId = 67
  - "prizepicks" is a real, valid bookmaker key (351 total bookmakers)
  - /v4/tournaments?sportId=67 returns 1300+ rows, the entire historical
    catalog -- filtering by keyword is required.
  - TWO rounds of "print less per entry" (full JSON -> one-line-per-entry)
    both still blew past 10k lines. That means the guess-and-shrink approach
    was wrong -- something is returning a payload far bigger than a golf
    market/tournament catalog should reasonably be, and guessing which one
    a third time isn't a real fix.

What changed this round -- a hard cap instead of another guess:
  1. Every fetch() call now prints its RAW response size (bytes + line count)
     the instant it comes back, before any processing. This is not capped,
     and there are only 5 fetch calls total, so this alone is at most 5 lines
     and will tell us definitively which endpoint is actually huge.
  2. A global output budget (400 lines) wraps every other print in this
     script. Once hit, it stops printing further detail and says so --
     it CANNOT blow past the budget regardless of what any endpoint
     returns, full stop.
  3. Every list-printing loop is hard-capped at 25 entries with a
     "+N more not shown" note, regardless of the list's real length.

Run this, paste the FULL output (it will now be well under a thousand
lines no matter what), and the real integration gets built from there.
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://api.oddspapi.io"
EVENT_KEYWORD = "fedex-st-jude"  # update each week
MAX_LINES = 400
MAX_LIST_ENTRIES = 25

_line_count = [0]
_budget_hit = [False]


def out(*args, **kwargs):
    """Print, but stop once the global line budget is spent. Unlike a plain
    print(), this cannot be individually forgotten in some new section added
    later -- every printed line in this script (except the raw-size lines,
    which are separately unbounded and always show) goes through this."""
    if _line_count[0] >= MAX_LINES:
        if not _budget_hit[0]:
            print(f"\n[[ OUTPUT BUDGET HIT: {MAX_LINES} lines. Suppressing further detail. "
                  f"Check the '[raw]' size lines above -- whichever endpoint has the "
                  f"biggest byte count is the one actually driving the output size. ]]")
            _budget_hit[0] = True
        return
    print(*args, **kwargs)
    _line_count[0] += 1


def get_key():
    key = os.environ.get("ODDSPAPI_KEY")
    if not key:
        sys.exit('ERROR: set your key first ->  export ODDSPAPI_KEY="your_oddspapi_key"')
    return key


def fetch(endpoint, key, **params):
    params["apiKey"] = key
    url = f"{BASE}{endpoint}?{urllib.parse.urlencode(params)}"
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
    # Always printed, never suppressed by the budget -- this is the diagnostic
    # that actually answers "which endpoint is huge", independent of anything
    # downstream doing with the data.
    print(f"[raw] {endpoint} ({params}) -> {len(raw)} bytes, {raw.count(chr(10)) + 1} lines of raw JSON")
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


def print_capped(items, formatter):
    for item in items[:MAX_LIST_ENTRIES]:
        out(formatter(item))
    if len(items) > MAX_LIST_ENTRIES:
        out(f"  ... +{len(items) - MAX_LIST_ENTRIES} more not shown (raise MAX_LIST_ENTRIES if needed)")


def section(title):
    out(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main():
    key = get_key()

    section("STEP 1 -- GET /v4/sports")
    sports = as_list(fetch("/v4/sports", key))
    golf_matches = [s for s in sports if "golf" in json.dumps(s).lower() or "pga" in json.dumps(s).lower()]
    out(f"Total sports: {len(sports)}  |  golf matches: {golf_matches}")
    if not golf_matches:
        out("No golf match -- stopping.")
        return
    golf_sport_id = golf_matches[0].get("sportId")

    section("STEP 2 -- GET /v4/bookmakers")
    bookmakers = as_list(fetch("/v4/bookmakers", key))
    pp_matches = [b for b in bookmakers if "priz" in json.dumps(b).lower()]
    out(f"Total bookmakers: {len(bookmakers)}  |  PrizePicks match: {pp_matches}")

    section(f"STEP 3 -- GET /v4/tournaments?sportId={golf_sport_id}, filtered to '{EVENT_KEYWORD}'")
    all_tournaments = as_list(fetch("/v4/tournaments", key, sportId=golf_sport_id))
    kw = EVENT_KEYWORD.lower()
    matches = [t for t in all_tournaments
               if kw in (t.get("tournamentSlug") or "").lower()
               or kw in (t.get("categorySlug") or "").lower()]
    out(f"Total tournaments in catalog: {len(all_tournaments)}  |  matches: {len(matches)}")
    print_capped(matches, lambda t: f"  id={t.get('tournamentId')} slug={t.get('tournamentSlug')} name={t.get('tournamentName')!r}")
    if not matches:
        out(f"No match for '{EVENT_KEYWORD}' -- update EVENT_KEYWORD and re-run.")
        return
    main_match = next((t for t in matches if "round" not in (t.get("tournamentName") or "").lower()), matches[0])
    target_id = main_match.get("tournamentId")
    out(f"Using tournamentId={target_id} ({main_match.get('tournamentName')}) for step 5.")

    section(f"STEP 4 -- GET /v4/markets?sportId={golf_sport_id}")
    markets = as_list(fetch("/v4/markets", key, sportId=golf_sport_id))
    out(f"Total markets: {len(markets)}")
    print_capped(markets, lambda m: f"  {m.get('marketId')} prop={m.get('playerProp')} type={m.get('marketType')} "
                                     f"handicap={m.get('handicap')} name={m.get('marketName')}")
    prop_markets = [m for m in markets if m.get("playerProp")]
    section(f"STEP 4b -- {len(prop_markets)} playerProp=true markets, full detail")
    print_capped(prop_markets, lambda m: json.dumps(m))

    section(f"STEP 5 -- GET /v4/odds-by-tournaments?bookmaker=prizepicks&tournamentIds={target_id}")
    odds = fetch("/v4/odds-by-tournaments", key, bookmaker="prizepicks",
                 tournamentIds=target_id, oddsFormat="american")
    odds_list = as_list(odds) if isinstance(odds, (list, dict)) else []
    out(f"Fixtures returned for this tournament: {len(odds_list) if odds_list else 'N/A (see raw size above)'}")
    dumped = json.dumps(odds, indent=1)
    # Print in a bounded number of chunks so it counts against the same line
    # budget as everything else, rather than dumping thousands of lines raw.
    for line in dumped.splitlines()[:MAX_LIST_ENTRIES * 4]:
        out(line)
    total_lines = len(dumped.splitlines())
    if total_lines > MAX_LIST_ENTRIES * 4:
        out(f"  ... +{total_lines - MAX_LIST_ENTRIES * 4} more lines not shown "
            f"(full payload was {len(dumped)} chars / {total_lines} lines -- the [raw] size line above has the real total)")


if __name__ == "__main__":
    main()
