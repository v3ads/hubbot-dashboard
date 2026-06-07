#!/usr/bin/env python3
"""Post a start-of-run heartbeat for HubBot.

The heartbeat is intentionally small, secret-safe, and idempotent. It gives the
live dashboard an immediate visible signal that a scheduled/fresh-sandbox run
has started before HubBot attempts community browser actions. The end-of-run
finalizer remains authoritative for the completed run result.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import requests
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
DEFAULT_DASHBOARD_URL = 'https://hubbot.virtapreneur.com'
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


def dashboard_api_key() -> str:
    key = os.environ.get('HUBBOT_API_KEY', '').strip()
    key_file = Path('/home/ubuntu/.config/hubbot/dashboard_api_key')
    if not key and key_file.exists():
        key = key_file.read_text(encoding='utf-8').strip()
    return key


def post_dashboard(payload: dict[str, Any], dashboard_url: str) -> str:
    key = dashboard_api_key()
    if not dashboard_url or not key:
        return 'skipped_no_endpoint_or_key'
    endpoint = dashboard_url.rstrip('/') + '/api/run-data'
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={'X-HubBot-Api-Key': key},
            timeout=25,
        )
        return f'posted_http_{response.status_code}' if response.ok else f'blocked_http_{response.status_code}'
    except requests.RequestException as exc:  # pragma: no cover - runtime environment dependent
        return f'blocked_{type(exc).__name__}'


def build_payload(previous: dict[str, Any], run_date: str, started_at: str, task_label: str) -> dict[str, Any]:
    history = [item for item in list(previous.get('run_history') or []) if item.get('run_date') != run_date]
    history.insert(0, {
        'run_date': run_date,
        'status': 'running',
        'primary_result': f'HubBot run started at {started_at} and has not finalized yet.',
        'posts_published': 0,
        'tasks_completed': 0,
        'tasks_failed': 0,
        'error_detail': 'No blocker has been recorded yet; run is in progress.',
        'blockers': [],
        'ai_news_title': 'Pending',
        'ai_news_post_url': None,
    })
    payload = dict(previous)
    payload.update({
        'run_date': run_date,
        'run_started_at_et': started_at,
        'run_completed_at_et': started_at,
        'run_weekday': datetime.fromisoformat(started_at).strftime('%A'),
        'timezone': 'America/New_York',
        'status': 'running',
        'last_run_label': f'{run_date} — running',
        'primary_result': f'HubBot start-of-run heartbeat posted at {started_at}. Community actions have not finalized yet.',
        'community': 'HubActually',
        'agent': 'HubBot',
        'agent_version': 'v2',
        'published_post': {
            'title': 'Pending',
            'thread_url': 'https://community.hubactually.com/',
            'thread_id': None,
            'category': 'General',
            'image_url': '',
            'image_attached': False,
            'publish_status': 'pending',
            'source_url': None,
            'supporting_url': None,
            'draft_path': None,
            'generated_image_path': None,
            'published_at_utc': None,
            'post_visible_after_submit': False,
            'post_url_note': 'Run is in progress; final post details are pending.',
        },
        'checklist': [
            {'task': 'Bootstrap', 'outcome': 'completed'},
            {'task': 'Preflight', 'outcome': 'completed_or_in_progress'},
            {'task': 'Start-of-run heartbeat', 'outcome': 'posting'},
            {'task': 'Community access', 'outcome': 'pending'},
            {'task': 'Member review', 'outcome': 'pending'},
            {'task': 'Discussion review', 'outcome': 'pending'},
            {'task': 'AI-news research', 'outcome': 'pending'},
            {'task': 'Image generation', 'outcome': 'pending'},
            {'task': 'Community post', 'outcome': 'pending'},
            {'task': 'Dashboard final update', 'outcome': 'pending'},
        ],
        'metrics': {
            'required_tasks_completed': 0,
            'required_tasks_failed': 0,
            'owner_alerts_sent': 0,
            'posts_published': 0,
            'new_welcomes_sent': 0,
            'duplicate_posts_avoided': 0,
            'flagged_items': 0,
        },
        'blockers': [],
        'flagged_items': [],
        'schedule': {
            'cron': '0 0 9 * * *',
            'label': 'Daily at 9:00 AM ET',
            'timezone': 'America/New_York',
            'status': 'active',
            'version': 'v2',
            'run_as_new_task': True,
        },
        'saturday_digest': {'status': 'pending', 'reason': 'Run has not reached digest evaluation yet.'},
        'owner_alert': {
            'status': 'pending',
            'recipient': 'vipaymanshalaby@gmail.com',
            'sender': 'ayman@hubactually.com',
            'reason': 'Run is in progress; no alert decision has been finalized.',
        },
        'evidence': {
            **(previous.get('evidence') if isinstance(previous.get('evidence'), dict) else {}),
            'heartbeat': {
                'status': 'posting',
                'run_started_at_et': started_at,
                'task_label': task_label,
                'host': socket.gethostname(),
                'purpose': 'Start-of-run visibility before community browser actions.',
            },
        },
        'run_history': history[:30],
        'ai_news_publish_status': 'pending',
        'ai_news_post_url': None,
    })
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='Post a HubBot start-of-run heartbeat to the dashboard.')
    parser.add_argument('--run-date', help='Run date in YYYY-MM-DD. Defaults to current America/New_York date.')
    parser.add_argument('--repo-root', default='/home/ubuntu/hubbot-dashboard')
    parser.add_argument('--dashboard-url', default=os.environ.get('HUBBOT_DASHBOARD_URL', DEFAULT_DASHBOARD_URL))
    parser.add_argument('--task-label', default=os.environ.get('MANUS_TASK_ID') or os.environ.get('TASK_UID') or 'scheduled_or_manual_run')
    parser.add_argument('--write-local', action='store_true', help='Also write repo fallback JSON files. Do not commit heartbeat-only files.')
    args = parser.parse_args()

    started_at = now_et().isoformat(timespec='seconds')
    run_date = args.run_date or started_at[:10]
    repo = Path(args.repo_root)
    previous = read_json(repo / 'client/public/latest-run.json', read_json(repo / 'run-data.json', {}))
    payload = build_payload(previous, run_date, started_at, args.task_label)
    status = post_dashboard(payload, args.dashboard_url)
    payload['evidence']['heartbeat']['status'] = status
    payload['checklist'] = [
        dict(item, outcome=('completed_' + status if item['task'] == 'Start-of-run heartbeat' else item['outcome']))
        for item in payload['checklist']
    ]
    if args.write_local:
        write_json(repo / 'run-data.json', payload)
        write_json(repo / 'client/public/latest-run.json', payload)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    heartbeat_result = {
        'run_date': run_date,
        'run_started_at_et': started_at,
        'dashboard_api_status': status,
        'dashboard_url': args.dashboard_url.rstrip('/') + '/api/run-data',
        'local_files_written': bool(args.write_local),
    }
    result_path = LEDGER_DIR / f'{run_date}_heartbeat.json'
    write_json(result_path, heartbeat_result)
    print(json.dumps({**heartbeat_result, 'result_path': str(result_path)}, indent=2))
    return 0 if status.startswith('posted_http_') or status == 'skipped_no_endpoint_or_key' else 1


if __name__ == '__main__':
    raise SystemExit(main())
