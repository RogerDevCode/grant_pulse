#!/usr/bin/env bash
set -euo pipefail

REPO_URL="git@github.com:RogerDevCode/grant_pulse.git"
BRANCH="main"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: no estás dentro de un repositorio Git."
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "Uso: $0 \"mensaje del commit\""
  exit 1
fi

COMMIT_MSG="$*"

git add -A

if git diff --cached --quiet; then
  echo "No hay cambios para commitear."
else
  git commit -m "$COMMIT_MSG"
fi

git branch -M "$BRANCH"

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

git push -u origin "$BRANCH"
