#!/bin/sh
# update.sh — pull, check and deploy. The entry point for CI.
#
# This is what the GitHub Actions workflow runs on the server after a push.
# It is also useful by hand.
#
#     ./scripts/update.sh <dev|live> [web|bot|minecraft|all] [--restart]
#
# The branch is chosen by the environment:
#   dev  -> develop branch
#   live -> main branch
#
# Safe to run from cron, a git hook, or CI.

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ENV=${1:-}
TARGET=${2:-all}
RESTART=""
for arg in "$@"; do
	[ "$arg" = "--restart" ] && RESTART=1
done

case "$ENV" in
dev) BRANCH=develop ;;
live) BRANCH=main ;;
*)
	echo "usage: $0 <dev|live> [web|bot|minecraft|all] [--restart]" >&2
	exit 2
	;;
esac

echo "==> branch: $BRANCH  (environment: $ENV)"

# The working copy is switched to the branch this environment deploys from.
current=$(git rev-parse --abbrev-ref HEAD)
if [ "$current" != "$BRANCH" ]; then
	echo "    switching from $current to $BRANCH"
	git checkout "$BRANCH"
fi

echo "==> pulling from origin"
before=$(git rev-parse HEAD)
git pull --ff-only origin "$BRANCH"
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
sh "$REPO_ROOT/scripts/deploy.sh" "$ENV" "$TARGET" $RESTART

echo
echo "==> reloading nginx"
sudo nginx -t && sudo systemctl reload nginx

echo "update complete ($ENV)"
