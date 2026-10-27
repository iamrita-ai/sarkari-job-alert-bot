#!/usr/bin/env bash
# =============================================================================
# One-command helper: create a PUBLIC GitHub repository and push this project.
#
# Usage:
#   export GITHUB_USER="your-github-username"
#   export GITHUB_TOKEN="ghp_xxx"          # https://github.com/settings/tokens
#   export REPO_NAME="sarkari-job-alert-bot"   # optional override
#   ./scripts/github_push.sh
#
# Token scopes: classic token with "repo" scope, OR a fine-grained token with
# Administration (read/write) and Contents (read/write) for your account.
# =============================================================================
set -euo pipefail

: "${GITHUB_USER:?Please export GITHUB_USER}"
: "${GITHUB_TOKEN:?Please export GITHUB_TOKEN}"
REPO_NAME="${REPO_NAME:-sarkari-job-alert-bot}"
DESCRIPTION="Personalised Telegram bot that scrapes SarkariResult.com for government jobs and pushes instant profile-based alerts (python-telegram-bot + Docker)."

cd "$(dirname "$0")/.."

echo "==> Creating public repository ${GITHUB_USER}/${REPO_NAME} ..."
curl --fail --silent --show-error --location \
  --request POST \
  --header "Authorization: Bearer ${GITHUB_TOKEN}" \
  --header "Accept: application/vnd.github+json" \
  --header "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/user/repos \
  --data "{\"name\":\"${REPO_NAME}\",\"private\":false,\"description\":\"${DESCRIPTION}\"}" \
  | grep -E '"(full_name|html_url)"' || true

echo "==> Initialising git and pushing ..."
git init --initial-branch=main >/dev/null
git config user.email "${GIT_EMAIL:-${GITHUB_USER}@users.noreply.github.com}"
git config user.name "${GIT_NAME:-${GITHUB_USER}}"
git add .
git commit -m "Initial commit: Sarkari Job Alert Telegram bot (PTB, scraper, Docker)" >/dev/null
git remote remove origin 2>/dev/null || true
git remote add origin "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"
git push -u origin main

echo
echo "✅ Done! Your public repo: https://github.com/${GITHUB_USER}/${REPO_NAME}"
