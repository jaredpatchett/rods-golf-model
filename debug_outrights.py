#!/usr/bin/env python3
"""
Debug tool: prints the RAW outrights response for the win market so we can
see whether market prices are genuinely sparse (sportsbooks often only post
outright odds for the top 40-60 contenders in a 156-man field, not everyone)
or whether the parsing in build_outrights_market() is missing real data due
to a field-name mismatch — same category of issue as the matchups fix
earlier, never actually verified live for this endpoint until now.
"""
import json
import rods_pipeline as p

key = p.get_key()

print("=== outrights: win market, raw payload ===")
payload = p.fetch(p.EP["outrights"], key, tour="pga", market="win", odds_format="american")
print(f"Top-level keys: {list(payload.keys()) if isinstance(payload, dict) else 'not a dict'}")

rows = p.as_rows(payload)
print(f"Row count (players with any entry in this market): {len(rows)}")

if rows:
    print("\nFirst 3 raw rows:")
    for r in rows[:3]:
        print(json.dumps(r, indent=1))

# run it through the actual parser to see what comes out the other end
market = p.build_outrights_market(payload)
priced = {k: v for k, v in market.items() if v.get("market") is not None}
print(f"\nAfter parsing: {len(market)} names extracted, {len(priced)} with a usable market price")
if len(market) > 0 and len(priced) == 0:
    print("!! Names extracted but NO prices parsed — that's a parsing bug, not a sparse market.")
elif len(rows) > 0 and len(market) == 0:
    print("!! Raw rows exist but ZERO names extracted — player_name field guess is wrong.")
else:
    print("Parsing looks consistent with the raw row count — likely a genuinely sparse market.")
