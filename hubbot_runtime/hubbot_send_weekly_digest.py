#!/usr/bin/env python3
"""HubBot Saturday weekly digest sender.

This helper is intentionally fail-closed. It sends or schedules the HubActually
weekly community digest only when the actual America/New_York date is Saturday.
It resolves the GetResponse sender, HubActually recipient list/campaign, and the
saved template named ``community`` through non-mutating API calls before any
full-list newsletter operation. It never prints API keys.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
DEFAULT_LEDGER_DIR = Path('/home/ubuntu/hubactually_hubbot_run_ledger')
DEFAULT_GETRESPONSE_FILE = Path('/home/ubuntu/.config/hubbot/getresponse_api_key')
GETRESPONSE = 'https://api.getresponse.com/v3'
SENDER_EMAIL = 'ayman@hubactually.com'
CAMPAIGN_NAMES = ('hubactually', 'HubActually')
TEMPLATE_NAME = 'community'
PS_LINE = 'P.S. Our live meeting is every Saturday at 1:00 PM Eastern. You can find the meeting link at the top of the community.'


def now_et() -> datetime:
    return datetime.now(ET)


def parse_now(value: str | None) -> datetime:
    if not value:
        return now_et()
    cleaned = value.strip().replace('Z', '+00:00')
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


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


def normalize_status(value: Any, default: str = 'unknown') -> str:
    if not value:
        return default
    return str(value).strip().lower().replace(' ', '_')


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def escape_line(line: str) -> str:
    if line.startswith('- '):
        return '&bull; ' + html.escape(line[2:])
    return html.escape(line)


def strip_tags(value: str) -> str:
    return re.sub(r'<[^>]+>', '', value or '').strip()


def item_text(item: Any) -> str:
    if isinstance(item, dict):
        parts: list[str] = []
        for key in ('title', 'name', 'member', 'summary', 'url', 'status', 'reason'):
            if item.get(key):
                parts.append(f'{key}: {strip_tags(str(item[key]))}')
        return '; '.join(parts) or json.dumps(item, ensure_ascii=False)
    return strip_tags(str(item))


def build_digest_content(ledger: dict[str, Any], *, body_file: Path | None = None) -> tuple[str, str, str]:
    run_dt = str(ledger.get('run_completed_at_et') or ledger.get('run_date') or now_et().date())
    run_date = str(ledger.get('run_date') or run_dt[:10])
    subject = f'HubActually weekly community digest — {run_date}'

    if body_file:
        text = body_file.read_text(encoding='utf-8').strip()
        if PS_LINE not in text:
            text = text.rstrip() + '\n\n' + PS_LINE
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        html_body = '<!doctype html><html><body style="font-family:Arial,sans-serif;line-height:1.55;color:#111827;">' + ''.join(
            f'<p>{html.escape(p).replace(chr(10), "<br>")}</p>' for p in paragraphs
        ) + '</body></html>'
        return subject, text + '\n', html_body

    lines = [
        f'HubActually weekly community digest — {run_date}',
        '',
        'Here is the concise community recap for the week.',
        '',
        'Community highlights',
    ]
    comments = as_list(ledger.get('comments_added'))
    welcomes = as_list(ledger.get('welcomes_posted'))
    flagged = as_list(ledger.get('flagged_items'))
    if comments:
        lines.extend([f'- {item_text(item)}' for item in comments])
    if welcomes:
        lines.extend([f'- New-member welcome activity: {item_text(item)}' for item in welcomes])
    if not comments and not welcomes:
        lines.append('- No high-signal community discussion items were recorded in the run ledger.')

    title = ledger.get('ai_news_title')
    source = ledger.get('ai_news_source_url')
    publish_status = normalize_status(ledger.get('ai_news_publish_status'), 'unknown')
    if title or source:
        lines.extend(['', 'AI and business note'])
        if title:
            lines.append(f'- {strip_tags(str(title))}')
        if source:
            lines.append(f'- Source: {source}')
        lines.append(f'- Publish status: {publish_status}')

    if flagged:
        lines.extend(['', 'Items to keep an eye on'])
        lines.extend([f'- {item_text(item)}' for item in flagged])

    lines.extend(['', PS_LINE])
    text = '\n'.join(lines) + '\n'
    html_body = '<!doctype html><html><body style="font-family:Arial,sans-serif;line-height:1.55;color:#111827;">' + ''.join(
        '<p></p>' if line == '' else f'<p>{escape_line(line)}</p>' for line in lines
    ) + '</body></html>'
    return subject, text, html_body


def request_json(method: str, url: str, *, headers: dict[str, str], body: Any = None, timeout: int = 45) -> tuple[int, Any]:
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
    except Exception as exc:
        return 0, {'error': type(exc).__name__}


def getresponse_headers(api_key: str) -> dict[str, str]:
    return {'X-Auth-Token': f'api-key {api_key}'}


def gr_get(api_key: str, path: str, query: dict[str, str] | None = None) -> tuple[int, Any]:
    suffix = path if path.startswith('/') else '/' + path
    url = GETRESPONSE + suffix
    if query:
        url += '?' + urllib.parse.urlencode(query)
    return request_json('GET', url, headers=getresponse_headers(api_key), timeout=30)


def item_id(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return None


def find_by_name(items: Any, names: tuple[str, ...] | list[str] | str) -> dict[str, Any] | None:
    if isinstance(names, str):
        names = (names,)
    wanted = {name.lower() for name in names}
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get('name', '')).strip().lower() in wanted:
            return item
    return None


def find_from_field(items: Any, email: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get('email', '')).lower() == email.lower():
            return item
    return items[0] if items else None


def resolve_getresponse(api_key: str) -> dict[str, Any]:
    result: dict[str, Any] = {'status': 'blocked'}
    account_status, _ = gr_get(api_key, '/accounts')
    result['account_http_status'] = account_status
    if not (200 <= account_status < 300):
        result['reason'] = 'GetResponse account endpoint unavailable'
        return result

    from_status, from_fields = gr_get(api_key, '/from-fields')
    result['from_fields_http_status'] = from_status
    from_field = find_from_field(from_fields, SENDER_EMAIL)
    if not from_field:
        result['reason'] = f'No usable GetResponse from-field found for {SENDER_EMAIL}'
        return result
    from_field_id = item_id(from_field, 'fromFieldId', 'id')
    if not from_field_id:
        result['reason'] = 'Resolved GetResponse from-field lacks an ID'
        return result

    campaign_status, campaigns = gr_get(api_key, '/campaigns', {'query[name]': 'hubactually'})
    result['campaigns_http_status'] = campaign_status
    campaign = find_by_name(campaigns, CAMPAIGN_NAMES)
    if not campaign and isinstance(campaigns, list) and campaigns:
        campaign = campaigns[0]
    if not campaign:
        result['reason'] = 'No usable GetResponse HubActually campaign/list found'
        return result
    campaign_id = item_id(campaign, 'campaignId', 'id')
    if not campaign_id:
        result['reason'] = 'Resolved GetResponse campaign/list lacks an ID'
        return result

    # Template resolution is a hard gate because the playbook requires the saved
    # My Templates template named "community". The newsletter content is still
    # supplied explicitly because the v3 newsletter endpoint sends rendered HTML.
    template_status, templates = gr_get(api_key, '/templates', {'query[name]': TEMPLATE_NAME})
    result['templates_http_status'] = template_status
    template = find_by_name(templates, TEMPLATE_NAME)
    if not template and isinstance(templates, list) and templates:
        template = templates[0]
    if not template:
        result['reason'] = 'No usable GetResponse template named community found'
        return result
    template_id = item_id(template, 'templateId', 'id')
    if not template_id:
        result['reason'] = 'Resolved GetResponse template lacks an ID'
        return result

    result.update({
        'status': 'resolved',
        'from_field_id_present': True,
        'campaign_id_present': True,
        'template_id_present': True,
        'campaign_name': campaign.get('name'),
        'template_name': template.get('name'),
        'from_field': {'email': from_field.get('email'), 'name': from_field.get('name')},
        '_from_field_id': from_field_id,
        '_campaign_id': campaign_id,
        '_template_id': template_id,
    })
    return result


def redact_resolution(resolution: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in resolution.items() if not k.startswith('_')}


def build_newsletter_payload(subject: str, html_body: str, text_body: str, resolution: dict[str, Any], *, action_time: datetime, scheduled_for: datetime | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'name': f'HubActually weekly digest {action_time.strftime("%Y-%m-%d %H:%M:%S %Z")}',
        'type': 'broadcast',
        'subject': subject,
        'fromField': {'fromFieldId': resolution['_from_field_id']},
        'content': {'html': html_body, 'plain': text_body},
        'sendSettings': {'selectedCampaigns': [{'campaignId': resolution['_campaign_id']}]},
    }
    # GetResponse v3 accepts a scheduled send timestamp on newsletter creation in
    # accounts where scheduling is enabled. If the provider rejects this field,
    # HubBot records a blocked result instead of silently sending at the wrong time.
    if scheduled_for:
        payload['sendOn'] = scheduled_for.isoformat(timespec='seconds')
    return payload


def send_or_schedule(api_key: str, payload: dict[str, Any], *, dry_run: bool, mode: str) -> dict[str, Any]:
    result: dict[str, Any] = {'provider': 'getresponse', 'status': 'blocked', 'mode': mode, 'mutating_contact_list': False}
    result['selected_campaigns_count'] = len(payload.get('sendSettings', {}).get('selectedCampaigns', []))
    result['has_plain_content'] = bool(payload.get('content', {}).get('plain'))
    result['has_html_content'] = bool(payload.get('content', {}).get('html'))
    result['has_send_on'] = bool(payload.get('sendOn'))
    if dry_run:
        result.update({'status': 'dry_run_ready', 'reason': f'GetResponse full-list digest payload resolved for {mode}'})
        return result
    status, data = request_json('POST', GETRESPONSE + '/newsletters', headers=getresponse_headers(api_key), body=payload, timeout=60)
    result['newsletter_create_http_status'] = status
    if 200 <= status < 300:
        result.update({'status': 'scheduled' if mode == 'schedule' else 'sent', 'message_id': data.get('newsletterId') or data.get('id') if isinstance(data, dict) else None})
    else:
        result.update({'status': 'blocked', 'reason': f'GetResponse newsletter create failed with HTTP {status}', 'response_keys': sorted(data.keys()) if isinstance(data, dict) else []})
    return result


def update_ledger(ledger_path: Path, result: dict[str, Any], result_path: Path) -> None:
    ledger = read_json(ledger_path, {})
    status = result.get('status', 'blocked')
    reason = result.get('reason') or result.get('mode') or 'recorded'
    ledger['saturday_digest_status'] = status
    ledger['saturday_digest_reason'] = reason
    if status == 'blocked':
        blockers = ledger.get('blockers') if isinstance(ledger.get('blockers'), list) else []
        blocker = f'Saturday weekly digest blocked: {reason}'
        if blocker not in blockers:
            blockers.append(blocker)
        ledger['blockers'] = blockers
        flagged = ledger.get('flagged_items') if isinstance(ledger.get('flagged_items'), list) else []
        flag = {'type': 'weekly_digest_blocked', 'reason': reason, 'result_path': str(result_path)}
        if flag not in flagged:
            flagged.append(flag)
        ledger['flagged_items'] = flagged
        ledger['owner_alert_required'] = True
    if result.get('scheduled_for_et'):
        ledger['saturday_digest_scheduled_for_et'] = result.get('scheduled_for_et')
    evidence = ledger.get('evidence') if isinstance(ledger.get('evidence'), dict) else {}
    evidence['saturday_digest_result_path'] = str(result_path)
    ledger['evidence'] = evidence
    write_json(ledger_path, ledger)


def main() -> int:
    parser = argparse.ArgumentParser(description='Send or schedule the HubActually Saturday weekly digest through GetResponse.')
    parser.add_argument('--ledger', required=True, help='Path to HubBot JSON run ledger.')
    parser.add_argument('--body-file', help='Optional prepared digest body text file. The required P.S. is appended if missing.')
    parser.add_argument('--output-dir', default=str(DEFAULT_LEDGER_DIR))
    parser.add_argument('--getresponse-key-file', default=str(DEFAULT_GETRESPONSE_FILE))
    parser.add_argument('--now-et', help='Testing override for current America/New_York datetime. Do not use in production.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    action_time = parse_now(args.now_et)
    stamp = action_time.strftime('%Y%m%dT%H%M%S%z')
    result_path = output_dir / f'{stamp}_weekly_digest_result.json'
    ledger = read_json(ledger_path, {})

    result: dict[str, Any] = {
        'agent': 'HubBot',
        'component': 'weekly_digest',
        'created_at_et': action_time.isoformat(timespec='seconds'),
        'ledger_path': str(ledger_path),
        'sender': SENDER_EMAIL,
        'recipient_list': 'hubactually',
        'template_name_required': TEMPLATE_NAME,
        'ps_line_present': True,
        'dry_run': bool(args.dry_run),
    }

    if action_time.weekday() != 5:
        result.update({'status': 'not_saturday', 'reason': 'Actual America/New_York date is not Saturday; digest is not allowed.'})
        write_json(result_path, result)
        update_ledger(ledger_path, result, result_path)
        print(f'weekly_digest_status={result["status"]}')
        print(f'weekly_digest_result={result_path}')
        return 0

    digest_cutoff = datetime.combine(action_time.date(), time(10, 0), tzinfo=ET)
    mode = 'schedule' if action_time < digest_cutoff else 'send'
    scheduled_for = digest_cutoff if mode == 'schedule' else None
    result['mode'] = mode
    if scheduled_for:
        result['scheduled_for_et'] = scheduled_for.isoformat(timespec='seconds')

    subject, text_body, html_body = build_digest_content(ledger, body_file=Path(args.body_file) if args.body_file else None)
    result['subject'] = subject
    result['body_chars'] = len(text_body)
    result['ps_line_present'] = PS_LINE in text_body
    if PS_LINE not in text_body:
        result.update({'status': 'blocked', 'reason': 'Required weekly digest P.S. line missing after content generation.'})
        write_json(result_path, result)
        update_ledger(ledger_path, result, result_path)
        print(f'weekly_digest_status={result["status"]}')
        print(f'weekly_digest_result={result_path}')
        return 2

    api_key = read_secret('GETRESPONSE_API_KEY', Path(args.getresponse_key_file))
    if not api_key:
        result.update({'status': 'blocked', 'reason': 'GetResponse API key is unavailable in environment or protected runtime store.'})
        write_json(result_path, result)
        update_ledger(ledger_path, result, result_path)
        print(f'weekly_digest_status={result["status"]}')
        print(f'weekly_digest_result={result_path}')
        return 2

    resolution = resolve_getresponse(api_key)
    result['getresponse_resolution'] = redact_resolution(resolution)
    if resolution.get('status') != 'resolved':
        result.update({'status': 'blocked', 'reason': resolution.get('reason', 'GetResponse resolution failed')})
        write_json(result_path, result)
        update_ledger(ledger_path, result, result_path)
        print(f'weekly_digest_status={result["status"]}')
        print(f'weekly_digest_result={result_path}')
        return 2

    payload = build_newsletter_payload(subject, html_body, text_body, resolution, action_time=action_time, scheduled_for=scheduled_for)
    attempt = send_or_schedule(api_key, payload, dry_run=args.dry_run, mode=mode)
    result['attempt'] = attempt
    result['status'] = attempt.get('status', 'blocked')
    result['reason'] = attempt.get('reason') or (f'Weekly digest {result["status"]} through GetResponse')
    write_json(result_path, result)
    update_ledger(ledger_path, result, result_path)
    print(f'weekly_digest_status={result["status"]}')
    print(f'weekly_digest_result={result_path}')
    return 0 if result['status'] in {'sent', 'scheduled', 'dry_run_ready'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
