#!/bin/sh
# autodeploy.sh — pull the branch for an environment and deploy it if it changed.
#
# This is the server-side half of the pipeline: it polls GitHub for new
# commits and deploys them. It runs from a systemd timer every minute.
#
# It exists as a backstop for the GitHub Actions workflow. The workflow is
# the primary path (it deploys within seconds and shows a green check in
# the GitHub UI); this catches anything the workflow misses, and keeps
# working if Actions is disabled, misconfigured, or out of minutes.
#
# Both paths run the same scripts/update.sh, and update.sh takes a lock, so
# whichever gets there first does the work and the other does nothing.
#
# Usage:  ./scripts/autodeploy.sh <dev|live>
# Exit:   0 if nothing to do or a deploy succeeded, non-zero on failure.

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ENV=${1:-}
case "$ENV" in
dev) BRANCH=develop ;;
live) BRANCH=main ;;
*)
	echo "usage: $0 <dev|live>" >&2
	exit 2
	;;
esac

# A lock so the timer and a GitHub Actions run never deploy at the same
# time. If the lock is held, the other path is already deploying, so there
# is nothing for us to do.
LOCK=/var/lock/honeybeesmp-deploy-$ENV.lock
exec 9>"$LOCK" 2>/dev/null || exec 9>"/tmp/honeybeesmp-deploy-$ENV.lock"
if ! flock -n 9; then
	echo "another deploy is already running for '$ENV'; skipping"
	exit 0
fi

# Fetch quietly; a failure here (network blip) is not worth failing over.
git fetch --quiet origin "$BRANCH" 2>/dev/null || {
	echo "could not fetch origin/$BRANCH; will try again next minute"
	exit 0
}

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")

if [ -z "$REMOTE" ]; then
	echo "origin/$BRANCH not found"
	exit 0
fi

if [ "$LOCAL" = "$REMOTE" ]; then
	# Up to date. But make sure the working copy is on the right branch
	# and clean, so the next real deploy is not blocked.
	current=$(git rev-parse --abbrev-ref HEAD)
	if [ "$current" != "$BRANCH" ]; then
		git checkout --quiet "$BRANCH" 2>/dev/null || true
	fi
	exit 0
fi

echo "==> new commit on $BRANCH: $(git rev-parse --short "$LOCAL") -> $(git rev-parse --short "$REMOTE")"
sh "$REPO_ROOT/scripts/update.sh" "$ENV" all
