#!/usr/bin/env python3
"""HubBot durable AI-news publisher.

Uploads the generated daily image through the HubActually community API and creates
the General-channel thread with the uploaded CDN URL as ``previewURL``. This helper
intentionally avoids the browser composer for image attachment because browser
uploads have proven unreliable in scheduled runs.

The script never prints cookies or credentials. It writes a redacted result JSON
suitable for the HubBot run ledger.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception:  # pragma: no cover - import availability is checked at runtime
    Cipher = algorithms = modes = default_backend = None  # type: ignore[assignment]

BASE = 'https://community.hubactually.com'
PROJECT = '56382'
GENERAL_CATEGORY = {
    'id': '4496ab4b-8529-4a7e-9a31-588fe414d9b0',
    'name': 'General',
    'permissions': 'anyone',
    'order': 0,
    'createdAt': '2026-03-10T15:22:56.403936+00:00',
}
DEFAULT_LEDGER_DIR = Path('/home/ubuntu/hubactually_hubbot_run_ledger')
COOKIE_CANDIDATES = [
    Path('/home/ubuntu/.browser_data_dir/Default/Cookies'),
    Path('/home/ubuntu/.config/chromium/Default/Cookies'),
    Path('/home/ubuntu/.config/google-chrome/Default/Cookies'),
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_text_arg(value: str | None, path: str | None, *, default: str = '') -> str:
    if path:
        return Path(path).read_text(encoding='utf-8')
    return value or default


def text_to_html(text: str) -> str:
    paragraphs = [p.strip() for p in text.replace('\r\n', '\n').split('\n\n') if p.strip()]
    return ''.join(f'<p>{html.escape(p).replace(chr(10), "<br>")}</p>' for p in paragraphs)


def locate_cookie_db(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise FileNotFoundError(f'cookie database not found at configured path: {path}')
    for candidate in COOKIE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError('no supported Chromium cookie database was found')


def chrome_unpad(data: bytes) -> bytes:
    if not data:
        return data
    n = data[-1]
    if 1 <= n <= 16 and data.endswith(bytes([n]) * n):
        return data[:-n]
    return data


def decrypt_chrome_cookie(host: str, encrypted_value: bytes) -> str:
    """Decrypt legacy Chromium Linux cookie values used by the scheduled browser."""
    if not encrypted_value:
        return ''
    if Cipher is None:
        raise RuntimeError('cryptography package is required to decrypt Chromium cookies')
    import hashlib

    payload = encrypted_value[3:] if encrypted_value.startswith(b'v10') else encrypted_value
    key = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'saltysalt', 1, dklen=16)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(b' ' * 16), backend=default_backend()).decryptor()
    raw = chrome_unpad(decryptor.update(payload) + decryptor.finalize())
    host_hash = hashlib.sha256(host.encode()).digest()
    if raw.startswith(host_hash):
        raw = raw[32:]
    return raw.decode('utf-8', 'replace')


def get_hubactually_cookies(cookie_db: Path, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hubbot_cookies_') as tmp:
        copy_path = Path(tmp) / 'Cookies.copy'
        shutil.copy2(cookie_db, copy_path)
        conn = sqlite3.connect(copy_path)
        try:
            rows = list(conn.execute(
                "select host_key, name, value, encrypted_value from cookies where host_key like '%hubactually%'"
            ))
        finally:
            conn.close()
    cookies: dict[str, str] = {}
    for host, name, value, encrypted in rows:
        cookie_value = value or ''
        if not cookie_value and encrypted:
            cookie_value = decrypt_chrome_cookie(str(host), bytes(encrypted))
        if cookie_value:
            cookies[str(name)] = cookie_value
    return cookies


def auth_headers(cookies: dict[str, str]) -> dict[str, str]:
    headers = {
        'Origin': BASE,
        'Referer': BASE + '/',
        'User-Agent': 'Mozilla/5.0 (HubBot durable runtime)',
    }
    if cookies.get('community_estage_token'):
        headers['Estage-Authorization'] = cookies['community_estage_token']
    if cookies.get('userTokenID'):
        headers['Authorization'] = cookies['userTokenID']
    return headers


def upload_image(session: requests.Session, headers: dict[str, str], image_path: Path) -> dict[str, Any]:
    if not image_path.exists():
        return {'status': 'blocked', 'reason': f'image file not found: {image_path}', 'ok': False}
    content_type = 'image/png' if image_path.suffix.lower() == '.png' else 'image/jpeg' if image_path.suffix.lower() in {'.jpg', '.jpeg'} else 'application/octet-stream'
    with image_path.open('rb') as handle:
        response = session.post(
            f'{BASE}/api/{PROJECT}/upload',
            headers=headers,
            files={'image': (image_path.name, handle, content_type)},
            timeout=60,
        )
    try:
        data: Any = response.json()
    except Exception:
        data = {'text': response.text[:500]}
    image_url = ''
    if isinstance(data, dict):
        image_url = str(data.get('path') or data.get('url') or '')
    return {
        'status': 'uploaded' if response.ok and image_url else 'blocked',
        'ok': bool(response.ok and image_url),
        'http_status': response.status_code,
        'image_url': image_url,
        'response_keys': sorted(data.keys()) if isinstance(data, dict) else [],
        'reason': '' if response.ok and image_url else 'upload did not return a usable image URL',
    }


def create_thread(session: requests.Session, headers: dict[str, str], title: str, body_html: str, image_url: str | None, *, dry_run: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'title': title,
        'description': body_html,
        'pinned': False,
        'category': GENERAL_CATEGORY,
        'previewURL': image_url or None,
        'previewImage': None,
        'previewImages': [],
        'emailMembers': False,
        'scheduled': None,
        'mentions': [],
        'ruleKey': None,
        'channel': session.cookies.get('channel_id'),
        'origin': BASE,
        'groupName': 'HubActually',
    }
    duplicate_image_refs = 0
    if image_url:
        duplicate_image_refs = json.dumps(payload).count(image_url)
    redacted_payload = dict(payload)
    redacted_payload['description'] = f'<html body omitted; {len(body_html)} chars>'
    if dry_run:
        return {
            'status': 'dry_run_ready',
            'ok': True,
            'payload_redacted': redacted_payload,
            'duplicate_image_reference_count': duplicate_image_refs,
        }
    response = session.post(
        f'{BASE}/api/{PROJECT}/threads/create',
        headers={**headers, 'Content-Type': 'application/json'},
        data=json.dumps(payload),
        timeout=60,
    )
    try:
        data: Any = response.json()
    except Exception:
        data = {'text': response.text[:500]}
    thread_id = data.get('id') if isinstance(data, dict) else None
    return {
        'status': 'published' if response.ok else 'blocked',
        'ok': response.ok,
        'http_status': response.status_code,
        'thread_id': thread_id,
        'post_url': f'{BASE}/{thread_id}' if thread_id else None,
        'payload_redacted': redacted_payload,
        'duplicate_image_reference_count': duplicate_image_refs,
        'response_redacted': {k: data.get(k) for k in ['id', 'title', 'slug', 'createdAt'] if k in data} if isinstance(data, dict) else data,
    }


def merge_ledger(ledger_path: Path, result: dict[str, Any]) -> None:
    try:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    except Exception:
        ledger = {}
    ledger.update({
        'ai_news_publish_status': result.get('ai_news_publish_status'),
        'ai_news_thread_id': result.get('thread_id'),
        'ai_news_post_url': result.get('post_url'),
        'image_status': result.get('image_status'),
        'image_url': result.get('image_url'),
        'image_uploaded_url': result.get('image_url'),
        'published_at_utc': result.get('published_at_utc'),
    })
    evidence = ledger.get('evidence') if isinstance(ledger.get('evidence'), dict) else {}
    evidence['api_publisher_result_path'] = result.get('result_path')
    evidence['image_url'] = result.get('image_url')
    ledger['evidence'] = evidence
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Publish the daily HubActually AI-news post through the durable API path.')
    parser.add_argument('--title')
    parser.add_argument('--title-file')
    parser.add_argument('--body-html')
    parser.add_argument('--body-html-file')
    parser.add_argument('--body-text')
    parser.add_argument('--body-text-file')
    parser.add_argument('--image-path')
    parser.add_argument('--cookie-db')
    parser.add_argument('--output-dir', default=str(DEFAULT_LEDGER_DIR))
    parser.add_argument('--ledger', help='Optional JSON ledger to update after a real publish.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-text-only-fallback', action='store_true', help='Block instead of publishing text-only when image upload fails.')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    title = read_text_arg(args.title, args.title_file).strip()
    if args.body_html or args.body_html_file:
        body_html = read_text_arg(args.body_html, args.body_html_file).strip()
    else:
        body_text = read_text_arg(args.body_text, args.body_text_file).strip()
        body_html = text_to_html(body_text)
    result: dict[str, Any] = {
        'agent': 'HubBot',
        'component': 'api_ai_news_publisher',
        'created_at_utc': now_utc(),
        'dry_run': bool(args.dry_run),
        'title_present': bool(title),
        'body_html_chars': len(body_html),
        'image_path': args.image_path,
    }
    if not title or not body_html:
        result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'reason': 'title and body are required'})
    else:
        try:
            cookie_db = locate_cookie_db(args.cookie_db)
            cookies = get_hubactually_cookies(cookie_db, output_dir)
            session = requests.Session()
            session.cookies.update(cookies)
            headers = auth_headers(cookies)
            result['cookie_db_found'] = True
            result['hubactually_cookie_names'] = sorted(cookies.keys())
            result['auth_header_names'] = sorted(headers.keys())
            image_url = ''
            image_status = 'not_provided'
            if args.image_path:
                upload = {'status': 'dry_run_skipped', 'ok': True, 'image_url': 'DRY_RUN_IMAGE_URL'} if args.dry_run else upload_image(session, headers, Path(args.image_path))
                result['upload'] = upload
                image_url = '' if args.dry_run else str(upload.get('image_url') or '')
                image_status = 'uploaded' if upload.get('ok') else 'blocked'
            if args.image_path and image_status == 'blocked' and args.no_text_only_fallback:
                result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'image_status': 'blocked', 'reason': 'image upload failed and text-only fallback was disabled'})
            else:
                create = create_thread(session, headers, title, body_html, image_url or ('DRY_RUN_IMAGE_URL' if args.dry_run and args.image_path else None), dry_run=args.dry_run)
                result['create'] = create
                result['status'] = create['status']
                result['ai_news_publish_status'] = 'dry_run_ready' if args.dry_run else ('published' if create.get('ok') else 'blocked')
                result['image_status'] = image_status if image_status != 'blocked' else 'text_only'
                result['image_url'] = image_url
                result['thread_id'] = create.get('thread_id')
                result['post_url'] = create.get('post_url')
                result['published_at_utc'] = now_utc() if create.get('ok') and not args.dry_run else None
        except Exception as exc:
            result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'reason': f'{type(exc).__name__}: {exc}'})

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result_path = output_dir / f'{stamp}_api_ai_news_publisher_result.json'
    result['result_path'] = str(result_path)
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if args.ledger and not args.dry_run and result.get('ai_news_publish_status') in {'published', 'blocked'}:
        merge_ledger(Path(args.ledger), result)
    print(json.dumps({
        'status': result.get('status'),
        'ai_news_publish_status': result.get('ai_news_publish_status'),
        'image_status': result.get('image_status'),
        'post_url': result.get('post_url'),
        'result_path': str(result_path),
    }, indent=2))
    return 0 if result.get('status') in {'published', 'dry_run_ready'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
