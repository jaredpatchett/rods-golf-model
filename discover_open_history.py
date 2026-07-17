#!/usr/bin/env python3
"""
Path B, step 1: find the real event_ids for Royal Birkdale and the similar-
course cluster (Troon, Portrush, Liverpool/Hoylake, St Andrews, Carnoustie)
before pulling any round-level history.

DataGolf's historical-raw-data endpoints need an event_id + year per
tournament (confirmed via their docs: /historical-raw-data/rounds?tour=X&
event_id=Y&year=Z). The Open Championship is a major, so per DataGolf's docs
majors are queryable back to 1983 — but I don't know the exact event_id or
which tour code ("pga" vs a major-specific code) The Open is filed under from
here, since I can't reach the live API myself. This script finds out.

Usage:
    export DG_KEY="..."
    python3 discover_open_history.py
    # or, if it comes back empty on tour=pga:
    python3 discover_open_history.py --tour euro
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://feeds.datagolf.com"

# The courses in the links cluster (course_fit_spec.docx §1) — matched against
# event_name / course_name substrings in the event-list response. Adjust these
# if DataGolf's naming differs from what's printed (e.g. "Hoylake" vs
# "Royal Liverpool") — the script prints the raw names either way.
CLUSTER_MATCH = [
    "birkdale", "troon", "portrush", "liverpool", "hoylake",
    "st andrews", "carnoustie", "open championship",
]


def get_key():
    key = os.environ.get("DG_KEY")
    if not key:
        sys.exit('ERROR: set your key first ->  export DG_KEY="your_datagolf_key"')
    return key


def fetch(endpoint, key, **params):
    params.setdefault("file_format", "json")
    params["key"] = key
    url = f"{BASE}{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise SystemExit(f"HTTP {e.code} on {endpoint}: {body[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error on {endpoint}: {e.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"Non-JSON reply on {endpoint} (first 200 chars): {raw[:200]}")


def as_rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour", default="pga", help="pga | euro — try euro if pga comes back empty for The Open")
    args = ap.parse_args()
    key = get_key()

    print(f"Pulling event-list for tour={args.tour} ...")
    payload = fetch("/historical-raw-data/event-list", key, tour=args.tour)
    rows = as_rows(payload)
    print(f"Got {len(rows)} total events on this tour.\n")

    if rows:
        print("--- first raw row, so we can see the actual field names ---")
        print(json.dumps(rows[0], indent=1))
        print()

    print(f"--- events matching the links cluster ({', '.join(CLUSTER_MATCH)}) ---")
    matches = []
    for r in rows:
        # check every string value in the row for a cluster keyword, since I don't
        # know for certain which field holds the course/event name until we see it
        blob = " ".join(str(v) for v in r.values() if isinstance(v, (str, int))).lower()
        if any(kw in blob for kw in CLUSTER_MATCH):
            matches.append(r)

    if not matches:
        print("No matches found. Either try --tour euro, or the field names in the raw "
              "row above differ from what CLUSTER_MATCH is checking — paste that raw row "
              "back and I'll fix the matching.")
    else:
        for m in matches:
            print(json.dumps(m))
    print(f"\n{len(matches)} matching events found.")


if __name__ == "__main__":
    main()
