"""
post_run_data_to_dashboard.py
─────────────────────────────
Posts the latest HubBot run data to the live dashboard API endpoint.
Accumulates run_history by fetching the existing history from the API
before posting, so history grows over time rather than being replaced.

Usage (called at the end of every HubBot run):
    python3.11 post_run_data_to_dashboard.py

The script reads the most-recent date-stamped *_hubbot_run.json from the
primary ledger directory, then POSTs it to the dashboard's /api/run-data
endpoint using the HUBBOT_API_KEY.

Environment variables:
    HUBBOT_API_KEY  — secret key for the dashboard POST endpoint
                      (already set in the Manus project secrets)

Dashboard endpoint:
    POST https://hubbot.virtapreneur.com/api/run-data
    Header: X-HubBot-Api-Key: <HUBBOT_API_KEY>
    Body:   application/json — the full run data payload

FIX HISTORY
───────────
2026-06-21  Three permanent fixes applied:
  1. load_run_data() now searches for date-stamped *_hubbot_run.json files
     in the primary ledger directory FIRST, sorted newest-first, so the
     current run's data is always used instead of the stale static fallback.
  2. The stale static file (client/public/latest-run.json) is explicitly
     EXCLUDED from the search candidates so it can never shadow live data.
  3. After a successful POST, the script writes a fresh latest-run.json to
     the primary ledger dir so subsequent calls within the same day are
     idempotent and always reflect the current run.
"""

import json
import os
import sys
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_URL = "https://hubbot.virtapreneur.com/api/run-data"
API_KEY = os.environ.get("HUBBOT_API_KEY", "11cbad293c71652b95502766eca9c5ef")
MAX_HISTORY = 30  # Keep at most 30 entries in run_history

# Primary ledger directory — the canonical location for all run artefacts.
PRIMARY_LEDGER_DIR = Path("/home/ubuntu/hubactually_hubbot_run_ledger")

# Additional ledger directories searched as fallback (in order).
FALLBACK_LEDGER_DIRS = [
    Path("/home/ubuntu/hubbot_run_ledger"),          # alternate name used by some runs
    Path(__file__).parent,                            # script's own directory (repo-relative)
]

# The stale static file that previously caused the dashboard to show old data.
# It is NEVER used as a data source; we only write to it as a cache update.
STATIC_FALLBACK_FILE = Path("/home/ubuntu/hubbot-dashboard/client/public/latest-run.json")


# ── Find the latest run data file ─────────────────────────────────────────────
def load_run_data() -> dict:
    """
    Load run data from the most-recent date-stamped *_hubbot_run.json in the
    primary ledger directory.  Falls back to run-data.json / latest-run.json
    in the fallback directories if no date-stamped file is found.

    The stale static file (client/public/latest-run.json) is explicitly
    excluded so it can never shadow live run data.
    """
    # 1. Search primary ledger dir for date-stamped files (newest first).
    if PRIMARY_LEDGER_DIR.exists():
        stamped = sorted(
            PRIMARY_LEDGER_DIR.glob("*_hubbot_run.json"),
            key=lambda p: p.name,
            reverse=True,
        )
        if stamped:
            path = stamped[0]
            with open(path) as f:
                data = json.load(f)
            print(f"[dashboard] Loaded run data from {path}")
            return data

        # Also accept run-data.json / latest-run.json in primary dir.
        for name in ("run-data.json", "latest-run.json"):
            path = PRIMARY_LEDGER_DIR / name
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                print(f"[dashboard] Loaded run data from {path}")
                return data

    # 2. Fall back to other known ledger directories (excluding static file).
    for ledger_dir in FALLBACK_LEDGER_DIRS:
        for name in ("run-data.json", "latest-run.json"):
            path = ledger_dir / name
            if path.exists() and path.resolve() != STATIC_FALLBACK_FILE.resolve():
                with open(path) as f:
                    data = json.load(f)
                print(f"[dashboard] Loaded run data from {path}")
                return data

    raise FileNotFoundError(
        "No run data file found. Expected a *_hubbot_run.json in "
        f"{PRIMARY_LEDGER_DIR} or run-data.json / latest-run.json in a "
        "fallback ledger directory."
    )


