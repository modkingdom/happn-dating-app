#!/usr/bin/env bash
set -euo pipefail

CREDENTIALS_FILE="../.gh-credentials"
COUNTER_FILE=".gh-commit-count"

# ── 1. Load credentials ───────────────────────────────────────────────────────
if [ ! -f "$CREDENTIALS_FILE" ]; then
  echo "ERROR: $CREDENTIALS_FILE not found."
  echo "Copy .gh-credentials.example → .gh-credentials and fill in your values."
  exit 1
fi

source "$CREDENTIALS_FILE"

: "${GITHUB_USER:?Missing GITHUB_USER in $CREDENTIALS_FILE}"
: "${GITHUB_EMAIL:?Missing GITHUB_EMAIL in $CREDENTIALS_FILE}"
: "${GITHUB_TOKEN:?Missing GITHUB_TOKEN in $CREDENTIALS_FILE}"

# ── 2. Repo name = current folder name ───────────────────────────────────────
GITHUB_REPO="$(basename "$(pwd)")"

# ── 3. Commit counter ─────────────────────────────────────────────────────────
if [ -f "$COUNTER_FILE" ]; then
  COUNT=$(( $(cat "$COUNTER_FILE") + 1 ))
else
  COUNT=1
fi
echo "$COUNT" > "$COUNTER_FILE"

# ── 4. Init git if needed ─────────────────────────────────────────────────────
if [ ! -d ".git" ]; then
  git init
  git branch -M main
fi

# ── 5. Configure git identity locally ────────────────────────────────────────
git config --local user.name  "$GITHUB_USER"
git config --local user.email "$GITHUB_EMAIL"

# ── 6. Create repo on GitHub if it doesn't exist ─────────────────────────────
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}")

if [ "$HTTP_STATUS" = "404" ]; then
  echo "Creating GitHub repo: ${GITHUB_USER}/${GITHUB_REPO} ..."
  curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${GITHUB_REPO}\",\"private\":false,\"auto_init\":false}" \
    "https://api.github.com/user/repos" > /dev/null
  echo "Repo created."
fi

# ── 7. Set remote ─────────────────────────────────────────────────────────────
REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${GITHUB_REPO}.git"

if git remote get-url origin &>/dev/null; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# ── 8. Stage and commit (if anything changed) ────────────────────────────────
git add -A

if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  git commit -m "$COUNT"
fi

# ── 9. Push (always — recovers from a previously failed push) ─────────────────
git push -u origin main

echo ""
echo "Done! [$COUNT] → github.com/${GITHUB_USER}/${GITHUB_REPO}"
