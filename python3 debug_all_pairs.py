#!/usr/bin/env python3
"""
Rod flagged real fabricated-looking matchups: pairings like "Tommy Fleetwood
vs Scottie Scheffler" that don't correspond to any real DraftKings tee-time
group (real DK pairings that day: Fleetwood/Rahm and Scheffler/Molinari, as
two SEPARATE matchups). Pattern spotted: every wrong-looking pairing was
priced from a non-DraftKings book (betcris/bet365/datagolf), while every
pairing matching Rod's real DK list was priced from DraftKings itself.

This prints every single (p1, p2, books_available) triple so we can check
that pattern against the ground truth directly, rather than filtering
anything based on a guess.
"""
import json
import rods_pipeline as p

key = p.get_key()
payload = p.fetch(p.EP["matchups"], key, tour="pga", market="round_matchups", odds_format="american")
rows = p.as_rows(payload)
print(f"Total raw rows: {len(rows)}\n")

for r in rows:
    p1 = r.get("p1_player_name", "?")
    p2 = r.get("p2_player_name", "?")
    books = list(r.get("odds", {}).keys())
    ties = r.get("ties", "?")
    has_dk = "draftkings" in books
    print(f"{p1:30s} vs {p2:30s} | ties={ties:22s} | DK={'YES' if has_dk else 'no '} | books={books}")
