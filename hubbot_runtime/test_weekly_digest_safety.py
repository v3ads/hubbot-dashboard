#!/usr/bin/env python3
"""Deterministic regression tests for HubBot weekly digest safety gates."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import hubbot_send_weekly_digest as digest


def write_ledger(tmp: Path, payload: dict) -> Path:
    path = tmp / 'ledger.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))



def run_cli(args: list[str]) -> int:
    import sys
    old = sys.argv[:]
    try:
        sys.argv = ['hubbot_send_weekly_digest.py'] + args
        return digest.main()
    finally:
        sys.argv = old


def test_non_saturday_is_not_sent_and_updates_ledger_cli() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ledger_path = write_ledger(tmp, {'run_date': '2026-06-05'})
        code = run_cli(['--ledger', str(ledger_path), '--output-dir', str(tmp), '--now-et', '2026-06-05T09:00:00-04:00'])
        ledger = read(ledger_path)
        assert code == 0
        assert ledger['saturday_digest_status'] == 'not_saturday'
        assert 'Actual America/New_York date is not Saturday' in ledger['saturday_digest_reason']
        assert 'saturday_digest_result_path' in ledger['evidence']


def test_saturday_missing_key_blocks_and_requires_owner_alert() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ledger_path = write_ledger(tmp, {'run_date': '2026-06-05', 'blockers': []})
        missing_key_file = tmp / 'missing_key'
        with mock.patch.dict('os.environ', {'GETRESPONSE_API_KEY': ''}, clear=False):
            code = run_cli(['--ledger', str(ledger_path), '--output-dir', str(tmp), '--getresponse-key-file', str(missing_key_file), '--now-et', '2026-06-06T11:00:00-04:00'])
        ledger = read(ledger_path)
        assert code == 2
        assert ledger['saturday_digest_status'] == 'blocked'
        assert 'GetResponse API key is unavailable' in ledger['saturday_digest_reason']
        assert ledger['owner_alert_required'] is True
        assert any('Saturday weekly digest blocked' in item for item in ledger['blockers'])


def test_saturday_before_10_dry_run_schedules_after_resolution() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        key_file = tmp / 'key'
        key_file.write_text('fake-key', encoding='utf-8')
        ledger_path = write_ledger(tmp, {'run_date': '2026-06-06', 'ai_news_title': 'Useful AI item'})
        fake_resolution = {
            'status': 'resolved',
            '_from_field_id': 'from-1',
            '_campaign_id': 'camp-1',
            '_template_id': 'tpl-1',
            'campaign_name': 'hubactually',
            'template_name': 'community',
            'from_field': {'email': 'ayman@hubactually.com'},
        }
        with mock.patch.object(digest, 'resolve_getresponse', return_value=fake_resolution):
            code = run_cli(['--ledger', str(ledger_path), '--output-dir', str(tmp), '--getresponse-key-file', str(key_file), '--now-et', '2026-06-06T09:15:00-04:00', '--dry-run'])
        ledger = read(ledger_path)
        assert code == 0
        assert ledger['saturday_digest_status'] == 'dry_run_ready'
        assert ledger['saturday_digest_scheduled_for_et'].startswith('2026-06-06T10:00:00')


def test_digest_content_always_contains_required_ps() -> None:
    subject, text_body, html_body = digest.build_digest_content({'run_date': '2026-06-06'})
    assert 'HubActually weekly community digest' in subject
    assert digest.PS_LINE in text_body
    assert '1:00 PM Eastern' in html_body


if __name__ == '__main__':
    tests = [
        test_non_saturday_is_not_sent_and_updates_ledger_cli,
        test_saturday_missing_key_blocks_and_requires_owner_alert,
        test_saturday_before_10_dry_run_schedules_after_resolution,
        test_digest_content_always_contains_required_ps,
    ]
    for test in tests:
        test()
    print(f'weekly_digest_tests_passed={len(tests)}')
