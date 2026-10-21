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
# Both paths run the same scripts/update.sh, which takes a global lock, so
# whichever gets there first does the work and the other finds nothing to
# do. They cannot race over the working copy's branch.
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

# Take the shared deploy lock for the whole operation, not just the
# update.sh call. Both environments use the same working copy and switch it
# to different branches, so the fetch/check/checkout/pull must all happen
# under one lock, or a dev and a live run would interleave and each would
# deploy the other's branch.
#
# The descriptor is closed before update.sh is called, so that the child
# does not inherit a held lock and block waiting for itself.
exec 9>&-
LOCK=/var/lock/honeybeesmp-deploy.lock
if ! exec 9>"$LOCK" 2>/dev/null; then
	exec 9>"/tmp/honeybeesmp-deploy.lock"
fi
if ! flock -n 9; then
	echo "another deploy is in progress; skipping"
	exit 0
fi

# Fetch quietly; a network blip is not worth failing over.
git fetch --quiet origin 2>/dev/null || {
	echo "could not fetch from origin; will try again next minute"
	exit 0
}

REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")
if [ -z "$REMOTE" ]; then
	echo "origin/$BRANCH not found"
	exit 0
fi

# What the working copy currently has. It may be on the other branch, so
# compare against that branch's remote rather than against HEAD.
LOCAL=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")
DEPLOYED=$(git rev-parse HEAD 2>/dev/null || echo "")

# Is the branch we deploy from ahead of what is checked out?
if git diff --quiet "origin/$BRANCH" HEAD 2>/dev/null; then
	# Same tree - nothing to deploy. Make sure the working copy is on the
	# right branch so the next deploy is not blocked by a stale checkout.
	current=$(git rev-parse --abbrev-ref HEAD)
	if [ "$current" != "$BRANCH" ]; then
		git checkout --quiet "$BRANCH" 2>/dev/null || true
	fi
	exit 0
fi

echo "==> new commit on $BRANCH: $(git rev-parse --short "$DEPLOYED") -> $(git rev-parse --short "$REMOTE")"

# Hand the lock down to update.sh as fd 9 and leave it open. The lock
# belongs to the open file description, so the child shares it and its
# own flock on fd 9 succeeds immediately. Crucially, the lock stays held
# for the whole deploy - if we closed fd 9 before calling, the lock would
# be released and a second deploy could start alongside this one.
sh "$REPO_ROOT/scripts/update.sh" "$ENV" all
