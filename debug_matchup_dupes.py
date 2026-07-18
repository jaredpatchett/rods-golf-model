#!/usr/bin/env python3
"""
Debug tool: checks whether DataGolf's round_matchups feed is genuinely
returning the same (p1, p2) pairing as multiple separate list entries
(possibly one per sportsbook, rather than one entry with all books nested
under 'odds' the way it worked for R1) — which would explain the duplicate
rows Rod is seeing on the live page, each with a different single-book price.
"""
import json
from collections import defaultdict
import rods_pipeline as p

key = p.get_key()
payload = p.fetch(p.EP["matchups"], key, tour="pga", market="round_matchups", odds_format="american")
rows = p.as_rows(payload)
print(f"Total raw rows: {len(rows)}")

# group by (p1, p2) as DataGolf names them, to see if any pair shows up more than once
groups = defaultdict(list)
for r in rows:
    p1 = r.get("p1_player_name", "?")
    p2 = r.get("p2_player_name", "?")
    groups[(p1, p2)].append(r)

dupes = {k: v for k, v in groups.items() if len(v) > 1}
print(f"Distinct (p1,p2) pairs: {len(groups)}")
print(f"Pairs appearing more than once: {len(dupes)}")

if dupes:
    print("\n--- First duplicate pair, full raw entries side by side ---")
    (p1, p2), entries = next(iter(dupes.items()))
    print(f"Pair: {p1} vs {p2} — appears {len(entries)} times")
    for i, e in enumerate(entries):
        print(f"\nEntry {i+1}:")
        print(json.dumps(e, indent=1))
else:
    print("\nNo duplicates found in the raw feed — if the live page is still showing "
          "duplicates, the bug is in our own parsing, not DataGolf's data.")
