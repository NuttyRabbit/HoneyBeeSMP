#!/bin/sh
# backup.sh — rclone backup of the HoneyBeeSMP server to Google Drive.
#
# What it backs up (in priority order):
#   1. Minecraft server files  - worlds, configs. CANNOT be regenerated.
#   2. Crafty panel config     - server definitions, users, schedules
#   3. Our own content         - website, bot, repo (small)
#
# Everything is packed into ONE zip per run. A zip is a single object on
# Drive, so an upload is one API call instead of hundreds of them, and a
# restore is a single download + unzip. This matters a lot: the Minecraft
# tree is ~136 files and uploading them individually was slow and fragile.
#
# Layout on Drive:
#   HoneyBeeSMP/
#     backup-2026-10-20_2349.zip   dated archives (BACKUP_KEEP most recent)
#     latest.zip                   rolling copy of the newest archive
#
# Usage:  ./scripts/backup.sh [--dry-run]
# Exit:   0 success, non-zero on any failure (so cron/monitoring sees it)

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
REMOTE=gdrive:HoneyBeeSMP
STAMP=$(date -u +%Y-%m-%d_%H%M)
LOGDIR="$REPO_ROOT/logs"
LOG="$LOGDIR/backup.log"

# Which Crafty servers (by directory name under /opt/crafty/servers) to back
# up. Only these are copied; anything else on the box is ignored. Override at
# runtime with MINECRAFT_SERVERS="id1 id2" ./scripts/backup.sh
MINECRAFT_SERVERS=${MINECRAFT_SERVERS:-119045e1-1fac-41a0-83c0-5e2d85ce4c78}
SERVERS_DIR=/opt/crafty/servers

# How many dated archives to keep on Drive. "latest.zip" is never pruned.
BACKUP_KEEP=${BACKUP_KEEP:-7}

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="--dry-run"

mkdir -p "$LOGDIR"

