#!/usr/bin/env python3
"""
Debug tool: prints DataGolf's RAW matchups response so we can see whether the
market just isn't posted yet, or the field names differ from what pick() expects.
"""
import os
import json
import rods_pipeline as p

key = p.get_key()
print("--- trying market=tournament_matchups ---")
try:
    r = p.fetch(p.EP["matchups"], key, tour="pga", market="tournament_matchups", odds_format="american")
    print(json.dumps(r, indent=1)[:3000])
except SystemExit as e:
    print("FAILED:", e)

print("\n--- trying market=round_matchups ---")
try:
    r2 = p.fetch(p.EP["matchups"], key, tour="pga", market="round_matchups", odds_format="american")
    print(json.dumps(r2, indent=1)[:3000])
except SystemExit as e:
    print("FAILED:", e)

print("\n--- trying with no market param at all ---")
try:
    r3 = p.fetch(p.EP["matchups"], key, tour="pga", odds_format="american")
    print(json.dumps(r3, indent=1)[:3000])
except SystemExit as e:
    print("FAILED:", e)