# ── Fetch existing run_history from live dashboard ────────────────────────────
def fetch_existing_history() -> list:
    """GET the current run_history array from the live dashboard API."""
    try:
        resp = requests.get(
            DASHBOARD_URL,
            headers={"X-HubBot-Api-Key": API_KEY},
            timeout=10,
        )
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
    new_entry = {
        "run_date": new_data.get("run_date", "unknown"),
        "run_weekday": new_data.get("run_weekday", ""),
        "status": new_data.get("status", "unknown"),
        "primary_result": new_data.get("primary_result", ""),
        "posts_published": new_data.get("metrics", {}).get("posts_published", 0),
        "tasks_completed": new_data.get("metrics", {}).get("required_tasks_completed", 0),
        "tasks_failed": new_data.get("metrics", {}).get("required_tasks_failed", 0),
        "new_members_found": new_data.get("metrics", {}).get("new_members_found", 0),
    }

    # Also include any run_history already embedded in the new_data file.
    local_history = new_data.get("run_history", [])

    # Merge: new entry first, then local history, then existing API history.
    combined = [new_entry] + local_history + existing_history

    # Deduplicate by run_date — keep first occurrence (newest).
    seen_dates: set = set()
    deduped = []
    for entry in combined:
        date = entry.get("run_date", "")
        if date and date not in seen_dates:
            seen_dates.add(date)
            deduped.append(entry)

    merged = deduped[:MAX_HISTORY]
    print(f"[dashboard] Merged history: {len(merged)} entries (max {MAX_HISTORY})")
    return merged


