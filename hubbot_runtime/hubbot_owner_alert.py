#!/usr/bin/env python3
"""HubBot durable owner-alert sender.

Sends the required single-recipient owner alert when a run has new members,
flagged items, or blockers. The helper first tries GetResponse without modifying
campaigns/contact lists; if that path cannot deliver, it falls back to a direct
transactional email provider when configured. It never prints API keys.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
DEFAULT_LEDGER_DIR = Path('/home/ubuntu/hubactually_hubbot_run_ledger')
DEFAULT_GETRESPONSE_FILE = Path('/home/ubuntu/.config/hubbot/getresponse_api_key')
DEFAULT_BREVO_FILE = Path('/home/ubuntu/.config/hubbot/brevo_api_key')
OWNER_EMAIL = 'vipaymanshalaby@gmail.com'
SENDER_EMAIL = 'ayman@hubactually.com'
GETRESPONSE = 'https://api.getresponse.com/v3'
BREVO_SEND = 'https://api.brevo.com/v3/smtp/email'


def now_et() -> datetime:
    return datetime.now(ET)


def normalize_status(value: Any, default: str = 'unknown') -> str:
    if not value:
        return default
    return str(value).strip().lower().replace(' ', '_')


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_secret(env_name: str, file_path: Path) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value.strip()
    if file_path.exists():
        value = file_path.read_text(encoding='utf-8').strip()
        return value or None
    return None


def valid_email(value: str) -> bool:
    _, addr = parseaddr(value)
    return addr == value and bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value))


def publish_success(status: str) -> bool:
    return status == 'published' or status.startswith('published_') or status in {'skipped_existing_same_day_post', 'skipped_with_existing_same_day_post'}


def alert_required(ledger: dict[str, Any], *, force: bool = False) -> tuple[bool, list[str]]:
    if force:
        return True, ['forced_by_operator']
    reasons: list[str] = []
    if ledger.get('new_members_found'):
        reasons.append('new_members_found')
    if ledger.get('flagged_items'):
        reasons.append('flagged_items_present')
    if ledger.get('blockers'):
        reasons.append('blockers_present')
    if int(ledger.get('tasks_failed') or 0) > 0:
        reasons.append('failed_tasks_present')
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'unknown')
    if publish_status not in {'unknown', 'not_required'} and not publish_success(publish_status):
        reasons.append('required_ai_news_not_published')
    if ledger.get('owner_alert_required') is True:
        reasons.append('ledger_marked_required')
    return bool(reasons), reasons


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def item_text(item: Any) -> str:
    if isinstance(item, dict):
        parts = []
        for key in ('name', 'member', 'title', 'issue', 'summary', 'recommended_next_action', 'url', 'status'):
            if item.get(key):
                parts.append(f'{key}: {item[key]}')
        return '; '.join(parts) or json.dumps(item, ensure_ascii=False)
    return str(item)


def build_alert(ledger: dict[str, Any], reasons: list[str]) -> tuple[str, str, str]:
    run_completed = ledger.get('run_completed_at_et') or now_et().isoformat(timespec='seconds')
    run_date = (ledger.get('run_date') or str(run_completed)[:10])
    subject = f'HubActually admin alert: new members / flagged items — {run_date}'
    title = ledger.get('ai_news_title') or 'Not recorded'
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'unknown')
    post_url = ledger.get('ai_news_post_url') or 'Not available'
    new_members = as_list(ledger.get('new_members_found'))
    welcomed = as_list(ledger.get('welcomes_posted'))
    flagged = as_list(ledger.get('flagged_items'))
    blockers = as_list(ledger.get('blockers'))
    completed_actions = [
        f"Community access: {ledger.get('community_access_result', 'unknown')}",
        f"Comments added: {len(as_list(ledger.get('comments_added')))}",
        f"AI-news publish status: {publish_status}",
        f"Image status: {normalize_status(ledger.get('image_status'), 'unknown')}",
        f"Saturday digest: {normalize_status(ledger.get('saturday_digest_status'), 'unknown')}",
    ]
    lines = [
        f'HubActually admin alert for {run_date}',
        '',
        f'Run completed: {run_completed} America/New_York',
        f'Alert reasons: {", ".join(reasons)}',
        '',
        'AI-news post',
        f'- Title: {title}',
        f'- Publish status: {publish_status}',
        f'- Post URL: {post_url}',
        f"- Source URL: {ledger.get('ai_news_source_url') or 'Not available'}",
        '',
        'New members',
    ]
    lines.extend([f'- {item_text(item)}' for item in new_members] or ['- None recorded'])
    lines.extend(['', 'Welcomes posted'])
    lines.extend([f'- {item_text(item)}' for item in welcomed] or ['- None recorded'])
    lines.extend(['', 'Flagged items'])
    lines.extend([f'- {item_text(item)}' for item in flagged] or ['- None recorded'])
    lines.extend(['', 'Blockers / failed required steps'])
    lines.extend([f'- {item_text(item)}' for item in blockers] or ['- None recorded'])
    lines.extend(['', 'Actions completed'])
    lines.extend([f'- {item}' for item in completed_actions])
    if ledger.get('recommended_next_actions'):
        lines.extend(['', 'Recommended next actions'])
        lines.extend([f'- {item_text(item)}' for item in as_list(ledger.get('recommended_next_actions'))])
    text = '\n'.join(lines) + '\n'
    html = '<!doctype html><html><body style="font-family:Arial,sans-serif;line-height:1.45;color:#111827;">' + ''.join(
        '<p></p>' if line == '' else f'<p>{escape_line(line)}</p>' for line in lines
    ) + '</body></html>'
    return subject, text, html


def escape_line(line: str) -> str:
    import html
    if line.startswith('- '):
        return '&bull; ' + html.escape(line[2:])
    return html.escape(line)


def request_json(method: str, url: str, *, headers: dict[str, str], body: Any = None, timeout: int = 30) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode('utf-8')
    req_headers = dict(headers)
    if body is not None:
        req_headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', 'replace')
        try:
            payload: Any = json.loads(raw) if raw else {}
        except Exception:
            payload = {'error': raw[:500]}
        return exc.code, payload


def getresponse_headers(api_key: str) -> dict[str, str]:
    return {'X-Auth-Token': f'api-key {api_key}'}


def gr_get(api_key: str, path: str, query: dict[str, str] | None = None) -> tuple[int, Any]:
    suffix = path if path.startswith('/') else '/' + path
    url = GETRESPONSE + suffix
    if query:
        url += '?' + urllib.parse.urlencode(query)
    return request_json('GET', url, headers=getresponse_headers(api_key))


def find_gr_by_email_or_name(items: Any, *, email: str | None = None, name: str | None = None) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if email and str(item.get('email', '')).lower() == email.lower():
            return item
        if name and str(item.get('name', '')).lower() == name.lower():
            return item
    return None


def send_getresponse_newsletter(api_key: str, subject: str, html_body: str, text_body: str, *, dry_run: bool) -> dict[str, Any]:
    """Try a single-contact GetResponse newsletter without mutating contacts/lists."""
    result: dict[str, Any] = {'provider': 'getresponse', 'status': 'blocked', 'mutating_contact_list': False}
    account_status, _ = gr_get(api_key, '/accounts')
    result['account_http_status'] = account_status
    if not (200 <= account_status < 300):
        result['reason'] = 'GetResponse account endpoint unavailable'
        return result

    status, from_fields = gr_get(api_key, '/from-fields')
    result['from_fields_http_status'] = status
    from_field = find_gr_by_email_or_name(from_fields, email=SENDER_EMAIL)
    if not from_field and isinstance(from_fields, list) and from_fields:
        from_field = from_fields[0]
    if not from_field:
        result['reason'] = 'No usable GetResponse from-field found'
        return result

    status, campaigns = gr_get(api_key, '/campaigns', {'query[name]': 'HubActually'})
    result['campaigns_http_status'] = status
    campaign = find_gr_by_email_or_name(campaigns, name='HubActually')
    if not campaign and isinstance(campaigns, list) and campaigns:
        campaign = campaigns[0]
    if not campaign:
        result['reason'] = 'No usable GetResponse campaign/list found'
        return result

    status, contacts = gr_get(api_key, '/contacts', {'query[email]': OWNER_EMAIL})
    result['contacts_http_status'] = status
    owner_contact = find_gr_by_email_or_name(contacts, email=OWNER_EMAIL)
    if not owner_contact:
        result['reason'] = 'Owner email is not an existing GetResponse contact; contact creation is intentionally disabled'
        return result

    payload = {
        'name': f'HubBot owner alert {datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S %Z")}',
        'type': 'broadcast',
        'subject': subject,
        'fromField': {'fromFieldId': from_field.get('fromFieldId') or from_field.get('id')},
        'content': {'html': html_body, 'plain': text_body},
        'sendSettings': {'selectedContacts': [{'contactId': owner_contact.get('contactId') or owner_contact.get('id')}]},
    }
    result['selected_contact_id_present'] = bool(payload['sendSettings']['selectedContacts'][0].get('contactId'))
    if dry_run:
        result.update({'status': 'dry_run_ready', 'reason': 'GetResponse selected-contact newsletter payload resolved'})
        return result
    status, data = request_json('POST', GETRESPONSE + '/newsletters', headers=getresponse_headers(api_key), body=payload, timeout=45)
    result['newsletter_create_http_status'] = status
    if 200 <= status < 300:
        result.update({'status': 'sent', 'message_id': data.get('newsletterId') or data.get('id') if isinstance(data, dict) else None})
    else:
        result.update({'status': 'blocked', 'reason': f'GetResponse newsletter create failed with HTTP {status}', 'response_keys': sorted(data.keys()) if isinstance(data, dict) else []})
    return result


def send_brevo(api_key: str, subject: str, html_body: str, text_body: str, *, dry_run: bool) -> dict[str, Any]:
    result: dict[str, Any] = {'provider': 'brevo_direct_email', 'status': 'blocked'}
    if not valid_email(OWNER_EMAIL) or not valid_email(SENDER_EMAIL):
        result['reason'] = 'Configured sender or recipient email is invalid'
        return result
    payload = {
        'sender': {'email': SENDER_EMAIL, 'name': 'HubActually'},
        'to': [{'email': OWNER_EMAIL}],
        'subject': subject,
        'htmlContent': html_body,
        'textContent': text_body,
    }
    if dry_run:
        result.update({'status': 'dry_run_ready', 'recipient': OWNER_EMAIL, 'sender': SENDER_EMAIL})
        return result
    status, data = request_json('POST', BREVO_SEND, headers={'api-key': api_key, 'accept': 'application/json'}, body=payload, timeout=45)
    result['http_status'] = status
    if 200 <= status < 300:
        result.update({'status': 'sent', 'message_id': data.get('messageId') if isinstance(data, dict) else None, 'recipient': OWNER_EMAIL})
    else:
        result.update({'status': 'blocked', 'reason': f'Brevo direct email failed with HTTP {status}', 'response_keys': sorted(data.keys()) if isinstance(data, dict) else []})
    return result


def update_ledger(ledger_path: Path, status: str, reason: str, result_path: Path) -> None:
    ledger = read_json(ledger_path, {})
    ledger['owner_alert_status'] = status
    ledger['owner_alert_reason'] = reason
    evidence = ledger.get('evidence') if isinstance(ledger.get('evidence'), dict) else {}
    evidence['owner_alert_result_path'] = str(result_path)
    ledger['evidence'] = evidence
    write_json(ledger_path, ledger)


def main() -> int:
    parser = argparse.ArgumentParser(description='Send a HubActually owner alert when the HubBot run requires one.')
    parser.add_argument('--ledger', required=True, help='Path to the HubBot JSON run ledger.')
    parser.add_argument('--output-dir', default=str(DEFAULT_LEDGER_DIR))
    parser.add_argument('--getresponse-key-file', default=str(DEFAULT_GETRESPONSE_FILE))
    parser.add_argument('--brevo-key-file', default=str(DEFAULT_BREVO_FILE))
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = read_json(ledger_path, {})
    required, reasons = alert_required(ledger, force=args.force)
    result: dict[str, Any] = {
        'agent': 'HubBot',
        'component': 'owner_alert',
        'created_at_et': now_et().isoformat(timespec='seconds'),
        'ledger_path': str(ledger_path),
        'alert_required': required,
        'alert_reasons': reasons,
        'recipient': OWNER_EMAIL,
        'sender': SENDER_EMAIL,
        'dry_run': bool(args.dry_run),
        'attempts': [],
    }
    if not required:
        result.update({'status': 'not_required', 'reason': 'No new members, flagged items, blockers, or failed required steps were recorded.'})
    else:
        subject, text_body, html_body = build_alert(ledger, reasons)
        result['subject'] = subject
        gr_key = read_secret('GETRESPONSE_API_KEY', Path(args.getresponse_key_file))
        brevo_key = read_secret('BREVO_API_KEY', Path(args.brevo_key_file))
        if gr_key:
            gr_attempt = send_getresponse_newsletter(gr_key, subject, html_body, text_body, dry_run=args.dry_run)
            result['attempts'].append(gr_attempt)
            if gr_attempt.get('status') in {'sent', 'dry_run_ready'}:
                result.update({'status': gr_attempt['status'], 'provider': gr_attempt['provider'], 'reason': gr_attempt.get('reason', 'delivered by GetResponse')})
        if result.get('status') not in {'sent', 'dry_run_ready'} and brevo_key:
            brevo_attempt = send_brevo(brevo_key, subject, html_body, text_body, dry_run=args.dry_run)
            result['attempts'].append(brevo_attempt)
            if brevo_attempt.get('status') in {'sent', 'dry_run_ready'}:
                result.update({'status': brevo_attempt['status'], 'provider': brevo_attempt['provider'], 'reason': brevo_attempt.get('reason', 'delivered by direct email fallback')})
        if result.get('status') not in {'sent', 'dry_run_ready'}:
            configured = []
            if gr_key:
                configured.append('getresponse')
            if brevo_key:
                configured.append('brevo_direct_email')
            result.update({'status': 'blocked', 'reason': 'No configured provider delivered the owner alert.', 'configured_providers': configured})

    stamp = datetime.now(ET).strftime('%Y%m%dT%H%M%S%z')
    result_path = output_dir / f'{stamp}_owner_alert_result.json'
    result['result_path'] = str(result_path)
    write_json(result_path, result)
    if not args.dry_run:
        update_ledger(ledger_path, str(result['status']), str(result.get('reason', '')), result_path)
    print(json.dumps({
        'status': result.get('status'),
        'provider': result.get('provider'),
        'alert_required': result.get('alert_required'),
        'result_path': str(result_path),
    }, indent=2))
    return 0 if result.get('status') in {'sent', 'not_required', 'dry_run_ready'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
