#!/usr/bin/env bash
# Commit the state/ folder and sources.txt and push, retrying if the other workflow pushed first.
set -euo pipefail
git config user.name "capcutclips-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add state sources.txt
if git diff --cached --quiet; then
  echo "Nothing to save."
  exit 0
fi
git commit -q -m "$1"
for attempt in 1 2 3 4 5; do
  if git push -q; then
    echo "Saved."
    exit 0
  fi
  git pull -q --rebase
  sleep $((attempt * 3))
done
echo "::error::Could not save progress after 5 attempts."
exit 1
