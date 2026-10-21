#!/bin/sh
# deploy.sh — publish FROM THIS REPO to the places that serve/run it.
#
# The repo is the single source of truth:
#   website/  ->  the nginx web root
#   bot/      ->  the Discord bot runtime directory (.env preserved)
#   minecraft/->  the Minecraft server's configuration
#
# There are two environments:
#
#   dev   the development server, for trying things out
#         website -> /var/www/honeybeesmp.dev
#         bot     -> /opt/honeybee-discord-bot-dev
#         MC      -> the DEV server id
#
#   live  the production server that real players use
#         website -> /var/www/honeybeesmp.co.uk
#         bot     -> /opt/honeybee-discord-bot
#         MC      -> the LIVE server id
#
# Run after pulling. Keeps the live dirs identical to the repo so there is
# no ambiguity about which copy is authoritative.
#
# Usage:  ./scripts/deploy.sh <dev|live> [web|bot|minecraft|all] [--restart]
#         ./scripts/deploy.sh <dev|live> all --restart
#
# Default target is "all".

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
WEB_SRC="$REPO_ROOT/website"
BOT_SRC="$REPO_ROOT/bot"

ENV=${1:-}
TARGET=${2:-all}
RESTART=""
for arg in "$@"; do
	[ "$arg" = "--restart" ] && RESTART=1
done

case "$ENV" in
dev | live) ;;
*)
	echo "usage: $0 <dev|live> [web|bot|minecraft|all] [--restart]" >&2
	exit 2
	;;
esac

case "$ENV" in
dev)
	WEB_ROOT=/var/www/honeybeesmp.dev
	BOT_DEST=/opt/honeybee-discord-bot-dev
	;;
live)
	WEB_ROOT=/var/www/honeybeesmp.co.uk
	BOT_DEST=/opt/honeybee-discord-bot
	;;
esac

deploy_web() {
	echo "==> website: $WEB_SRC -> $WEB_ROOT"
	# --delete keeps the web root exactly matching the repo.
	# The destination directory belongs to www-data; we are only a group
	# member, so rsync cannot chgrp/chmod/chtime the dir itself. Skip all
	# directory attribute syncing: files inherit the setgid group and
	# remain group-writable, which is what nginx and future deploys need.
	mkdir -p "$WEB_ROOT"
	rsync -a --delete --no-group --no-perms --omit-dir-times \
		--chmod=Fg+rw "$WEB_SRC/" "$WEB_ROOT/"
	echo "    $(find "$WEB_ROOT" -type f | wc -l) file(s) published"
}

deploy_bot() {
	echo "==> bot: $BOT_SRC -> $BOT_DEST"
	# .env must never be touched: it holds the live Discord token.
	# data/ and logs/ hold runtime state.
	mkdir -p "$BOT_DEST"
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

deploy_minecraft() {
	echo "==> minecraft config -> $ENV"
	sh "$REPO_ROOT/scripts/deploy-minecraft.sh" "$ENV" $RESTART
}

case "$TARGET" in
web) deploy_web ;;
bot) deploy_bot ;;
minecraft) deploy_minecraft ;;
all)
	deploy_web
	deploy_bot
	deploy_minecraft
	;;
*)
	echo "usage: $0 <dev|live> [web|bot|minecraft|all] [--restart]" >&2
	exit 2
	;;
esac

echo "deploy complete ($ENV)"
