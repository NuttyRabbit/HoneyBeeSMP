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
	# The root may not exist yet and /var/www is not writable by us.
	sudo mkdir -p "$WEB_ROOT"
	rsync -a --delete --no-group --no-perms --omit-dir-times \
		--chmod=Fg+rw "$WEB_SRC/" "$WEB_ROOT/"

	echo "    $(find "$WEB_ROOT" -type f | wc -l) file(s) published"
}

# Publish the modpack to Modrinth, where players install it from and the
# launcher keeps it up to date. The project is the distribution channel, so
# a pack change is not finished until it is published.
#
# If Modrinth is not set up yet there is nothing to publish to, so the step
# is skipped rather than failing the whole deploy.
publish_modpack() {
	echo "==> modpack -> Modrinth"

	if [ -z "${MODRINTH_TOKEN:-}" ] && [ ! -f "$HOME/.config/modrinth/token" ]; then
		echo "    skipped: no Modrinth API token configured"
		echo "    see scripts/publish-modpack.py for how to set one up"
		return 0
	fi
	if [ ! -f "$HOME/.config/modrinth/project-id" ]; then
		echo "    skipped: no Modrinth project yet"
		echo "    run: python3 scripts/publish-modpack.py create"
		return 0
	fi

	if ! python3 "$REPO_ROOT/scripts/publish-modpack.py" publish; then
		echo "    FAILED to publish the modpack to Modrinth" >&2
		return 1
	fi

	# The project page's description lives in the repo too, so push it as
	# well. Otherwise the listing can say something different from what
	# the repo says, and nobody notices until a player quotes it.
	if ! python3 "$REPO_ROOT/scripts/publish-modpack.py" sync-description; then
		echo "    FAILED to sync the description to Modrinth" >&2
		return 1
	fi
}

deploy_bot() {
	echo "==> bot: $BOT_SRC -> $BOT_DEST"
	# .env must never be touched: it holds the live Discord token.
	# data/ and logs/ hold runtime state.
	# The destination may not exist yet, and /opt is not writable by the
	# deploy user, so creating it needs sudo. It is owned by the deploy
	# user so that subsequent deploys can write to it without sudo.
	sudo mkdir -p "$BOT_DEST"
	sudo chown "$(id -u):$(id -g)" "$BOT_DEST" 2>/dev/null || true
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
	# The modpack is published from the live environment only - publishing
	# a draft pack would push unreleased mods at players.
	if [ "$ENV" = "live" ]; then
		publish_modpack
	fi
	;;
*)
	echo "usage: $0 <dev|live> [web|bot|minecraft|all] [--restart]" >&2
	exit 2
	;;
esac

echo "deploy complete ($ENV)"
