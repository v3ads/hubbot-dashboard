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
import random
import re
import shutil
import sqlite3
import string
import sys
import tempfile
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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


URL_RE = re.compile(r'https?://[^\s<)"\']+', re.I)


def text_to_html(text: str) -> str:
    paragraphs = [p.strip() for p in text.replace('\r\n', '\n').split('\n\n') if p.strip()]
    parts = []
    for p in paragraphs:
        escaped = html.escape(p).replace(chr(10), '<br>')
        # Wrap plain-text URLs in <a> tags so the platform renders them as clickable hyperlinks.
        def _make_link(m: re.Match) -> str:
            url = m.group(0)
            return f'<a href="{url}" target="_blank">{url}</a>'
        escaped = URL_RE.sub(_make_link, escaped)
        parts.append(f'<p>{escaped}</p>')
    return ''.join(parts)


PARAGRAPH_RE = re.compile(r'<p\b[^>]*>(.*?)</p>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


def visible_text(fragment: str) -> str:
    return html.unescape(TAG_RE.sub(' ', fragment)).replace('\xa0', ' ')


def source_link_spacing_qa(body_html: str) -> dict[str, Any]:
    """Verify that source links are isolated from following prose.

    HubActually's rich-text feed has previously rendered a source URL and the
    following community question as one run of text when the URL was not placed
    in its own paragraph/line. Treat that as a publish blocker. A valid source
    link is either a paragraph whose visible text is only an optional "Source:"
    label plus a URL, or a paragraph that contains an anchor/URL and no other
    post content after the URL.
    """
    urls = URL_RE.findall(body_html or '')
    paragraphs = PARAGRAPH_RE.findall(body_html or '')
    url_paragraphs: list[str] = []
    failures: list[str] = []
    for para in paragraphs or [body_html]:
        if URL_RE.search(para):
            url_paragraphs.append(para)
            text_only = ' '.join(visible_text(para).split())
            cleaned = re.sub(r'^Source\s*:\s*', '', text_only, flags=re.I).strip()
            cleaned = re.sub(r'^Source\s+', '', cleaned, flags=re.I).strip()
            cleaned = URL_RE.sub('', cleaned).strip(' .;:-–—|')
            if cleaned:
                failures.append('source URL paragraph contains additional non-source text')
            if re.search(r'Community\s+question|Question\s*:', text_only, re.I):
                failures.append('community question appears in the same paragraph as the source URL')
    if not urls:
        failures.append('no source URL found')
    if not url_paragraphs:
        failures.append('no paragraph or line containing the source URL found')
    return {
        'ok': not failures,
        'source_url_count': len(urls),
        'source_url_paragraph_count': len(url_paragraphs),
        'failures': sorted(set(failures)),
    }


def prepublish_payload_qa(payload: dict[str, Any], body_html: str, image_url: str | None) -> dict[str, Any]:
    payload_text = json.dumps(payload, ensure_ascii=False)
    image_count = payload_text.count(image_url) if image_url else 0
    link_qa = source_link_spacing_qa(body_html)
    failures: list[str] = []
    if not payload.get('title'):
        failures.append('title missing')
    if not image_url:
        failures.append('image URL missing; text-only publishing is disabled')
    # The platform displays images via previewImages array, not previewURL.
    # Verify previewImages contains the uploaded image URL.
    preview_images = payload.get('previewImages') or []
    preview_image_urls = [img.get('url', '') for img in preview_images if isinstance(img, dict)]
    if image_url and image_url not in preview_image_urls:
        failures.append('uploaded image URL is not in previewImages array')
    if payload.get('previewImage') is not None:
        failures.append('previewImage must be null')
    if payload.get('previewURL') not in (None, ''):
        failures.append('previewURL must be empty; use previewImages instead')
    if not link_qa.get('ok'):
        failures.extend(link_qa.get('failures') or ['source link spacing failed'])
    return {
        'ok': not failures,
        'image_url_count_in_payload': image_count,
        'source_link_spacing_qa': link_qa,
        'failures': sorted(set(failures)),
    }



STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'how', 'in', 'into',
    'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'with', 'without', 'your',
    'you', 'hubactually', 'source', 'general', 'post', 'posts', 'community', 'business',
    'businesses', 'small', 'ai', 'artificial', 'intelligence',
    # Common English function/filler words that cause false-positive topic matches
    'about', 'after', 'all', 'also', 'but', 'can', 'day', 'days', 'did', 'do', 'does',
    'even', 'get', 'got', 'has', 'have', 'her', 'him', 'his', 'if', 'its', 'just',
    'know', 'like', 'make', 'more', 'most', 'much', 'need', 'new', 'not', 'now',
    'one', 'only', 'our', 'out', 'over', 'own', 'same', 'see', 'she', 'so', 'some',
    'than', 'their', 'them', 'then', 'there', 'they', 'time', 'tool', 'tools', 'up',
    'use', 'used', 'using', 'was', 'way', 'we', 'were', 'what', 'when', 'where',
    'which', 'who', 'will', 'would', 'yet'
}


