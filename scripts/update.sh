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

# Where the commit each environment is running is recorded. The polling
# backstop (scripts/autodeploy.sh) reads it to decide whether there is
# anything to deploy.
STATE_DIR="${HOME:-/tmp}/.cache/honeybeesmp"

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

# Fetch first, so the ref below is current. Without this the GitHub
# Actions path - which SSHes in and runs this script directly - works from
# a stale origin/BRANCH and can deploy an old commit while reporting
# success.
git fetch --quiet origin "$BRANCH" 2>/dev/null || {
	echo "could not fetch origin/$BRANCH - aborting" >&2
	exit 1
}

# The working copy on the server is a deployment target, not a place to
# work. Local edits are overwritten by the next deploy anyway, and local
# commits are not ours to keep, so the branch is reset to exactly what is
# on GitHub.
#
# Stashing used to be used here, and it was a source of real failures: a
# stash made on one branch cannot be popped cleanly onto another, and a
# failed pop leaves the tree in a state where the *next* run cannot even
# stash either - so every later deploy fails with "could not stash local
# changes". A reset cannot fail that way.
if [ -n "$(git status --porcelain)" ]; then
	echo "    discarding local changes on the server"
	echo "    (edit in the repo and push - the server's copy is regenerated)"
	git reset --hard > /dev/null 2>&1 || true
	git clean -fdq > /dev/null 2>&1 || true
fi

# Switch to the branch this environment deploys from, and make it match
# origin exactly. -B resets the branch to the given start point, so a
# diverged local branch cannot wedge the deploy.
current=$(git rev-parse --abbrev-ref HEAD)
if [ "$current" != "$BRANCH" ]; then
	echo "    switching from $current to $BRANCH"
fi
# What this environment was running before, so the log says what changed.
# Not HEAD: there is one working copy shared by both environments, so HEAD
# is whichever branch was deployed last.
before=$(cat "$STATE_DIR/deployed-$ENV.sha" 2>/dev/null || echo "")
if ! checkout_out=$(git checkout -f -B "$BRANCH" "origin/$BRANCH" 2>&1); then
	echo "could not switch to $BRANCH - aborting" >&2
	echo "$checkout_out" >&2
	exit 1
fi
after=$(git rev-parse HEAD)

if [ -z "$before" ]; then
	echo "    deploying $(git rev-parse --short "$after")"
elif [ "$before" = "$after" ]; then
	echo "    already up to date ($(git rev-parse --short HEAD))"
else
	echo "    updated $(echo "$before" | cut -c1-7) -> $(git rev-parse --short "$after")"
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

# Record the commit this environment is now running, so the polling
# backstop (scripts/autodeploy.sh) can tell whether there is anything to
# do next time.
mkdir -p "$STATE_DIR"
git rev-parse HEAD > "$STATE_DIR/deployed-$ENV.sha"

echo "update complete ($ENV)"
