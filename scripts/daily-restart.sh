#!/bin/sh
# daily-restart.sh - scheduled, graceful restart of a Minecraft server.
#
# Why bother: a server that has been up for a long time accumulates memory
# pressure and stale state, and anything deployed during the day - mods,
# configs - only takes effect at the next restart. A restart at a quiet,
# predictable hour is much kinder than one triggered by a crash, or by an
# admin doing it while somebody is mid-build.
#
# The restart is announced in game (10, 5, 2 and 0.5 minutes), then the
# server is asked to stop. That is the same graceful path as typing "stop"
# in the console: the world is saved and the players are told the server
# is shutting down. It is started again once the Java process has actually
# gone, because starting it earlier would fight the old one for the world
# lock.
#
# Usage:  ./scripts/daily-restart.sh [live|dev] [--dry-run]
# Exit:   0 on success (including "nothing needs doing"), non-zero on
#         failure, so systemd records a failed unit.
#
# Scheduled by scripts/install-daily-restart-timer.sh, which runs it at
# 05:00 Europe/London. Run it by hand with:
#     sudo systemctl start honeybeesmp-daily-restart.service

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ENV=live
DRY_RUN=0
for arg in "$@"; do
	case "$arg" in
	live | dev) ENV=$arg ;;
	--dry-run) DRY_RUN=1 ;;
	*)
		echo "usage: $0 [live|dev] [--dry-run]" >&2
		exit 2
		;;
	esac
done

ENV_FILE="minecraft/env/$ENV/env.conf"
if [ ! -f "$ENV_FILE" ]; then
	echo "no environment config at $ENV_FILE" >&2
	exit 1
fi
SERVER_ID=$(sed -n 's/^SERVER_ID=//p' "$ENV_FILE" | head -1)
if [ -z "$SERVER_ID" ]; then
	echo "$ENV_FILE has no SERVER_ID" >&2
	exit 1
fi

LOGDIR="$REPO_ROOT/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/daily-restart.log"

# One run at a time. The timer cannot normally fire twice, but a hand-run
# while the timer's run is still sleeping through its countdown would
# otherwise restart the server twice.
exec 9>"$LOGDIR/daily-restart.lock"
if ! flock -n 9; then
	echo "another restart is already running - leaving it alone"
	exit 0
fi

log() {
	printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG"
}

crafty() {
	sh "$REPO_ROOT/scripts/crafty.sh" "$@"
}

# "running" or "stopped". This looks at the host's process table rather
# than the panel API, so it still answers if the panel is unwell.
server_status() {
	crafty status "$SERVER_ID" | head -1
}

# Say something in game. A failed warning must not stop the restart: the
# whole point is to restart, and a player who missed the countdown still
# gets the server's own "shutting down" message.
announce() {
	log "in-game: $1"
	if [ "$DRY_RUN" = 0 ]; then
		if ! crafty cmd "$SERVER_ID" "say $1" >/dev/null; then
			log "warning could not be delivered"
		fi
	fi
}

pause() {
	[ "$DRY_RUN" = 1 ] && return 0
	sleep "$1"
}

# Wait for the server to reach the wanted state, giving up rather than
# hanging forever. Returns non-zero on timeout.
wait_for() {
	want=$1
	limit=$2
	waited=0
	while [ "$(server_status)" != "$want" ]; do
		if [ "$waited" -ge "$limit" ]; then
			log "FAILED: server still $(server_status) after ${limit}s - check the console"
			return 1
		fi
		sleep 5
		waited=$((waited + 5))
	done
	log "server $want after ${waited}s"
}

start_server() {
	if [ "$DRY_RUN" = 1 ]; then
		log "would start the server"
		return 0
	fi
	log "starting the server"
	crafty start "$SERVER_ID" >/dev/null
	wait_for running 300
}

suffix=""
[ "$DRY_RUN" = 1 ] && suffix=" (dry run)"
log "daily restart: $ENV server $SERVER_ID$suffix"

STATE=$(server_status)
log "current state: $STATE"

# If it is already down, the useful thing is to bring it back up. There is
# nobody to warn, and starting is what a restart would end with anyway.
if [ "$STATE" = "stopped" ]; then
	log "server is not running - starting it instead of restarting"
	start_server
	log "done"
	exit 0
fi

announce "Server restarting in 10 minutes."
pause 300
announce "Server restarting in 5 minutes."
pause 180
announce "Server restarting in 2 minutes."
pause 90
announce "Server restarting in 30 seconds."
pause 30
announce "Server restarting now - back in a minute."

if [ "$DRY_RUN" = 1 ]; then
	log "would stop the server"
	log "done"
	exit 0
fi

log "stopping the server"
crafty stop "$SERVER_ID" >/dev/null

# Never start while the old process is alive: two servers on one world
# directory corrupt it. If the stop hangs, leave the server up and shout.
if ! wait_for stopped 300; then
	log "not starting another server while the old one may still be running"
	exit 1
fi

start_server
log "done"