def normalize_url_for_duplicate(url: str) -> str:
    """Normalize source URLs so tracking parameters do not bypass duplicate checks."""
    cleaned = html.unescape(url or '').strip().rstrip('.,);]\'\"')
    if not cleaned:
        return ''
    parts = urlsplit(cleaned)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith(('utm_', 'fbclid', 'gclid'))]
    netloc = parts.netloc.lower().removeprefix('www.')
    path = re.sub(r'/+$', '', parts.path or '/')
    return urlunsplit((parts.scheme.lower() or 'https', netloc, path, urlencode(query, doseq=True), ''))


def normalize_text_for_duplicate(value: str) -> str:
    value = html.unescape(value or '')
    value = TAG_RE.sub(' ', value)
    value = re.sub(r'[-_/]+', ' ', value.lower())
    value = re.sub(r'[^a-z0-9\s]+', ' ', value)
    return ' '.join(value.split())


def duplicate_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in normalize_text_for_duplicate(value).split():
        if len(token) < 3 or token in STOPWORDS:
            continue
        if token.endswith('ies') and len(token) > 4:
            token = token[:-3] + 'y'
        elif token.endswith('s') and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def extract_source_urls(body_html: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for raw in URL_RE.findall(body_html or ''):
        normalized = normalize_url_for_duplicate(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def extract_recent_text_candidates(raw_html: str) -> list[str]:
    """Extract likely recent feed titles/text snippets without exposing cookies or secrets."""
    raw_html = html.unescape(raw_html or '')
    candidates: list[str] = []
    candidates.extend(re.findall(r'>([^<>]{20,180})<', raw_html))
    candidates.extend(re.findall(r'"([^"\\]{20,180})"', raw_html))
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        item = ' '.join(TAG_RE.sub(' ', item).split())
        if not item or len(item) < 20:
            continue
        low = item.lower()
        if any(skip in low for skip in ['password', 'authorization', 'cookie', 'csrf', 'webpack', '__nuxt']):
            continue
        key = normalize_text_for_duplicate(item)
        if key and key not in seen:
            seen.add(key)
            cleaned.append(item)
    return cleaned[:500]


def duplicate_post_guard(session: requests.Session, headers: dict[str, str], title: str, body_html: str) -> dict[str, Any]:
    """Block publishing when the candidate matches a recent General-feed source, title, or topic.

    The guard is intentionally conservative. If the recent feed cannot be read, publishing is blocked
    because avoiding duplicate community posts is safer than guessing.
    """
    result: dict[str, Any] = {
        'ok': False,
        'status': 'blocked',
        'candidate_source_urls': extract_source_urls(body_html),
        'candidate_title_normalized': normalize_text_for_duplicate(title),
        'matches': [],
    }
    try:
        response = session.get(BASE + '/', headers=headers, timeout=30)
    except Exception as exc:
        result['reason'] = f'duplicate guard could not inspect recent feed: {type(exc).__name__}'
        return result
    result['http_status'] = response.status_code
    if not response.ok or not response.text:
        result['reason'] = f'duplicate guard could not inspect recent feed: HTTP {response.status_code}'
        return result

    raw = response.text
    raw_urls = {normalize_url_for_duplicate(u) for u in URL_RE.findall(raw)}
    raw_urls.discard('')
    for source_url in result['candidate_source_urls']:
        if source_url in raw_urls:
            result['matches'].append({'type': 'same_source_url', 'value': source_url})

    title_norm = result['candidate_title_normalized']
    page_norm = normalize_text_for_duplicate(raw)
    if title_norm and title_norm in page_norm:
        result['matches'].append({'type': 'same_title', 'value': title})

    title_tokens = duplicate_tokens(title)
    body_tokens = duplicate_tokens(visible_text(body_html))
    candidate_tokens = title_tokens | {t for t in body_tokens if t not in {'news', 'today', 'question', 'members'}}
    semantic_matches: list[dict[str, Any]] = []
    if len(candidate_tokens) >= 4:
        for snippet in extract_recent_text_candidates(raw):
            snippet_tokens = duplicate_tokens(snippet)
            if not snippet_tokens:
                continue
            overlap = sorted(candidate_tokens & snippet_tokens)
            score = len(overlap) / max(1, min(len(candidate_tokens), len(snippet_tokens)))
            if len(overlap) >= 4 and score >= 0.40:
                semantic_matches.append({
                    'type': 'same_or_near_duplicate_topic',
                    'overlap_score': round(score, 3),
                    'overlap_terms': overlap[:12],
                    'snippet': snippet[:180],
                })
    result['matches'].extend(semantic_matches[:5])
    if result['matches']:
        result['reason'] = 'duplicate guard blocked publish: candidate matches a recent source, title, or AI-news topic'
        return result
    result['ok'] = True
    result['status'] = 'passed'
    result['reason'] = 'no duplicate source, title, or near-duplicate topic found in recent feed'
    return result


def resolve_channel_id(session: requests.Session, headers: dict[str, str]) -> str | None:
    """Resolve the live channel id from cookies or the community page state before creating a thread.

    The HubActually frontend falls back to the literal channel value ``main`` when
    no selected-channel object is present. Current authenticated page state often
    stores existing General posts with ``channel`` as null, so the absence of a
    page-state channel must not produce an invalid API payload. Returning ``main``
    matches the shipped frontend bundle default and keeps the publisher fail-closed
    for true read/auth failures while preventing a known null-channel regression.
    """
    cookie_value = session.cookies.get('channel_id')
    if cookie_value:
        return str(cookie_value)
    try:
        response = session.get(BASE + '/', headers=headers, timeout=30)
    except Exception:
        return None
    if not response.ok:
        return None
    raw = html.unescape(response.text or '')
    patterns = [
        r'"channel_id"\s*:\s*"([^"\\]+)"',
        r'"channelId"\s*:\s*"([^"\\]+)"',
        r'"channel"\s*:\s*"([^"\\]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return match.group(1)
    if 'HubActually' in raw and 'General' in raw:
        return 'main'
    return None

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


def get_live_browser_cookies() -> dict[str, str]:
    """Read current HubActually cookies from the already-authenticated browser page via local CDP.

    Values are returned only in memory and must never be logged. If CDP is unavailable,
    the publisher falls back to the Chromium cookie database so scheduled runs remain
    compatible with non-debug browser sessions.
    """
    try:
        import websocket  # type: ignore
        targets = json.loads(urllib.request.urlopen('http://127.0.0.1:9222/json', timeout=5).read().decode('utf-8'))
        target = next((t for t in targets if 'community.hubactually.com' in str(t.get('url', ''))), None)
        if not target or not target.get('webSocketDebuggerUrl'):
            return {}
        ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=10, suppress_origin=True)
        try:
            seq = 1
            expr = """(() => Object.fromEntries(document.cookie.split('; ').filter(Boolean).map(s => { const i=s.indexOf('='); return [decodeURIComponent(s.slice(0,i)), decodeURIComponent(s.slice(i+1))]; })))()"""
            ws.send(json.dumps({'id': seq, 'method': 'Runtime.evaluate', 'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get('id') == seq:
                    value = msg.get('result', {}).get('result', {}).get('value', {})
                    return {str(k): str(v) for k, v in (value or {}).items() if v}
        finally:
            ws.close()
    except Exception:
        return {}


def auth_headers(cookies: dict[str, str]) -> dict[str, str]:
    headers = {
        'Origin': BASE,
        'Referer': BASE + '/',
        'User-Agent': 'Mozilla/5.0 (HubBot durable runtime)',
    }
    if cookies.get('community_estage_token'):
        headers['Estage-Authorization'] = cookies['community_estage_token']
        headers['Authorization'] = cookies['community_estage_token']
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


def _make_image_id(length: int = 20) -> str:
    """Generate a Cloudinary-style alphanumeric ID matching the platform's format."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))


def create_thread(session: requests.Session, headers: dict[str, str], title: str, body_html: str, image_url: str | None, *, dry_run: bool, channel_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'title': title,
        'description': body_html,
        'pinned': False,
        'category': GENERAL_CATEGORY,
        'previewURL': '',
        'previewImage': None,
        'previewImages': [{'id': _make_image_id(), 'url': image_url, 'type': 'image'}] if image_url else [],
        'emailMembers': False,
        'scheduled': None,
        'mentions': [],
        'ruleKey': None,
        'channel': channel_id or session.cookies.get('channel_id'),
        'origin': BASE,
        'groupName': 'HubActually',
    }
    prepublish_qa = prepublish_payload_qa(payload, body_html, image_url)
    if not payload.get('channel'):
        prepublish_qa['ok'] = False
        prepublish_qa.setdefault('failures', []).append('channel id missing; refusing to create thread without validated channel/auth context')
    duplicate_image_refs = prepublish_qa['image_url_count_in_payload']
    redacted_payload = dict(payload)
    redacted_payload['description'] = f'<html body omitted; {len(body_html)} chars>'
    if not prepublish_qa.get('ok'):
        return {
            'status': 'blocked',
            'ok': False,
            'payload_redacted': redacted_payload,
            'duplicate_image_reference_count': duplicate_image_refs,
            'prepublish_qa': prepublish_qa,
            'reason': 'pre-publish QA failed: image and source-link spacing are required',
        }
    if dry_run:
        return {
            'status': 'dry_run_ready',
            'ok': True,
            'payload_redacted': redacted_payload,
            'duplicate_image_reference_count': duplicate_image_refs,
            'prepublish_qa': prepublish_qa,
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
    parser.add_argument('--no-text-only-fallback', action='store_true', help='Deprecated: image is always required; retained for CLI compatibility.')
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
            # Prefer the injected env-var token (set in Doppler) over the browser cookie DB.
            # This is the permanent fix for scheduled runs which start in a fresh sandbox
            # with no browser cookies present.
            env_token = os.environ.get('COMMUNITY_ESTAGE_TOKEN', '').strip()
            # Fallback: fetch the token from the HubBot dashboard API
            # (used when the env var is not set but HUBBOT_API_KEY + HUBBOT_DASHBOARD_URL are available)
            if not env_token:
                dashboard_url = os.environ.get('HUBBOT_DASHBOARD_URL', 'https://hubbot-dashboard.manus.space').rstrip('/')
                hubbot_api_key = os.environ.get('HUBBOT_API_KEY', '').strip()
                if hubbot_api_key:
                    try:
                        resp = requests.get(
                            f'{dashboard_url}/api/community-token',
                            headers={'x-hubbot-api-key': hubbot_api_key},
                            timeout=10,
                        )
                        if resp.ok:
                            env_token = resp.json().get('token', '').strip()
                            if env_token:
                                result['cookie_source_detail'] = 'dashboard_api'
                    except Exception as fetch_exc:
                        result['dashboard_token_fetch_error'] = f'{type(fetch_exc).__name__}: {fetch_exc}'
            if env_token:
                cookies: dict[str, str] = {'community_estage_token': env_token}
                result['cookie_source'] = 'env_var_or_dashboard'
                result['cookie_db_found'] = False
                result['live_browser_cookies_used'] = False
            else:
                cookie_db = locate_cookie_db(args.cookie_db)
                cookies = get_hubactually_cookies(cookie_db, output_dir)
                live_cookies = get_live_browser_cookies()
                if live_cookies:
                    cookies.update(live_cookies)
                    result['live_browser_cookies_used'] = True
                    result['live_browser_cookie_names'] = sorted(live_cookies.keys())
                else:
                    result['live_browser_cookies_used'] = False
                result['cookie_source'] = 'browser_db'
                result['cookie_db_found'] = True
            session = requests.Session()
            session.cookies.update(cookies)
            headers = auth_headers(cookies)
            result['hubactually_cookie_names'] = sorted(cookies.keys())
            result['auth_header_names'] = sorted(headers.keys())
            duplicate_guard = duplicate_post_guard(session, headers, title, body_html)
            result['duplicate_guard'] = duplicate_guard
            channel_id = resolve_channel_id(session, headers)
            result['channel_id_resolved'] = bool(channel_id)
            image_url = ''
            image_status = 'not_provided'
            if not duplicate_guard.get('ok'):
                result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'image_status': 'blocked', 'reason': duplicate_guard.get('reason') or 'duplicate guard blocked publish'})
            elif not channel_id:
                result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'image_status': 'blocked', 'reason': 'channel id could not be resolved; refusing to publish with invalid API payload'})
            elif not args.image_path:
                result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'image_status': 'blocked', 'reason': 'image path is required; text-only publishing is disabled'})
            else:
                upload = {'status': 'dry_run_skipped', 'ok': True, 'image_url': 'DRY_RUN_IMAGE_URL'} if args.dry_run else upload_image(session, headers, Path(args.image_path))
                result['upload'] = upload
                image_url = 'DRY_RUN_IMAGE_URL' if args.dry_run else str(upload.get('image_url') or '')
                image_status = 'uploaded' if upload.get('ok') else 'blocked'
                if image_status == 'blocked':
                    result.update({'status': 'blocked', 'ai_news_publish_status': 'blocked', 'image_status': 'blocked', 'reason': 'image upload failed; text-only publishing is disabled'})
                else:
                    create = create_thread(session, headers, title, body_html, image_url, dry_run=args.dry_run, channel_id=channel_id)
                    result['create'] = create
                    result['prepublish_qa'] = create.get('prepublish_qa')
                    result['status'] = create['status']
                    result['ai_news_publish_status'] = 'dry_run_ready' if args.dry_run and create.get('ok') else ('published' if create.get('ok') else 'blocked')
                    result['image_status'] = image_status if create.get('ok') else 'blocked'
                    result['image_url'] = '' if args.dry_run else image_url
                    result['thread_id'] = create.get('thread_id')
                    result['post_url'] = create.get('post_url')
                    result['published_at_utc'] = now_utc() if create.get('ok') and not args.dry_run else None
                    if not create.get('ok'):
                        result['reason'] = create.get('reason') or 'thread creation failed or pre-publish QA blocked publish'
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
