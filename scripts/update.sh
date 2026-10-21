#!/bin/sh
# update.sh — pull, check and deploy. The entry point for CI.
#
# This is what the GitHub Actions workflow runs on the server after a push.
# It is also used by the polling backstop (scripts/autodeploy.sh).
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

# A lock, so that two deploys never run at the same time.
#
# The lock is GLOBAL, not per-environment, and that matters: there is only
# one working copy, and a dev deploy checks out "develop" while a live
# deploy checks out "main". If they ran together they would fight over
# the checkout and could deploy the wrong branch to the wrong server.
#
# If the caller already holds the lock it passes it down as fd 9, and
# flock on an inherited descriptor succeeds immediately - the lock belongs
# to the open file description, which the child shares. So we try that
# first, and only take a lock of our own if there is no inherited one.
if ! flock -n 9 2>/dev/null; then
	LOCK=/var/lock/honeybeesmp-deploy.lock
	if ! exec 9>"$LOCK" 2>/dev/null; then
		exec 9>"/tmp/honeybeesmp-deploy.lock"
	fi
	if ! flock -w 600 9; then
		echo "timed out waiting for the deploy lock" >&2
		exit 1
	fi
fi

echo "==> branch: $BRANCH  (environment: $ENV)"

# The working copy is switched to the branch this environment deploys from.
current=$(git rev-parse --abbrev-ref HEAD)
if [ "$current" != "$BRANCH" ]; then
	echo "    switching from $current to $BRANCH"
	git checkout "$BRANCH"
fi

# A dirty working tree would stop the pull ("local changes would be
# overwritten"). That happens if someone edits files on the server
# directly. Stash them before pulling, so the deploy is never blocked.
STASHED=0
if [ -n "$(git status --porcelain)" ]; then
	echo "    working tree has local changes - stashing them"
	if git stash push --include-untracked -m "autodeploy $(date -u +%Y%m%d-%H%M%S)" >/dev/null 2>&1; then
		STASHED=1
	fi
fi

echo "==> pulling from origin"
before=$(git rev-parse HEAD)
# Pull the remote branch into the *current* branch explicitly. Naming the
# ref "origin/$BRANCH" and the destination "HEAD" avoids git's ambiguous
# "Cannot fast-forward to multiple branches" error, which happens when the
# local branch name also matches a remote-tracking branch.
git merge --ff-only "origin/$BRANCH"
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

# Put back anything we stashed. The deployed copy is regenerated from the
# repo, so restoring is only to avoid surprising whoever was editing.
if [ "$STASHED" = "1" ]; then
	echo
	echo "==> restoring stashed local changes"
	git stash pop >/dev/null 2>&1 || {
		echo "    could not restore automatically; your changes are in 'git stash list'"
	}
fi

echo "update complete ($ENV)"
