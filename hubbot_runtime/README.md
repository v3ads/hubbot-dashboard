# HubBot Permanent Runtime Layer

This directory contains the durable runtime controls for **HubBot v2**, the scheduled HubActually community-admin agent. The goal is to prevent daily manual repair by making each scheduled run start with a secret-safe preflight, finish with a dashboard/ledger finalizer, and preserve the active run contract inside the dashboard repository.

## Runtime Contract

Every scheduled run should first clone or update this repository, then run `hubbot_runtime/hubbot_preflight.py`. The preflight validates the components that historically blocked the automation: Doppler credential retrieval, the dashboard update path, GitHub-backed ledger fallback, GetResponse availability for owner alerts, and the direct-email fallback used when GetResponse cannot safely deliver a single-recipient alert. The script never prints secret values; it only reports whether required values can be retrieved or whether a safe blocker exists.

If preflight reports hard blockers, HubBot must not publish, comment, welcome, or perform authenticated community actions. It should continue only with safe non-authenticated work, record the blocker, and finalize the run ledger/dashboard status. If preflight passes, HubBot may proceed through the approved daily playbook and then call `hubbot_finalize.py` with the run ledger path.

| File | Purpose |
|---|---|
| `hubbot_bootstrap.sh` | Updates this repository and runs the preflight in one command. |
| `hubbot_preflight.py` | Performs secret-safe checks for Doppler, GitHub/dashboard fallback, dashboard API, GetResponse, and Brevo direct-email fallback. |
| `hubbot_heartbeat.py` | Posts a secret-safe `running` heartbeat to the dashboard at the start of each run so fresh-sandbox runs are observable before community actions begin. |
| `hubbot_publish_ai_news.py` | Legacy API publisher retained only for evidence and fallback investigation; the playbook now requires the authenticated browser composer for AI-news publishing. |
| `hubbot_owner_alert.py` | Sends required single-recipient owner alerts through a non-mutating GetResponse path or the configured direct-email fallback. |
| `hubbot_send_weekly_digest.py` | Sends or schedules the Saturday HubActually weekly digest through GetResponse using actual America/New_York time, recipient list `hubactually`, sender `ayman@hubactually.com`, and the saved `community` template. |
| `hubbot_finalize.py` | Converts a run ledger into dashboard-compatible JSON, invokes the owner-alert helper when required, and updates `run-data.json` plus `client/public/latest-run.json`. |
| `README.md` | Documents the permanent operating model. |

## Scheduled Run Sequence

The scheduled playbook should use this sequence at the beginning and end of every run. The bootstrap also installs the official Doppler CLI through Doppler’s Ubuntu apt repository if the binary is absent, ensures the Chromium cookie decryption dependency is available, and accepts either `DOPPLER_TOKEN` or `DOPPLER_SERVICE_TOKEN` from scheduled connectors:

```bash
bash /home/ubuntu/hubbot-dashboard/hubbot_runtime/hubbot_bootstrap.sh
```

Immediately after bootstrap/preflight succeeds, post the start-of-run heartbeat before opening the community browser workflow:

```bash
python3.11 /home/ubuntu/hubbot-dashboard/hubbot_runtime/hubbot_heartbeat.py \
  --repo-root /home/ubuntu/hubbot-dashboard
```

The heartbeat writes `/home/ubuntu/hubactually_hubbot_run_ledger/YYYY-MM-DD_heartbeat.json` and posts a `running` dashboard state. It must not be committed as the final run state; the end-of-run finalizer remains authoritative and replaces the same-date heartbeat entry in run history.

The daily AI-news post should be published through the authenticated HubActually browser composer after the title, body, and cover image are prepared. Browser submission must only proceed after the generated image is visibly attached, the General channel is selected, and the source link has the required trailing space for clickable rendering.

On Saturdays, after community work is complete and before the dashboard update, run `hubbot_send_weekly_digest.py --ledger /path/to/run_ledger.json`. The helper uses the actual `America/New_York` date and time, not the nominal run date, to decide whether to send immediately, schedule for 10:00 AM Eastern, mark `not_saturday`, or block with evidence. It is fail-closed: missing GetResponse credentials, list/campaign, sender, template, or provider acceptance records `saturday_digest_status: blocked` instead of silently skipping the digest.

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
| Brevo direct-email fallback key | `BREVO_API_KEY` or `/home/ubuntu/.config/hubbot/brevo_api_key` | `600` for file fallback |
| Dashboard API key fallback | `/home/ubuntu/.config/hubbot/dashboard_api_key` | `600` |

The Doppler token must be scoped read-only to the `hubbot` / `prd` secrets used by the dedicated HubBot account. The runtime should prefer environment variables or connector-backed credentials when available, but the files above are the durable fallback for unattended scheduled execution.
