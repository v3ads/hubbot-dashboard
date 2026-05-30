#!/usr/bin/env python3
"""HubBot v2 permanent finalization helper.

This script converts a HubBot run ledger into dashboard-compatible JSON, writes
local durable evidence files, optionally posts to the dashboard API, and always
updates the dashboard repository fallback files when available.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
LEDGER_DIR = Path('/home/ubuntu/hubactually_hubbot_run_ledger')


def now_et() -> datetime:
    return datetime.now(ET)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def normalize_status(value: Any, default: str = 'unknown') -> str:
    if not value:
        return default
    return str(value).strip().lower().replace(' ', '_')


def checklist_item(task: str, outcome: str) -> dict[str, str]:
    return {'task': task, 'outcome': outcome}


def is_publish_success(status: str) -> bool:
    """Return True for all durable success variants used by recovery and scheduled runs."""
    return status == 'published' or status.startswith('published_')


def is_existing_duplicate_skip(status: str) -> bool:
    """Return True when the run correctly avoided a same-day duplicate post."""
    return status in {'skipped_existing_same_day_post', 'skipped_with_existing_same_day_post'}


def ledger_image_url(ledger: dict[str, Any]) -> str:
    """Resolve the best available community image URL without requiring one exact field name."""
    for key in ('image_url', 'image_uploaded_url', 'uploaded_image_url', 'ai_news_image_url'):
        value = ledger.get(key)
        if value:
            return str(value)
    evidence = ledger.get('evidence') or {}
    if isinstance(evidence, dict):
        for key in ('image_url', 'image_uploaded_url', 'uploaded_image_url', 'live_image_url'):
            value = evidence.get(key)
            if value:
                return str(value)
    return ''


def image_is_attached(ledger: dict[str, Any]) -> bool:
    status = normalize_status(ledger.get('image_status'))
    if status in {'uploaded', 'attached', 'uploaded_and_live', 'live_verified', 'corrected_live', 'published_live'}:
        return True
    return bool(ledger_image_url(ledger)) and status not in {'blocked', 'rejected_for_quality', 'text_only'}


def build_dashboard_payload(ledger: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    completed = ledger.get('run_completed_at_et') or now_et().isoformat(timespec='seconds')
    date = (ledger.get('run_date') or completed[:10])
    blockers = ledger.get('blockers') or []
    flagged = ledger.get('flagged_items') or []
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'blocked')
    publish_success = is_publish_success(publish_status)
    duplicate_skip = is_existing_duplicate_skip(publish_status)
    status = 'completed' if publish_success and not blockers else ('completed_with_flags' if publish_success or duplicate_skip else 'blocked_required_action')
    ai_title = ledger.get('ai_news_title') or 'Not published'
    post_url = ledger.get('ai_news_post_url')
    run_history = list(previous.get('run_history') or [])
    run_history.insert(0, {
        'run_date': date,
        'status': status,
        'primary_result': ledger.get('run_evidence_summary') or ('Daily AI-news post published.' if publish_success else ('Existing same-day post detected; duplicate avoided.' if duplicate_skip else 'Daily run blocked before required publishing completed.')),
        'posts_published': 1 if publish_success else 0,
        'tasks_completed': int(ledger.get('tasks_completed') or 0),
        'tasks_failed': int(ledger.get('tasks_failed') or len(blockers)),
        'error_detail': '; '.join(map(str, blockers)) if blockers else 'No unresolved blocker recorded.',
        'blockers': blockers,
        'ai_news_title': ai_title,
        'ai_news_post_url': post_url,
    })
    run_history = run_history[:30]
    payload = dict(previous)
    payload.update({
        'run_date': date,
        'run_completed_at_et': completed,
        'run_weekday': datetime.fromisoformat(completed).strftime('%A') if 'T' in completed else now_et().strftime('%A'),
        'timezone': 'America/New_York',
        'status': status,
        'last_run_label': f"{date} — {status.replace('_', ' ')}",
        'primary_result': run_history[0]['primary_result'],
        'community': 'HubActually',
        'agent': 'HubBot',
        'agent_version': 'v2',
        'published_post': {
            'title': ai_title,
            'thread_url': post_url or 'https://community.hubactually.com/',
            'thread_id': ledger.get('ai_news_thread_id'),
            'category': 'General',
            'image_url': ledger_image_url(ledger),
            'image_attached': image_is_attached(ledger),
            'publish_status': publish_status,
            'source_url': ledger.get('ai_news_source_url'),
            'supporting_url': ledger.get('ai_news_supporting_url'),
            'draft_path': ledger.get('ai_news_draft_path'),
            'generated_image_path': ledger.get('generated_image_path'),
            'published_at_utc': ledger.get('published_at_utc'),
            'post_visible_after_submit': bool(ledger.get('post_visible_after_submit')),
            'post_url_note': ledger.get('post_url_note'),
        },
        'checklist': [
            checklist_item('Preflight', normalize_status(ledger.get('preflight_status'), 'unknown')),
            checklist_item('Community access', normalize_status(ledger.get('community_access_result'), 'unknown')),
            checklist_item('Member review', 'completed' if ledger.get('new_members_found') is not None else 'unknown'),
            checklist_item('Discussion review', 'completed' if ledger.get('comments_added') is not None else 'unknown'),
            checklist_item('AI-news research', 'completed' if ledger.get('ai_news_source_url') else 'unknown'),
            checklist_item('Image generation', normalize_status(ledger.get('image_status'), 'unknown')),
            checklist_item('Community post', publish_status),
            checklist_item('Owner alert email', normalize_status(ledger.get('owner_alert_status'), 'unknown')),
            checklist_item('Saturday digest', normalize_status(ledger.get('saturday_digest_status'), 'unknown')),
            checklist_item('Dashboard update', 'pending_finalizer'),
        ],
        'metrics': {
            'required_tasks_completed': int(ledger.get('tasks_completed') or (1 if publish_success else 0)),
            'required_tasks_failed': int(ledger.get('tasks_failed') or len(blockers)),
            'owner_alerts_sent': 1 if normalize_status(ledger.get('owner_alert_status')) == 'sent' else 0,
            'posts_published': 1 if publish_success else 0,
            'new_welcomes_sent': len(ledger.get('welcomes_posted') or []),
            'duplicate_posts_avoided': 1 if publish_status == 'skipped_existing_same_day_post' else 0,
            'flagged_items': len(flagged),
        },
        'blockers': blockers,
        'flagged_items': flagged,
        'schedule': {
            'cron': '0 0 9 * * *',
            'label': 'Daily at 9:00 AM ET',
            'timezone': 'America/New_York',
            'status': 'active',
            'version': 'v2',
            'run_as_new_task': True,
        },
        'saturday_digest': {
            'status': normalize_status(ledger.get('saturday_digest_status'), 'unknown'),
            'reason': ledger.get('saturday_digest_reason'),
        },
        'owner_alert': {
            'status': normalize_status(ledger.get('owner_alert_status'), 'unknown'),
            'recipient': 'vipaymanshalaby@gmail.com',
            'sender': 'ayman@hubactually.com',
            'reason': ledger.get('owner_alert_reason'),
        },
        'community_stats': ledger.get('community_stats') or previous.get('community_stats') or {},
        'evidence': ledger.get('evidence') or {},
        'run_history': run_history,
        'ai_news_publish_status': publish_status,
        'ai_news_post_url': post_url,
    })
    return payload


def owner_alert_required(ledger: dict[str, Any]) -> bool:
    status = normalize_status(ledger.get('owner_alert_status'), 'unknown')
    if status in {'sent', 'not_required'}:
        return False
    if ledger.get('owner_alert_required') is True:
        return True
    if ledger.get('new_members_found') or ledger.get('flagged_items') or ledger.get('blockers'):
        return True
    if int(ledger.get('tasks_failed') or 0) > 0:
        return True
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'unknown')
    if publish_status not in {'unknown', 'not_required'} and not (is_publish_success(publish_status) or is_existing_duplicate_skip(publish_status)):
        return True
    return False


def run_owner_alert_fallback(ledger_path: Path, repo: Path) -> dict[str, Any]:
    helper = repo / 'hubbot_runtime' / 'hubbot_owner_alert.py'
    if not helper.exists():
        return {'status': 'skipped_helper_missing', 'helper': str(helper)}
    completed = subprocess.run(
        ['python3.11', str(helper), '--ledger', str(ledger_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120,
    )
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(completed.stdout or '{}')
    except Exception:
        parsed = {}
    parsed.update({
        'status': parsed.get('status') or ('completed' if completed.returncode == 0 else 'blocked'),
        'returncode': completed.returncode,
        'stderr_tail': (completed.stderr or '').strip().splitlines()[-1:] or [],
    })
    return parsed


def post_dashboard(payload: dict[str, Any]) -> str:
    url = os.environ.get('HUBBOT_DASHBOARD_URL')
    key = os.environ.get('HUBBOT_API_KEY')
    key_file = Path('/home/ubuntu/.config/hubbot/dashboard_api_key')
    if not key and key_file.exists():
        key = key_file.read_text(encoding='utf-8').strip()
    if not url or not key:
        return 'skipped_no_endpoint_or_key'
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url.rstrip('/') + '/api/run-data', data=body, method='POST', headers={'Content-Type': 'application/json', 'x-hubbot-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return f'posted_http_{resp.status}'
    except urllib.error.HTTPError as exc:
        return f'blocked_http_{exc.code}'
    except Exception as exc:
        return f'blocked_{type(exc).__name__}'


def git_commit(repo: Path, message: str) -> str:
    subprocess.run(['git', '-C', str(repo), 'add', 'run-data.json', 'client/public/latest-run.json', 'hubbot_runtime'], check=False)
    diff = subprocess.run(['git', '-C', str(repo), 'diff', '--cached', '--quiet'], check=False)
    if diff.returncode == 0:
        return 'no_changes_to_commit'
    commit = subprocess.run(['git', '-C', str(repo), 'commit', '-m', message], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if commit.returncode != 0:
        return 'commit_failed'
    push = subprocess.run(['git', '-C', str(repo), 'push'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    return 'committed_pushed' if push.returncode == 0 else 'committed_push_failed'


def main() -> int:
    parser = argparse.ArgumentParser(description='Finalize a HubBot run and update dashboard state.')
    parser.add_argument('--ledger', required=True, help='Path to HubBot JSON run ledger')
    parser.add_argument('--repo-root', default='/home/ubuntu/hubbot-dashboard')
    parser.add_argument('--commit', action='store_true', help='Commit and push repository fallback updates')
    parser.add_argument('--skip-owner-alert', action='store_true', help='Do not invoke the owner-alert fallback helper before dashboard update')
    args = parser.parse_args()
    repo = Path(args.repo_root)
    ledger_path = Path(args.ledger)
    ledger = read_json(ledger_path, {})
    owner_alert_fallback_status: dict[str, Any] = {'status': 'skipped_not_required'}
    if not args.skip_owner_alert and owner_alert_required(ledger):
        owner_alert_fallback_status = run_owner_alert_fallback(ledger_path, repo)
        ledger = read_json(ledger_path, ledger)
    previous = read_json(repo / 'run-data.json', {})
    payload = build_dashboard_payload(ledger, previous)
    evidence = payload.get('evidence') if isinstance(payload.get('evidence'), dict) else {}
    evidence['owner_alert_fallback_status'] = owner_alert_fallback_status
    payload['evidence'] = evidence
    if payload.get('owner_alert'):
        payload['owner_alert']['fallback_status'] = owner_alert_fallback_status.get('status')
    status = post_dashboard(payload)
    payload['checklist'] = [dict(item, outcome=('completed_' + status if item['task'] == 'Dashboard update' else item['outcome'])) for item in payload['checklist']]
    write_json(repo / 'run-data.json', payload)
    write_json(repo / 'client/public/latest-run.json', payload)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    write_json(LEDGER_DIR / 'latest.json', {'latest_ledger_json': str(ledger_path), 'dashboard_update_status': status, 'owner_alert_fallback_status': owner_alert_fallback_status.get('status'), 'updated_at_et': now_et().isoformat(timespec='seconds')})
    commit_status = 'not_requested'
    if args.commit and (repo / '.git').exists():
        commit_status = git_commit(repo, f"HubBot runtime/dashboard update {payload['run_date']}")
    print(json.dumps({'dashboard_api_status': status, 'repo_files_updated': True, 'commit_status': commit_status, 'run_date': payload['run_date'], 'owner_alert_fallback_status': owner_alert_fallback_status.get('status')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
