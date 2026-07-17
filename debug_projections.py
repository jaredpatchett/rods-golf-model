#!/usr/bin/env python3
"""
Debug tool: prints the RAW decomposition and pre-tournament responses so we
can see the actual field names DataGolf uses for SG components and projected
scores — these are coming back as None right now, meaning pick() is guessing
wrong names for this feed version.
"""
import json
import rods_pipeline as p

key = p.get_key()

print("=== player-decompositions: first 2 raw rows ===")
decomp = p.fetch(p.EP["decomp"], key, tour="pga")
rows = p.as_rows(decomp)
print(f"(top-level keys: {list(decomp.keys()) if isinstance(decomp, dict) else 'not a dict'})")
print(f"(row count: {len(rows)})")
for r in rows[:2]:
    print(json.dumps(r, indent=1))

print("\n=== pre-tournament predictions: first 2 raw rows ===")
pretourn = p.fetch(p.EP["pretourn"], key, tour="pga", odds_format="percent")
rows2 = p.as_rows(pretourn)
print(f"(top-level keys: {list(pretourn.keys()) if isinstance(pretourn, dict) else 'not a dict'})")
print(f"(row count: {len(rows2)})")
for r in rows2[:2]:
    print(json.dumps(r, indent=1))
