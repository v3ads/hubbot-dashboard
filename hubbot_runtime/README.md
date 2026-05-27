# HubBot Permanent Runtime Layer

This directory contains the durable runtime controls for **HubBot v2**, the scheduled HubActually community-admin agent. The goal is to prevent daily manual repair by making each scheduled run start with a secret-safe preflight, finish with a dashboard/ledger finalizer, and preserve the active run contract inside the dashboard repository.

## Runtime Contract

Every scheduled run should first clone or update this repository, then run `hubbot_runtime/hubbot_preflight.py`. The preflight validates the components that historically blocked the automation: Doppler credential retrieval, the dashboard update path, GitHub-backed ledger fallback, and GetResponse availability for owner alerts. The script never prints secret values; it only reports whether required values can be retrieved or whether a safe blocker exists.

If preflight reports hard blockers, HubBot must not publish, comment, welcome, or perform authenticated community actions. It should continue only with safe non-authenticated work, record the blocker, and finalize the run ledger/dashboard status. If preflight passes, HubBot may proceed through the approved daily playbook and then call `hubbot_finalize.py` with the run ledger path.

| File | Purpose |
|---|---|
| `hubbot_bootstrap.sh` | Updates this repository and runs the preflight in one command. |
| `hubbot_preflight.py` | Performs secret-safe checks for Doppler, GitHub/dashboard fallback, dashboard API, and GetResponse. |
| `hubbot_finalize.py` | Converts a run ledger into dashboard-compatible JSON and updates `run-data.json` plus `client/public/latest-run.json`. |
| `README.md` | Documents the permanent operating model. |

## Scheduled Run Sequence

The scheduled playbook should use this sequence at the beginning and end of every run. The bootstrap also installs the official Doppler CLI through Doppler’s Ubuntu apt repository if the binary is absent, and it accepts either `DOPPLER_TOKEN` or `DOPPLER_SERVICE_TOKEN` from scheduled connectors:

```bash
bash /home/ubuntu/hubbot-dashboard/hubbot_runtime/hubbot_bootstrap.sh
```

At the end of the run, after the JSON ledger exists:

```bash
python3.11 /home/ubuntu/hubbot-dashboard/hubbot_runtime/hubbot_finalize.py \
  --ledger /home/ubuntu/hubactually_hubbot_run_ledger/YYYY-MM-DD_hubbot_run.json \
  --repo-root /home/ubuntu/hubbot-dashboard \
  --commit
```

## Secret Storage Requirements

Secrets must stay outside GitHub and outside user-visible reports. The expected local files are:

| Secret | Preferred location | Permission |
|---|---|---:|
| Doppler service token | `DOPPLER_TOKEN`, `DOPPLER_SERVICE_TOKEN`, or `/home/ubuntu/.config/hubbot/doppler_service_token` | `600` for file fallback |
| GetResponse API key fallback | `/home/ubuntu/.config/hubbot/getresponse_api_key` | `600` |
| Dashboard API key fallback | `/home/ubuntu/.config/hubbot/dashboard_api_key` | `600` |

The Doppler token must be scoped read-only to the `hubbot` / `prd` secrets used by the dedicated HubBot account. The runtime should prefer environment variables or connector-backed credentials when available, but the files above are the durable fallback for unattended scheduled execution.
