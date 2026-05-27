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


def build_dashboard_payload(ledger: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    completed = ledger.get('run_completed_at_et') or now_et().isoformat(timespec='seconds')
    date = (ledger.get('run_date') or completed[:10])
    blockers = ledger.get('blockers') or []
    flagged = ledger.get('flagged_items') or []
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'blocked')
    status = 'completed' if publish_status == 'published' and not blockers else ('completed_with_flags' if publish_status == 'published' else 'blocked_required_action')
    ai_title = ledger.get('ai_news_title') or 'Not published'
    post_url = ledger.get('ai_news_post_url')
    run_history = list(previous.get('run_history') or [])
    run_history.insert(0, {
        'run_date': date,
        'status': status,
        'primary_result': ledger.get('run_evidence_summary') or ('Daily AI-news post published.' if publish_status == 'published' else 'Daily run blocked before required publishing completed.'),
        'posts_published': 1 if publish_status == 'published' else 0,
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
            'image_url': ledger.get('image_url') or '',
            'image_attached': normalize_status(ledger.get('image_status')) in {'uploaded', 'attached'},
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
            'required_tasks_completed': int(ledger.get('tasks_completed') or (1 if publish_status == 'published' else 0)),
            'required_tasks_failed': int(ledger.get('tasks_failed') or len(blockers)),
            'owner_alerts_sent': 1 if normalize_status(ledger.get('owner_alert_status')) == 'sent' else 0,
            'posts_published': 1 if publish_status == 'published' else 0,
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
    args = parser.parse_args()
    repo = Path(args.repo_root)
    ledger_path = Path(args.ledger)
    ledger = read_json(ledger_path, {})
    previous = read_json(repo / 'run-data.json', {})
    payload = build_dashboard_payload(ledger, previous)
    status = post_dashboard(payload)
    payload['checklist'] = [dict(item, outcome=('completed_' + status if item['task'] == 'Dashboard update' else item['outcome'])) for item in payload['checklist']]
    write_json(repo / 'run-data.json', payload)
    write_json(repo / 'client/public/latest-run.json', payload)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    write_json(LEDGER_DIR / 'latest.json', {'latest_ledger_json': str(ledger_path), 'dashboard_update_status': status, 'updated_at_et': now_et().isoformat(timespec='seconds')})
    commit_status = 'not_requested'
    if args.commit and (repo / '.git').exists():
        commit_status = git_commit(repo, f"HubBot runtime/dashboard update {payload['run_date']}")
    print(json.dumps({'dashboard_api_status': status, 'repo_files_updated': True, 'commit_status': commit_status, 'run_date': payload['run_date']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
