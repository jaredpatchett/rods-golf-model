#!/usr/bin/env python3
"""
Debug tool round 2: as_rows() grabbed 'books_offering' (a flat list of
sportsbook name strings) instead of the real player data, because 'odds'
apparently isn't a simple list — as_rows()'s generic "first list value found"
fallback picked the wrong key. This inspects payload['odds'] directly,
whatever shape it actually is, to find the real structure.
"""
import json
import rods_pipeline as p

key = p.get_key()

payload = p.fetch(p.EP["outrights"], key, tour="pga", market="win", odds_format="american")
print("Top-level keys:", list(payload.keys()))
print("books_offering:", payload.get("books_offering"))

odds = payload.get("odds")
print(f"\ntype(payload['odds']) = {type(odds)}")

if isinstance(odds, dict):
    print(f"odds is a DICT with {len(odds)} keys")
    print("First 5 keys:", list(odds.keys())[:5])
    first_key = next(iter(odds))
    print(f"\nFull entry for '{first_key}':")
    print(json.dumps(odds[first_key], indent=1))
elif isinstance(odds, list):
    print(f"odds is a LIST with {len(odds)} entries")
    print("\nFirst entry:")
    print(json.dumps(odds[0], indent=1))
else:
    print("odds is neither dict nor list:", odds)