log() {
	# Timestamped, tee'd to the log file so there is an audit trail.
	printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

# Run a command, capture its exit code portably.
# This script runs under dash, where bash-only constructs like ${PIPESTATUS[0]}
# are a syntax error, so the status is written to a temp file by a subshell.
run_logged() {
	rc_file=$(mktemp)
	( "$@" 2>&1; echo $? > "$rc_file" ) | tee -a "$LOG" >&2
	rc=$(cat "$rc_file" 2>/dev/null || echo 1)
	rm -f "$rc_file"
	return "$rc"
}

# Upload a local file to Drive.
rclone_put() {
	src=$1; dest=$2
	log "  -> upload $(basename "$src")"
	run_logged rclone copyto "$src" "$dest" \
		--transfers 8 \
		--stats 15s \
		--stats-one-line \
		--log-level INFO
}

fail=0
WORK=$(mktemp -d)
cleanup() {
	sudo rm -rf "$WORK" 2>/dev/null
	return 0
}
trap cleanup EXIT

log "===== backup started (stamp $STAMP) ====="

# ---------------------------------------------------------------------------
# 1. Minecraft server files
# ---------------------------------------------------------------------------
# A running server writes to its world while we read it, which can yield an
# inconsistent copy. Detect that and say so loudly.
mc_running=0
if sudo -n docker inspect -f '{{.State.Status}}' crafty_container >/dev/null 2>&1; then
	if [ "$(sudo -n docker inspect -f '{{.State.Status}}' crafty_container)" = "running" ]; then
		if sudo -n docker exec crafty_container sh -c 'pgrep -f "[j]ava" >/dev/null' 2>/dev/null; then
			mc_running=1
		fi
	fi
fi

if [ "$mc_running" = "1" ]; then
	log "WARNING: a Minecraft server is RUNNING. The world copy may be inconsistent."
	log "         Stop the server for a guaranteed-consistent backup."
fi

log "staging minecraft files (servers: $MINECRAFT_SERVERS)"
MC_STAGE="$WORK/minecraft"
CRAFTY_CONFIG_DIR=/opt/crafty/config
mkdir -p "$MC_STAGE"
found=0
for srv in $MINECRAFT_SERVERS; do
	if [ ! -d "$SERVERS_DIR/$srv" ]; then
		log "  !! server '$srv' not found under $SERVERS_DIR - skipping"
		fail=1
		continue
	fi
	found=1
	log "  staging $srv ($(sudo du -sh "$SERVERS_DIR/$srv" 2>/dev/null | cut -f1))"
	# rsync will not create missing intermediate directories, so make the
	# per-server destination explicitly first.
	mkdir -p "$MC_STAGE/$srv"
	# Exclude things that are large and regenerable, or actively written.
	sudo rsync -a \
		--exclude='logs/' \
		--exclude='crash-reports/' \
		--exclude='*.log' \
		--exclude='session.lock' \
		"$SERVERS_DIR/$srv/" "$MC_STAGE/$srv/" 2>&1 | tail -2 | tee -a "$LOG" >&2 || \
	rsync -a --exclude='logs/' --exclude='crash-reports/' --exclude='*.log' \
		--exclude='session.lock' \
		"$SERVERS_DIR/$srv/" "$MC_STAGE/$srv/" 2>&1 | tail -2 | tee -a "$LOG" >&2
done
[ "$found" = "1" ] || { log "FATAL: no configured servers exist"; exit 1; }
# The staged files are written by root (we read /opt/crafty as root), but we
# zip as the normal user, so hand ownership back before packing.
sudo chown -R "$(id -u):$(id -g)" "$MC_STAGE" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Crafty panel config (excludes DB journals and the live TLS key)
# ---------------------------------------------------------------------------
log "staging crafty config"
CR_STAGE="$WORK/crafty"
mkdir -p "$CR_STAGE"
sudo rsync -a \
	--exclude='db/*.sqlite-shm' \
	--exclude='db/*.sqlite-wal' \
	--exclude='session.lock' \
	--exclude='logs/' \
	--exclude='*.pem' \
	--exclude='*.key' \
	"$CRAFTY_CONFIG_DIR/" "$CR_STAGE/config/" 2>&1 | tail -2 | tee -a "$LOG" >&2 || \
	rsync -a --exclude='db/*.sqlite-shm' --exclude='db/*.sqlite-wal' \
		--exclude='session.lock' --exclude='logs/' --exclude='*.pem' --exclude='*.key' \
		"$CRAFTY_CONFIG_DIR/" "$CR_STAGE/config/" 2>&1 | tail -2 | tee -a "$LOG" >&2
sudo chown -R "$(id -u):$(id -g)" "$CR_STAGE" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Our own content: website, bot, repo. Small and regenerable from git,
#    but cheap to include and useful for a bare-metal restore.
# ---------------------------------------------------------------------------
log "staging content"
CONTENT_STAGE="$WORK/content"
mkdir -p "$CONTENT_STAGE"
rsync -a "$REPO_ROOT/website/" "$CONTENT_STAGE/website/" 2>/dev/null || true
rsync -a \
	--exclude='.env' --exclude='data/' --exclude='logs/' \
	"$REPO_ROOT/bot/" "$CONTENT_STAGE/bot/" 2>/dev/null || true
rsync -a \
	--exclude='.git/' --exclude='logs/' \
	--exclude='crafty-panel' --exclude='minecraft-servers' --exclude='discord-bot' \
	"$REPO_ROOT/" "$CONTENT_STAGE/repo/" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 4. Pack it all into one zip
# ---------------------------------------------------------------------------
ARCHIVE="$WORK/backup-$STAMP.zip"
log "creating archive $(basename "$ARCHIVE")"
# -r recurse, -X drop extra file attributes (uid/gid/times) that are not
# meaningful in a backup and cause noisy diffs, -1 = fast compression
# (the tree is mostly jars and already-compressed world data).
# zip exits non-zero if it could not read every file, so check the archive
# itself for validity rather than trusting the exit code alone.
( cd "$WORK" && zip -r -X -1 "$ARCHIVE" minecraft crafty content ) \
	>> "$LOG" 2>&1 || true

if ! unzip -tqq "$ARCHIVE" > /dev/null 2>&1; then
	log "FATAL: archive failed integrity check"
	tail -5 "$LOG"
	exit 1
fi

ZIP_SIZE=$(du -h "$ARCHIVE" | cut -f1)
ZIP_FILES=$(unzip -l "$ARCHIVE" 2>/dev/null | tail -1 | awk '{print $2}')
log "archive created: $ZIP_SIZE ($ZIP_FILES entries)"

# ---------------------------------------------------------------------------
# 5. Upload
# ---------------------------------------------------------------------------
if rclone_put "$ARCHIVE" "$REMOTE/backup-$STAMP.zip"; then
	log "     ok"
else
	log "     FAILED: upload"
	fail=1
fi

# A rolling copy of the newest archive, for quick restores.
if rclone_put "$ARCHIVE" "$REMOTE/latest.zip"; then
	log "     ok"
else
	log "     FAILED: latest upload"
	fail=1
fi

# ---------------------------------------------------------------------------
# 6. Retention: keep the newest N dated archives, delete older ones.
#    "latest.zip" is a rolling copy and is never pruned.
# ---------------------------------------------------------------------------
log "pruning archives, keeping newest $BACKUP_KEEP"
snaps=$(rclone lsf "$REMOTE/" 2>/dev/null \
	| grep -E '^backup-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}\.zip$' \
	| sort -r)
count=$(printf '%s\n' "$snaps" | grep -c . || true)
if [ "$count" -gt "$BACKUP_KEEP" ]; then
	printf '%s\n' "$snaps" | tail -n +$((BACKUP_KEEP + 1)) | while read -r old; do
		[ -n "$old" ] || continue
		log "  purging old archive $old"
		rclone deletefile "$REMOTE/$old" 2>&1 | tail -1 | tee -a "$LOG"
	done
else
	log "  nothing to prune ($count archive(s))"
fi

log "===== backup complete (fail=$fail) ====="
exit "$fail"