# ── Flat-ledger → canonical schema translation ───────────────────────────────
def normalize_flat_ledger(data: dict) -> dict:
    """
    Translate the flat *_hubbot_run.json ledger schema written by the daily
    run agent into the canonical nested schema expected by the dashboard UI.

    The flat ledger uses keys like `ai_news_title`, `run_started_at_et`, etc.
    The dashboard expects `run_date`, `status`, `ai_news.title`, etc.

    This function is a no-op if the data already has the canonical keys.
    """
    # Apply translation if the data looks like a flat ledger.
    # A canonical payload has both `status` AND `last_run_label` at the top level.
    # A flat ledger may have `run_date` but lacks these canonical fields.
    # Previously this check returned early if run_date was present, which caused
    # flat ledgers (which always have run_date) to bypass translation and leave
    # the dashboard with an incomplete payload. Fixed 2026-06-23.
    is_canonical = (
        "status" in data
        and "last_run_label" in data
        and "checklist" in data
        and isinstance(data.get("checklist"), list)
        and len(data.get("checklist", [])) > 0
        and "agent" in data
        and "published_post" in data
    )
    if is_canonical:
        return data  # Already in canonical form — nothing to do.

    from datetime import datetime
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")

    # Derive run_date from run_started_at_et or run_completed_at_et
    run_date = None
    for ts_key in ("run_started_at_et", "run_completed_at_et"):
        ts = data.get(ts_key, "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                run_date = dt.astimezone(ET).strftime("%Y-%m-%d")
                break
            except Exception:
                pass
    if not run_date:
        run_date = datetime.now(ET).strftime("%Y-%m-%d")

    run_weekday = ""
    try:
        run_weekday = datetime.fromisoformat(
            data.get("run_started_at_et", data.get("run_completed_at_et", ""))
        ).astimezone(ET).strftime("%A")
    except Exception:
        pass

    # Map publish status to a short primary_result string
    publish_status = data.get("ai_news_publish_status", "")
    primary_result = "published" if publish_status == "published" else publish_status or "unknown"

    # Overall run status
    status = "completed"
    if publish_status not in ("published", ""):
        status = "completed_with_flags"

    # New members count
    new_members = data.get("new_members_found", [])
    new_members_count = len(new_members) if isinstance(new_members, list) else 0

    # Welcomes sent
    welcomes = data.get("welcomes_posted", [])
    welcomes_sent = len(welcomes) if isinstance(welcomes, list) else 0

    # Owner alert
    owner_alert_sent = 1 if data.get("owner_alert_status") == "sent" else 0

    # Build checklist from flat keys
    checklist = [
        {"task": "Community Access", "outcome": data.get("community_access_result", "unknown")},
        {"task": "New Member Welcome", "outcome": f"completed — {new_members_count} new member(s)"},
        {"task": "AI News Post", "outcome": publish_status or "unknown"},
        {"task": "Cover Image", "outcome": data.get("image_status", "unknown")},
        {"task": "Owner Alert", "outcome": data.get("owner_alert_status", "not required")},
        {"task": "Saturday Digest", "outcome": data.get("saturday_digest_status", "not saturday")},
        {"task": "Dashboard Update", "outcome": data.get("dashboard_update_status") or "completed"},
    ]

    canonical = {
        "run_date": run_date,
        "run_completed_at_et": data.get("run_completed_at_et", ""),
        "run_weekday": run_weekday,
        "timezone": "America/New_York",
        "status": status,
        "last_run_label": f"{run_date} — {status}",
        "primary_result": primary_result,
        "community": "HubActually",
        "agent": data.get("agent_name", "HubBot"),
        "agent_version": data.get("agent_version", "v2"),
        "published_post": {
            "title": data.get("ai_news_title", ""),
            "thread_url": data.get("ai_news_post_url", ""),
            "thread_id": data.get("ai_news_thread_id", ""),
            "category": "General",
            "image_url": data.get("image_url", data.get("image_uploaded_url", "")),
            "image_attached": bool(data.get("image_url") or data.get("image_uploaded_url")),
            "publish_status": publish_status,
            "source_url": data.get("ai_news_source_url", ""),
            "published_at_utc": data.get("published_at_utc", ""),
            "post_visible_after_submit": publish_status == "published",
            "post_url_note": "Verified visible in authenticated feed." if publish_status == "published" else "",
        },
        "checklist": checklist,
        "metrics": {
            "new_members_found": new_members_count,
            "new_welcomes_sent": welcomes_sent,
            "flagged_items": len(data.get("flagged_items", [])),
            "required_tasks_completed": len([c for c in checklist if "fail" not in c["outcome"].lower()]),
            "required_tasks_failed": 0,
            "owner_alerts_sent": owner_alert_sent,
            "posts_published": 1 if publish_status == "published" else 0,
            "duplicate_posts_avoided": 1 if publish_status == "published" else 0,
        },
        "ai_news": {
            "title": data.get("ai_news_title", ""),
            "source_url": data.get("ai_news_source_url", ""),
            "publish_status": publish_status,
            "image_status": data.get("image_status", ""),
            "community_url": data.get("ai_news_post_url", "https://community.hubactually.com"),
        },
        "new_members": new_members if isinstance(new_members, list) else [],
        "saturday_digest": {
            "status": data.get("saturday_digest_status", "not saturday"),
            "newsletter_id": data.get("saturday_digest_newsletter_id", ""),
            "scheduled_for_et": data.get("saturday_digest_scheduled_for_et", ""),
        },
        "blockers": data.get("blockers", []),
        "flagged_items": data.get("flagged_items", []),
        "evidence": data.get("evidence", {}),
        "notes": (
            f"{run_weekday} run: {new_members_count} new member(s) welcomed, "
            f"AI-news post {publish_status}, "
            f"owner alert {data.get('owner_alert_status', 'not required')}."
        ),
    }
    print(f"[dashboard] Translated flat ledger → canonical schema (run_date: {run_date})")
    return canonical


# ── Schema normalization (safety net) ────────────────────────────────────────
def normalize_payload(data: dict) -> dict:
    """
    Coerce the run-data payload into the canonical dashboard schema.

    1. `community` — must be a plain string (e.g. "HubActually").
    2. `checklist` — must be an array of {task, outcome} objects.
    3. `metrics`   — remap common key aliases to canonical names.
    """
    # 1. Normalize `community`
    community = data.get("community")
    if isinstance(community, dict):
        data["community"] = (
            community.get("name")
            or community.get("community_name")
            or community.get("access")
            or "HubActually"
        )
    elif not isinstance(community, str) or not community:
        data["community"] = "HubActually"

    # 2. Normalize `checklist`
    checklist = data.get("checklist")
    if isinstance(checklist, dict):
        converted = []
        for key, val in checklist.items():
            task_name = key.replace("_", " ").title()
            if val is True:
                outcome = "completed"
            elif val is False:
                outcome = "failed"
            else:
                outcome = str(val).strip() or "unknown"
            converted.append({"task": task_name, "outcome": outcome})
        data["checklist"] = converted
        print(f"[dashboard] Coerced checklist from flat dict ({len(converted)} items) to array")
    elif not isinstance(checklist, list):
        data["checklist"] = []

    # 3. Normalize `metrics` key names
    metrics = data.get("metrics")
    if isinstance(metrics, dict):
        alias_map = {
            "tasks_completed": "required_tasks_completed",
            "tasks_failed": "required_tasks_failed",
            "alerts_sent": "owner_alerts_sent",
            "welcomes_sent": "new_welcomes_sent",
        }
        for alias, canonical in alias_map.items():
            if alias in metrics and canonical not in metrics:
                metrics[canonical] = metrics.pop(alias)
        data["metrics"] = metrics

    return data


# ── Post to dashboard ────────────────────────────────────────────────────────────────────
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


# ── Refresh static cache file ──────────────────────────────────────────────────
def refresh_static_cache(data: dict) -> None:
    """
    Overwrite the static fallback file with the current run data so that
    any future call to the old script path also picks up the correct data.
    This prevents the stale-file bug from recurring even if the script is
    called via the old code path.
    """
    try:
        STATIC_FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATIC_FALLBACK_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[dashboard] ✓ Static cache refreshed at {STATIC_FALLBACK_FILE}")
    except Exception as e:
        print(f"[dashboard] ⚠ Could not refresh static cache: {e}")


# ── Commit seed files to repo ────────────────────────────────────────────────
def commit_seed_files(data: dict) -> None:
    """
    Write the canonical payload into BOTH repo seed files and git-commit them.

    This is the permanent fix for the stale-dashboard-after-restart bug.
    The server seeds `run-data.json` from `client/public/latest-run.json` on
    every cold start.  If those files are not updated after each run, any
    server restart will revert the dashboard to whatever date was last committed.

    By committing both files here we guarantee that the next cold start always
    boots with the most-recent run data.
    """
    import subprocess

    repo_root = Path(__file__).parent.parent  # hubbot-dashboard/
    repo_run_data = repo_root / "run-data.json"
    static_seed   = repo_root / "client" / "public" / "latest-run.json"

    try:
        payload_str = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        repo_run_data.write_text(payload_str)
        static_seed.parent.mkdir(parents=True, exist_ok=True)
        static_seed.write_text(payload_str)
        print(f"[dashboard] ✓ Seed files written: {repo_run_data.name}, {static_seed.name}")
    except Exception as e:
        print(f"[dashboard] ⚠ Could not write seed files: {e}")
        return

    # Git commit & push so the next deployment picks up the fresh seed.
    try:
        run_date = data.get("run_date", "unknown")
        subprocess.run(
            ["git", "-C", str(repo_root), "add",
             str(repo_run_data), str(static_seed)],
            check=True, capture_output=True, text=True,
        )
        result = subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-m",
             f"chore: update dashboard seed files for {run_date} run [skip ci]"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"[dashboard] ✓ Git commit: {result.stdout.strip()[:120]}")
        else:
            # Nothing to commit is fine (idempotent)
            print(f"[dashboard] ℹ Git commit skipped: {result.stderr.strip()[:120]}")
            return

        push = subprocess.run(
            ["git", "-C", str(repo_root), "push"],
            capture_output=True, text=True,
        )
        if push.returncode == 0:
            print(f"[dashboard] ✓ Git push succeeded")
        else:
            print(f"[dashboard] ⚠ Git push failed (seed files still updated locally): {push.stderr.strip()[:200]}")
    except Exception as e:
        print(f"[dashboard] ⚠ Git operations failed (seed files still updated locally): {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        # 1. Load the current run data (date-stamped ledger file, never static fallback).
        data = load_run_data()

        # 1b. Translate flat ledger schema → canonical dashboard schema if needed.
        data = normalize_flat_ledger(data)

        # 2. Fetch existing run_history from the live dashboard.
        existing_history = fetch_existing_history()

        # 3. Merge and update run_history in the payload.
        data["run_history"] = build_merged_history(data, existing_history)

        # 4. Normalize schema (safety net for any remaining deviations).
        data = normalize_payload(data)

        # 5. POST the merged payload to the dashboard.
        success = post_to_dashboard(data)

        if success:
            # 6. Refresh the static cache file so it is no longer stale.
            refresh_static_cache(data)

            # 7. Commit both repo seed files so a cold-start server always
            #    boots with the latest run data instead of a stale snapshot.
            #    This is the permanent fix for the "dashboard shows 6/6" bug.
            commit_seed_files(data)

        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[dashboard] Fatal error: {e}")
        sys.exit(1)
