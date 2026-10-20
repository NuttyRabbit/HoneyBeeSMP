#!/bin/sh
# update.sh — one-command update for the server.
#
# Pull the latest code from GitHub, sanity-check it, and deploy.
# This is the intended "automation" entry point:
#
#     ./scripts/update.sh
#
# Safe to run from a cron job or a git hook.

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "==> pulling from origin"
before=$(git rev-parse HEAD)
git pull --ff-only
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ]; then
	echo "    already up to date ($(git rev-parse --short HEAD))"
	else
	echo "    updated $(git rev-parse --short "$before") -> $(git rev-parse --short "$after")"
fi

echo
echo "==> sanity check"
sh "$REPO_ROOT/scripts/check.sh"

echo
echo "==> deploy"
sh "$REPO_ROOT/scripts/deploy.sh" all

echo
echo "==> reloading nginx"
sudo nginx -t && sudo systemctl reload nginx
echo "update complete"
