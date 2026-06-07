"""
post_run_data_to_dashboard.py
─────────────────────────────
Posts the latest HubBot run data to the live dashboard API endpoint.
Accumulates run_history by fetching the existing history from the API
before posting, so history grows over time rather than being replaced.

Usage (called at the end of every HubBot run):
    python3.11 post_run_data_to_dashboard.py

The script reads run-data.json from the ledger directory, then POSTs it
to the dashboard's /api/run-data endpoint using the HUBBOT_API_KEY.

Environment variables:
    HUBBOT_API_KEY  — secret key for the dashboard POST endpoint
                      (already set in the Manus project secrets)

Dashboard endpoint:
    POST https://hubbot.virtapreneur.com/api/run-data
    Header: X-HubBot-Api-Key: <HUBBOT_API_KEY>
    Body:   application/json — the full run data payload
"""

import json
import os
import sys
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_URL = "https://hubbot.virtapreneur.com/api/run-data"
API_KEY = os.environ.get("HUBBOT_API_KEY", "11cbad293c71652b95502766eca9c5ef")
LEDGER_DIR = Path(__file__).parent
MAX_HISTORY = 30  # Keep at most 30 entries in run_history

# ── Known ledger directories (searched in order) ──────────────────────────────
# Each HubBot run may write its ledger to a different directory depending on
# how it was bootstrapped. We search all known locations so the script works
# regardless of which sandbox or bootstrap path was used.
LEDGER_SEARCH_DIRS = [
    Path("/home/ubuntu/hubactually_hubbot_run_ledger"),  # primary ledger dir
    Path("/home/ubuntu/hubbot-dashboard/hubbot_runtime"),  # fallback: repo-relative
    Path("/home/ubuntu/hubbot_run_ledger"),  # alternate name used by some runs
    LEDGER_DIR,  # script's own directory
]


# ── Find the latest run data file ─────────────────────────────────────────────
def load_run_data() -> dict:
    """Load run data — search all known ledger directories."""
    candidates = []
    for ledger_dir in LEDGER_SEARCH_DIRS:
        candidates += [
            ledger_dir / "run-data.json",
            ledger_dir / "latest-run.json",
        ]
    # Also check the legacy public path
    candidates.append(Path("/home/ubuntu/hubbot-dashboard/client/public/latest-run.json"))
    for path in candidates:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            print(f"[dashboard] Loaded run data from {path}")
            return data
    raise FileNotFoundError("No run data file found in ledger directory.")


# ── Fetch existing run_history from live dashboard ────────────────────────────
def fetch_existing_history() -> list:
    """GET the current run_history array from the live dashboard API."""
    try:
        resp = requests.get(DASHBOARD_URL, timeout=10)
        if resp.status_code == 200:
            existing = resp.json()
            history = existing.get("run_history", [])
            print(f"[dashboard] Fetched {len(history)} existing history entries from live API")
            return history
        else:
            print(f"[dashboard] Could not fetch existing history: HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"[dashboard] Could not fetch existing history: {e}")
        return []


# ── Build merged run_history ──────────────────────────────────────────────────
def build_merged_history(new_data: dict, existing_history: list) -> list:
    """
    Build a merged run_history list:
    - Prepend today's entry (from new_data) to the existing history
    - Deduplicate by run_date (keep the newest entry for each date)
    - Trim to MAX_HISTORY entries
    """
    # Build the new entry from the current run data
    new_entry = {
        "run_date": new_data.get("run_date", "unknown"),
        "status": new_data.get("status", "unknown"),
        "primary_result": new_data.get("primary_result", ""),
        "posts_published": new_data.get("metrics", {}).get("posts_published", 0),
        "tasks_completed": new_data.get("metrics", {}).get("required_tasks_completed", 0),
        "tasks_failed": new_data.get("metrics", {}).get("required_tasks_failed", 0),
    }

    # Also include any run_history already in the new_data file (from this run)
    local_history = new_data.get("run_history", [])

    # Merge: new entry first, then local history, then existing API history
    combined = [new_entry] + local_history + existing_history

    # Deduplicate by run_date — keep first occurrence (newest)
    seen_dates = set()
    deduped = []
    for entry in combined:
        date = entry.get("run_date", "")
        if date and date not in seen_dates:
            seen_dates.add(date)
            deduped.append(entry)

    # Trim to max
    merged = deduped[:MAX_HISTORY]
    print(f"[dashboard] Merged history: {len(merged)} entries (max {MAX_HISTORY})")
    return merged


# ── Post to dashboard ─────────────────────────────────────────────────────────
def post_to_dashboard(data: dict) -> bool:
    """POST run data to the dashboard API. Returns True on success."""
    headers = {
        "Content-Type": "application/json",
        "X-HubBot-Api-Key": API_KEY,
    }
    try:
        resp = requests.post(DASHBOARD_URL, json=data, headers=headers, timeout=15)
        if resp.status_code == 200:
            result = resp.json()
            print(f"[dashboard] ✓ Dashboard updated at {result.get('updated_at', 'unknown')}")
            return True
        else:
            print(f"[dashboard] ✗ POST failed: HTTP {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"[dashboard] ✗ POST error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        # 1. Load the current run data
        data = load_run_data()

        # 2. Fetch existing run_history from the live dashboard
        existing_history = fetch_existing_history()

        # 3. Merge and update run_history in the payload
        data["run_history"] = build_merged_history(data, existing_history)

        # 4. POST the merged payload to the dashboard
        success = post_to_dashboard(data)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[dashboard] Fatal error: {e}")
        sys.exit(1)
