#!/usr/bin/env python3
"""HubBot v2 permanent preflight.

This script performs secret-safe checks before the scheduled HubActually daily run
performs any community action. It never prints credential values. It writes JSON
and Markdown evidence that the agent can attach to the run ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
DEFAULT_TOKEN_FILE = Path('/home/ubuntu/.config/hubbot/doppler_service_token')
DEFAULT_GETRESPONSE_FILE = Path('/home/ubuntu/.config/hubbot/getresponse_api_key')
DEFAULT_BREVO_FILE = Path('/home/ubuntu/.config/hubbot/brevo_api_key')
DEFAULT_DASHBOARD_KEY_FILE = Path('/home/ubuntu/.config/hubbot/dashboard_api_key')
DEFAULT_OUTPUT_DIR = Path('/home/ubuntu/hubactually_hubbot_run_ledger')
DOPPLER_PROJECT = 'hubbot'
DOPPLER_CONFIG = 'prd'
REQUIRED_DOPPLER_SECRETS = ['HUBACTUALLY_HUBBOT_EMAIL', 'HUBACTUALLY_HUBBOT_PASSWORD']


def now_et() -> str:
    return datetime.now(ET).isoformat(timespec='seconds')


def command_exists(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'exists': False, 'path': str(path)}
    st = path.stat()
    return {
        'exists': True,
        'path': str(path),
        'mode_octal': oct(stat.S_IMODE(st.st_mode)),
        'size_bytes': st.st_size,
        'owner_uid': st.st_uid,
    }


def read_secret_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding='utf-8').strip()
    return value or None


def run_command(cmd: list[str], env: dict[str, str] | None = None, timeout: int = 20) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, f'{type(exc).__name__}'
    if completed.returncode == 0:
        return True, 'ok'
    stderr = (completed.stderr or completed.stdout or '').strip().splitlines()
    return False, stderr[-1][:240] if stderr else f'exit_{completed.returncode}'


def validate_doppler(token_file: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        'component': 'doppler_credentials',
        'required': True,
        'status': 'unknown',
        'details': [],
        'metadata': {
            'token_file': metadata(token_file),
            'env_present': bool(os.environ.get('DOPPLER_TOKEN') or os.environ.get('DOPPLER_SERVICE_TOKEN')),
        },
    }
    if not command_exists('doppler'):
        result['status'] = 'blocked'
        result['details'].append('Doppler CLI is not installed in the scheduled runtime.')
        result['remediation'] = 'Install Doppler CLI in the runtime image or run hubbot_bootstrap.sh before preflight.'
        return result
    token_source = 'environment' if (os.environ.get('DOPPLER_TOKEN') or os.environ.get('DOPPLER_SERVICE_TOKEN')) else 'file'
    token = os.environ.get('DOPPLER_TOKEN') or os.environ.get('DOPPLER_SERVICE_TOKEN') or read_secret_file(token_file)
    if not token:
        result['status'] = 'blocked'
        result['details'].append('Doppler service token is missing from environment and the fallback file is missing or empty.')
        result['remediation'] = f'Attach the Doppler connector/env secret or create {token_file} with the read-only Doppler service token and chmod 600 it.'
        return result
    if token_source == 'file' and token_file.exists():
        mode = stat.S_IMODE(token_file.stat().st_mode)
        if mode & 0o077:
            result['details'].append('Doppler token file permissions are broader than 600; runtime should tighten them before use.')
    env = os.environ.copy()
    env['DOPPLER_TOKEN'] = token
    validated: list[str] = []
    for name in REQUIRED_DOPPLER_SECRETS:
        ok, note = run_command(['doppler', 'secrets', 'get', name, '--project', DOPPLER_PROJECT, '--config', DOPPLER_CONFIG, '--plain'], env=env)
        if ok:
            validated.append(name)
        else:
            result['status'] = 'blocked'
            result['details'].append(f'Doppler secret {name} could not be retrieved: {note}')
            result['remediation'] = 'Verify the service token scope, project/config, and secret names.'
            return result
    result['status'] = 'passed'
    result['details'].append(f'Validated presence of {len(validated)} required HubActually login secrets without printing values; token source: {token_source}.')
    result['validated_secret_names'] = validated
    return result


def validate_getresponse(key_file: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        'component': 'getresponse_owner_alert',
        'required': False,
        'status': 'unknown',
        'details': [],
        'metadata': {'key_file': metadata(key_file), 'env_present': bool(os.environ.get('GETRESPONSE_API_KEY'))},
    }
    key = os.environ.get('GETRESPONSE_API_KEY') or read_secret_file(key_file)
    if not key:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append('No GetResponse API key was available in environment or configured key file.')
        result['remediation'] = f'Provide GETRESPONSE_API_KEY or create {key_file} with chmod 600.'
        return result
    req = urllib.request.Request('https://api.getresponse.com/v3/accounts', headers={'X-Auth-Token': f'api-key {key}'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result['status'] = 'passed' if 200 <= resp.status < 300 else 'warning'
            result['details'].append(f'GetResponse account endpoint responded with HTTP {resp.status}.')
    except urllib.error.HTTPError as exc:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append(f'GetResponse account endpoint returned HTTP {exc.code}.')
        result['remediation'] = 'Verify GetResponse API key validity and account permissions.'
    except Exception as exc:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append(f'GetResponse endpoint check failed: {type(exc).__name__}.')
        result['remediation'] = 'Verify outbound network access and GetResponse availability.'
    return result


def validate_brevo(key_file: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        'component': 'brevo_owner_alert_fallback',
        'required': False,
        'status': 'unknown',
        'details': [],
        'metadata': {'key_file': metadata(key_file), 'env_present': bool(os.environ.get('BREVO_API_KEY'))},
    }
    key = os.environ.get('BREVO_API_KEY') or read_secret_file(key_file)
    if not key:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append('No Brevo direct-email API key was available in environment or configured key file.')
        result['remediation'] = f'Provide BREVO_API_KEY or create {key_file} with chmod 600 to enable the direct-email fallback.'
        return result
    req = urllib.request.Request('https://api.brevo.com/v3/account', headers={'api-key': key, 'accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result['status'] = 'passed' if 200 <= resp.status < 300 else 'warning'
            result['details'].append(f'Brevo account endpoint responded with HTTP {resp.status}; direct single-recipient owner-alert fallback is available.')
    except urllib.error.HTTPError as exc:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append(f'Brevo account endpoint returned HTTP {exc.code}.')
        result['remediation'] = 'Verify Brevo API key validity and sender-domain permissions.'
    except Exception as exc:
        result['status'] = 'blocked_if_alert_required'
        result['details'].append(f'Brevo endpoint check failed: {type(exc).__name__}.')
        result['remediation'] = 'Verify outbound network access and Brevo availability.'
    return result


def validate_dashboard(repo_root: Path, key_file: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        'component': 'dashboard_update',
        'required': True,
        'status': 'unknown',
        'details': [],
        'metadata': {
            'repo_root': str(repo_root),
            'repo_exists': (repo_root / '.git').exists(),
            'run_data_json_exists': (repo_root / 'run-data.json').exists(),
            'latest_run_json_exists': (repo_root / 'client/public/latest-run.json').exists(),
            'dashboard_url_env_present': bool(os.environ.get('HUBBOT_DASHBOARD_URL')),
            'api_key_env_or_file_present': bool(os.environ.get('HUBBOT_API_KEY') or read_secret_file(key_file)),
        },
    }
    dashboard_url = os.environ.get('HUBBOT_DASHBOARD_URL')
    api_key = os.environ.get('HUBBOT_API_KEY') or read_secret_file(key_file)
    if dashboard_url and api_key:
        req = urllib.request.Request(dashboard_url.rstrip('/') + '/api/run-data', headers={'x-hubbot-api-key': api_key})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if 200 <= resp.status < 300:
                    result['status'] = 'passed_endpoint'
                    result['details'].append(f'Dashboard API endpoint reachable with HTTP {resp.status}.')
                    return result
        except Exception as exc:
            result['details'].append(f'Dashboard API endpoint check failed; repository fallback will be used: {type(exc).__name__}.')
    if (repo_root / '.git').exists() and (repo_root / 'run-data.json').exists() and (repo_root / 'client/public/latest-run.json').exists():
        result['status'] = 'passed_repository_fallback'
        result['details'].append('Dashboard repository fallback files are available and can be updated/committed.')
    else:
        result['status'] = 'blocked'
        result['details'].append('Neither dashboard API credentials nor dashboard repository fallback files are available.')
        result['remediation'] = 'Clone v3ads/hubbot-dashboard or configure HUBBOT_DASHBOARD_URL plus HUBBOT_API_KEY.'
    return result


def validate_git_repo(repo_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {'component': 'github_ledger_repository', 'required': True, 'status': 'unknown', 'details': []}
    if not (repo_root / '.git').exists():
        result['status'] = 'blocked'
        result['details'].append('Dashboard Git repository is not cloned in the runtime.')
        result['remediation'] = 'Run gh repo clone v3ads/hubbot-dashboard /home/ubuntu/hubbot-dashboard before finalization.'
        return result
    ok, note = run_command(['git', '-C', str(repo_root), 'status', '--short'])
    if ok:
        result['status'] = 'passed'
        result['details'].append('Dashboard Git repository is available for durable fallback commits.')
    else:
        result['status'] = 'blocked'
        result['details'].append(f'Git status check failed: {note}')
    return result


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        '# HubBot Preflight Report',
        '',
        f"**Generated at:** {report['generated_at_et']}",
        '',
        '| Component | Required | Status | Details |',
        '|---|---:|---|---|',
    ]
    for check in report['checks']:
        details = '<br>'.join(check.get('details') or []) or 'No detail.'
        lines.append(f"| `{check['component']}` | {str(check.get('required', False)).lower()} | **{check['status']}** | {details} |")
    if report['hard_blockers']:
        lines.extend(['', '## Hard Blockers', ''])
        for item in report['hard_blockers']:
            lines.append(f'- {item}')
    if report['warnings']:
        lines.extend(['', '## Warnings', ''])
        for item in report['warnings']:
            lines.append(f'- {item}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Run HubBot secret-safe preflight checks.')
    parser.add_argument('--repo-root', default='/home/ubuntu/hubbot-dashboard')
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument('--token-file', default=str(DEFAULT_TOKEN_FILE))
    parser.add_argument('--getresponse-key-file', default=str(DEFAULT_GETRESPONSE_FILE))
    parser.add_argument('--brevo-key-file', default=str(DEFAULT_BREVO_FILE))
    parser.add_argument('--dashboard-key-file', default=str(DEFAULT_DASHBOARD_KEY_FILE))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(ET).date().isoformat()

    checks = [
        validate_git_repo(Path(args.repo_root)),
        validate_doppler(Path(args.token_file)),
        validate_getresponse(Path(args.getresponse_key_file)),
        validate_brevo(Path(args.brevo_key_file)),
        validate_dashboard(Path(args.repo_root), Path(args.dashboard_key_file)),
    ]
    hard_blockers = []
    warnings = []
    for check in checks:
        status = check.get('status')
        if check.get('required') and status not in {'passed', 'passed_endpoint', 'passed_repository_fallback'}:
            hard_blockers.extend(check.get('details') or [f"{check['component']} failed"])
        elif str(status).startswith('blocked') or status == 'warning':
            warnings.extend(check.get('details') or [f"{check['component']} warning"])
    report = {
        'agent_name': 'HubBot',
        'agent_version': 'v2',
        'generated_at_et': now_et(),
        'status': 'passed' if not hard_blockers else 'blocked',
        'checks': checks,
        'hard_blockers': hard_blockers,
        'warnings': warnings,
        'safe_to_publish_or_comment': not hard_blockers,
        'safe_to_send_owner_alert_if_required': any(c['component'] in {'getresponse_owner_alert', 'brevo_owner_alert_fallback'} and c['status'] == 'passed' for c in checks),
    }
    json_path = output_dir / f'{date}_preflight.json'
    md_path = output_dir / f'{date}_preflight.md'
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    write_markdown(report, md_path)
    print(json.dumps({'status': report['status'], 'json_path': str(json_path), 'markdown_path': str(md_path), 'hard_blocker_count': len(hard_blockers)}, indent=2))
    return 0 if not hard_blockers else 2


if __name__ == '__main__':
    raise SystemExit(main())
