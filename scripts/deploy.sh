#!/bin/sh
# deploy.sh — publish FROM THIS REPO to the places that serve/run it.
#
# The repo is the single source of truth:
#   website/  ->  /var/www/honeybeesmp.co.uk   (nginx serves this)
#   bot/      ->  /opt/honeybee-discord-bot    (runtime location, .env preserved)
#
# Run after pulling. Keeps the live dirs identical to the repo so there is
# no ambiguity about which copy is authoritative.
#
# Usage:  ./scripts/deploy.sh [web|bot|all]     (default: all)

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
WEB_SRC="$REPO_ROOT/website"
WEB_ROOT=/var/www/honeybeesmp.co.uk
BOT_SRC="$REPO_ROOT/bot"
BOT_DEST=/opt/honeybee-discord-bot

target=${1:-all}

deploy_web() {
	echo "==> website: $WEB_SRC -> $WEB_ROOT"
	# --delete keeps the web root exactly matching the repo.
	# The destination directory belongs to www-data; we are only a group
	# member, so rsync cannot chgrp/chmod/chtime the dir itself. Skip all
	# directory attribute syncing: files inherit the setgid group and
	# remain group-writable, which is what nginx and future deploys need.
	rsync -a --delete --no-group --no-perms --omit-dir-times \
		--chmod=Fg+rw "$WEB_SRC/" "$WEB_ROOT/"
	echo "    $(find "$WEB_ROOT" -type f | wc -l) file(s) published"
}

deploy_bot() {
	echo "==> bot: $BOT_SRC -> $BOT_DEST"
	# .env must never be touched: it holds the live Discord token.
	# data/ and logs/ hold runtime state.
	rsync -a \
		--no-group \
		--no-perms \
		--omit-dir-times \
		--exclude='.env' \
		--exclude='data/' \
		--exclude='logs/' \
		--exclude='node_modules/' \
		--exclude='.venv/' \
		--exclude='__pycache__/' \
		--chmod=Fg+rw "$BOT_SRC/" "$BOT_DEST/"
	echo "    $(find "$BOT_DEST" -type f | wc -l) file(s) in place"
}

case "$target" in
	web) deploy_web ;;
	bot) deploy_bot ;;
	all) deploy_web; deploy_bot ;;
	*) echo "usage: $0 [web|bot|all]" >&2; exit 2 ;;
esac

echo "deploy complete"
