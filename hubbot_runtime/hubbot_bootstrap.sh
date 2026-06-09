#!/usr/bin/env bash
set -euo pipefail
REPO="/home/ubuntu/hubbot-dashboard"
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" pull --ff-only
else
  rm -rf "$REPO"
  gh repo clone v3ads/hubbot-dashboard "$REPO"
fi
if ! command -v doppler >/dev/null 2>&1; then
  sudo apt-get update -o Acquire::Retries=3 -o DPkg::Lock::Timeout=60 >/tmp/hubbot_runtime_apt_update.log 2>&1
  sudo apt-get install -y -o DPkg::Lock::Timeout=60 apt-transport-https ca-certificates curl gnupg >/tmp/hubbot_runtime_prereq_install.log 2>&1
  sudo mkdir -p /usr/share/keyrings
  curl -sLf --retry 3 --tlsv1.2 --proto '=https' 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/doppler-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/doppler-cli.list >/dev/null
  sudo apt-get update -o Acquire::Retries=3 -o DPkg::Lock::Timeout=60 >/tmp/hubbot_runtime_doppler_apt_update.log 2>&1
  sudo apt-get install -y -o DPkg::Lock::Timeout=60 doppler >/tmp/hubbot_runtime_doppler_install.log 2>&1
fi
mkdir -p /home/ubuntu/.config/hubbot
chmod 700 /home/ubuntu/.config/hubbot
chmod 755 "$REPO/hubbot_runtime/hubbot_preflight.py" "$REPO/hubbot_runtime/hubbot_finalize.py" "$REPO/hubbot_runtime/hubbot_publish_ai_news.py" "$REPO/hubbot_runtime/hubbot_owner_alert.py" 2>/dev/null || true
if ! python3.11 -c 'import cryptography' >/dev/null 2>&1; then
  sudo pip3 install cryptography >/tmp/hubbot_runtime_pip_cryptography.log 2>&1
fi
if [ -n "${DOPPLER_SERVICE_TOKEN:-}" ] && [ -z "${DOPPLER_TOKEN:-}" ]; then
  export DOPPLER_TOKEN="$DOPPLER_SERVICE_TOKEN"
fi
# Export COMMUNITY_ESTAGE_TOKEN from Doppler so the publish script can authenticate
# directly via the API without needing browser cookies (permanent fix for fresh-sandbox runs).
if [ -n "${DOPPLER_TOKEN:-}" ] && [ -z "${COMMUNITY_ESTAGE_TOKEN:-}" ]; then
  _ct=$(doppler secrets get COMMUNITY_ESTAGE_TOKEN --project hubbot --config prd --plain 2>/dev/null || true)
  if [ -n "$_ct" ]; then
    export COMMUNITY_ESTAGE_TOKEN="$_ct"
  fi
  unset _ct
fi
python3.11 "$REPO/hubbot_runtime/hubbot_preflight.py" --repo-root "$REPO"
