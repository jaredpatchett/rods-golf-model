#!/usr/bin/env python3
"""
The dedup/fabricated-pairing filter (build_matchups, the "must appear under
BOTH ties=separate AND ties=void" rule) was built and tested against
round_matchups' real data shape. This run pulled tournament_matchups instead
(140 raw rows -> only 12 survived the filter, a 91% drop) — worth checking
whether that filter's assumption actually holds for this different market,
or whether it's incorrectly discarding real matchups.
"""
import json
from collections import defaultdict
import rods_pipeline as p

key = p.get_key()
payload = p.fetch(p.EP["matchups"], key, tour="pga", market="tournament_matchups", odds_format="american")
rows = p.as_rows(payload)
print(f"Total raw rows: {len(rows)}")

groups = defaultdict(list)
for r in rows:
    p1 = r.get("p1_player_name", "?")
    p2 = r.get("p2_player_name", "?")
    groups[(p1, p2)].append(r)

tie_type_counts = defaultdict(int)
for entries in groups.values():
    tie_types = tuple(sorted({e.get("ties") for e in entries}))
    tie_type_counts[tie_types] += 1

print(f"\nDistinct pairs: {len(groups)}")
print("Breakdown by which tie-structure(s) each pair has:")
for tie_types, count in sorted(tie_type_counts.items(), key=lambda x: -x[1]):
    print(f"  {tie_types}: {count} pairs")

print("\n--- Sample: first pair that has ONLY 'void' (no 'separate' sibling) ---")
for (p1, p2), entries in groups.items():
    tie_types = {e.get("ties") for e in entries}
    if tie_types == {"void"}:
        print(f"Pair: {p1} vs {p2}")
        print(json.dumps(entries[0], indent=1))
        break
else:
    print("(none found — every pair has a 'separate' sibling)")
