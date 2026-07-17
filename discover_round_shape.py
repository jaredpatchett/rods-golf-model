#!/usr/bin/env python3
"""
Path B, step 2: inspect the actual round-level row shape for The Open
(event_id=100, confirmed from event-list) in both an SG-available year
(2025, Portrush) and a pre-SG year (2017, Birkdale itself) — to see whether
plain round scores exist further back than the SG category data does, and to
see the real field names before building the fitting script.
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://feeds.datagolf.com"
EVENT_ID = 100  # The Open Championship, confirmed via event-list


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


def inspect_year(key, year, label):
    print(f"\n{'='*60}\n{label} (year={year})\n{'='*60}")
    payload = fetch("/historical-raw-data/rounds", key, tour="pga", event_id=EVENT_ID, year=year)
    rows = as_rows(payload)
    print(f"Row count: {len(rows)}")
    if not rows:
        print("(empty — nothing usable for this year)")
        return
    print("First row, all fields:")
    print(json.dumps(rows[0], indent=1))
    all_keys = set()
    for r in rows[:20]:
        all_keys.update(r.keys())
    print(f"\nAll keys seen across first 20 rows: {sorted(all_keys)}")


def main():
    key = get_key()
    inspect_year(key, 2025, "SG-available year — Royal Portrush")
    inspect_year(key, 2017, "Pre-SG year — Royal Birkdale itself")


if __name__ == "__main__":
    main()
