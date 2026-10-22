#!/bin/sh
# deploy-minecraft.sh — apply the repo's Minecraft configuration to a server.
#
# The repo holds the *configuration* for our Minecraft server (not the world
# data, which is large and lives on the server). This script pushes that
# configuration to a chosen environment:
#
#   dev   -> the development server, where new features are tested
#   live  -> the production server that real players use
#
# What it does:
#   1. Renders server.properties from the template, substituting the
#      environment's port.
#   2. Syncs config/ and defaultconfigs/ (NeoForge settings) to the server.
#   3. Reconciles mods/ against minecraft/mods/mods.manifest.
#   4. Optionally restarts the server so changes take effect.
#
# It NEVER touches the world directory, player data, or the server jars.
#
# Usage:
#   ./scripts/deploy-minecraft.sh <dev|live> [--restart]
#
# Exit: 0 on success, non-zero on failure.

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
MC_SRC="$REPO_ROOT/minecraft"
SERVERS_DIR=/opt/crafty/servers
CONTAINER=crafty_container

ENV=${1:-}
RESTART=""
[ "${2:-}" = "--restart" ] && RESTART=1

case "$ENV" in
dev | live) ;;
*)
	echo "usage: $0 <dev|live> [--restart]" >&2
	exit 2
	;;
esac

ENV_FILE="$MC_SRC/env/$ENV/env.conf"
if [ ! -f "$ENV_FILE" ]; then
	echo "no environment config at $ENV_FILE" >&2
	exit 1
fi

# Read the environment's settings (SERVER_ID, SERVER_PORT, and the world
# generation settings).
SERVER_ID=""
SERVER_PORT=""
SERVER_ADDRESS=""
LEVEL_NAME=""
LEVEL_TYPE=""
GENERATOR_SETTINGS=""
GENERATE_STRUCTURES=""
WHITELIST=""
MAX_PLAYERS=""
MOTD=""
while IFS='=' read -r key value; do
	case "$key" in
	"") continue ;;
	\#*) continue ;;
	SERVER_ID) SERVER_ID=$value ;;
	SERVER_PORT) SERVER_PORT=$value ;;
	SERVER_ADDRESS) SERVER_ADDRESS=$value ;;
	LEVEL_NAME) LEVEL_NAME=$value ;;
	LEVEL_TYPE) LEVEL_TYPE=$value ;;
	GENERATOR_SETTINGS) GENERATOR_SETTINGS=$value ;;
	GENERATE_STRUCTURES) GENERATE_STRUCTURES=$value ;;
	WHITELIST) WHITELIST=$value ;;
	MAX_PLAYERS) MAX_PLAYERS=$value ;;
	MOTD) MOTD=$value ;;
	esac
done < "$ENV_FILE"

if [ -z "$SERVER_ID" ] || [ -z "$SERVER_PORT" ]; then
	echo "env.conf for '$ENV' is missing SERVER_ID or SERVER_PORT" >&2
	exit 1
fi

# The world settings have to be present too: a missing one would render
# an empty value into server.properties, and Minecraft would then fall back
# to its own defaults - which for the dev server would quietly mean a
# normal world instead of the superflat we asked for.
for needed in LEVEL_NAME LEVEL_TYPE GENERATOR_SETTINGS GENERATE_STRUCTURES; do
	eval "have=\$$needed"
	if [ -z "$have" ]; then
		echo "env.conf for '$ENV' is missing $needed" >&2
		exit 1
	fi
done

# The whitelist switch, too. An empty value here would turn the whitelist
# off silently, which for the dev server means anyone could get in.
if [ -z "$WHITELIST" ]; then
	echo "env.conf for '$ENV' is missing WHITELIST" >&2
	exit 1
fi
case "$WHITELIST" in
true | false) ;;
*)
	echo "env.conf for '$ENV' has WHITELIST=$WHITELIST; it must be true or false" >&2
	exit 1
	;;
esac

# The player limit, too. A missing or nonsensical value here would be
# rendered straight into server.properties, so it is checked rather than
# trusted.
case "$MAX_PLAYERS" in
'' | *[!0-9]*)
	echo "env.conf for '$ENV' has MAX_PLAYERS='$MAX_PLAYERS'; it must be a number" >&2
	exit 1
	;;
esac

# The MOTD, too. An empty one would leave the server showing whatever
# Minecraft's default is, which is not what anyone asked for.
if [ -z "$MOTD" ]; then
	echo "env.conf for '$ENV' is missing MOTD" >&2
	exit 1
fi

TARGET="$SERVERS_DIR/$SERVER_ID"
if [ ! -d "$TARGET" ]; then
	echo "server directory not found: $TARGET" >&2
	exit 1
fi

echo "==> environment: $ENV (server $SERVER_ID, port $SERVER_PORT)"

# ---------------------------------------------------------------------------
# 1. Render server.properties
# ---------------------------------------------------------------------------
# The template carries @PLACEHOLDER@ markers; the environment supplies the
# real values.
#
# The values are substituted with a small python helper rather than sed,
# because generator-settings is JSON containing "/" and "&", which are
# special in a sed replacement.
#
# The values are passed through the environment rather than as positional
# arguments. Positional arguments are easy to get out of step with the
# script that reads them - and when that happens the failure is an
# IndexError deep inside a heredoc, with the real cause nowhere to be seen.
RENDERED=$(mktemp)
SERVER_PORT="$SERVER_PORT" \
LEVEL_NAME="$LEVEL_NAME" \
LEVEL_TYPE="$LEVEL_TYPE" \
GENERATOR_SETTINGS="$GENERATOR_SETTINGS" \
GENERATE_STRUCTURES="$GENERATE_STRUCTURES" \
WHITELIST="$WHITELIST" \
MAX_PLAYERS="$MAX_PLAYERS" \
MOTD="$MOTD" \
python3 - "$MC_SRC/server.properties" "$RENDERED" <<'PY'
import os
import sys

src, dest = sys.argv[1], sys.argv[2]
values = {
    "@SERVER_PORT@": os.environ["SERVER_PORT"],
    "@LEVEL_NAME@": os.environ["LEVEL_NAME"],
    "@LEVEL_TYPE@": os.environ["LEVEL_TYPE"],
    "@GENERATOR_SETTINGS@": os.environ["GENERATOR_SETTINGS"],
    "@GENERATE_STRUCTURES@": os.environ["GENERATE_STRUCTURES"],
    "@WHITELIST@": os.environ["WHITELIST"],
    "@MAX_PLAYERS@": os.environ["MAX_PLAYERS"],
    "@MOTD@": os.environ["MOTD"],
}

with open(src, encoding="utf-8") as fh:
    text = fh.read()

for key, value in values.items():
    text = text.replace(key, value)

# A placeholder that is still in the file means the template and the
# renderer have drifted apart. Writing it out anyway would give the
# server a broken setting, so stop here instead.
leftover = [key for key in values if key in text]
if leftover:
    sys.exit(
        "server.properties template has placeholder(s) this script does "
        "not fill in: " + ", ".join(sorted(leftover))
    )

with open(dest, "w", encoding="utf-8") as fh:
    fh.write(text)
PY

# Compare against what the server currently has, ignoring the timestamp
# comment Minecraft rewrites on every start. Only write when it differs, so
# we do not churn the file (and do not trigger needless restarts).
CURRENT=$(mktemp)
if sudo test -f "$TARGET/server.properties"; then
	sudo grep -vE "^#[A-Z][a-z]{2} [A-Z][a-z]{2} " "$TARGET/server.properties" > "$CURRENT" 2>/dev/null || true
fi
if cmp -s "$RENDERED" "$CURRENT"; then
	echo "    server.properties unchanged"
else
	echo "    server.properties changed - updating"
	sudo cp "$RENDERED" "$TARGET/server.properties"
	# Keep the ownership the server expects.
	sudo chown opc:root "$TARGET/server.properties" 2>/dev/null || true
fi
rm -f "$RENDERED" "$CURRENT"

# ---------------------------------------------------------------------------
# 1a. The whitelist
# ---------------------------------------------------------------------------
# The list of who may join lives in the repo, as player names. Minecraft's
# own whitelist file records UUIDs, so the names are resolved through
# Mojang's API and the file is written out.
#
# The server reads its whitelist at startup, so a change here only takes
# effect after a restart. It is written even when the server is running,
# because the server only rewrites the file when its own whitelist
# changes - so a file we write is not clobbered by the running server.
WHITELIST_SRC="$MC_SRC/env/$ENV/whitelist.txt"
if [ -f "$WHITELIST_SRC" ]; then
	echo "    whitelist:"
	WHITELIST_RENDERED=$(mktemp)
	if ! python3 "$REPO_ROOT/scripts/whitelist.py" build "$ENV" "$WHITELIST_RENDERED"; then
		echo "    could not build the whitelist - leaving the server's alone" >&2
		rm -f "$WHITELIST_RENDERED"
	else
		WHITELIST_CURRENT=$(mktemp)
		if sudo test -f "$TARGET/whitelist.json"; then
			sudo cat "$TARGET/whitelist.json" > "$WHITELIST_CURRENT" 2>/dev/null || true
		fi
		if cmp -s "$WHITELIST_RENDERED" "$WHITELIST_CURRENT"; then
			echo "    whitelist unchanged"
		else
			echo "    whitelist changed - updating"
			sudo cp "$WHITELIST_RENDERED" "$TARGET/whitelist.json"
			sudo chown opc:root "$TARGET/whitelist.json" 2>/dev/null || true
			echo "    (takes effect the next time the server starts)"
		fi
		rm -f "$WHITELIST_RENDERED" "$WHITELIST_CURRENT"
	fi
fi

# ---------------------------------------------------------------------------
# 1b. JVM memory settings
# ---------------------------------------------------------------------------
# Each environment has its own heap size, because the live server has real
# players and the dev server does not. Keeping these in the repo means the
# allocation is reviewable and reproducible, rather than being set once in
# the panel and forgotten.
#
# The change only takes effect when the server next starts, so this is
# safe to write while the server is running.
JVM_ARGS_SRC="$MC_SRC/env/$ENV/jvm_args.txt"
if [ -f "$JVM_ARGS_SRC" ]; then
	JVM_ARGS_RENDERED=$(mktemp)
	sed "s/@SERVER_ID@/$SERVER_ID/g" "$JVM_ARGS_SRC" > "$JVM_ARGS_RENDERED"
	JVM_ARGS_CURRENT=$(mktemp)
	if sudo test -f "$TARGET/user_jvm_args.txt"; then
		sudo cat "$TARGET/user_jvm_args.txt" > "$JVM_ARGS_CURRENT" 2>/dev/null || true
	fi
	if cmp -s "$JVM_ARGS_RENDERED" "$JVM_ARGS_CURRENT"; then
		echo "    jvm args unchanged"
	else
		echo "    jvm args changed - updating (takes effect on next restart)"
		sudo cp "$JVM_ARGS_RENDERED" "$TARGET/user_jvm_args.txt"
		sudo chown opc:root "$TARGET/user_jvm_args.txt" 2>/dev/null || true
	fi
	rm -f "$JVM_ARGS_RENDERED" "$JVM_ARGS_CURRENT"
fi

# ---------------------------------------------------------------------------
# 2. Sync the modpack config
# ---------------------------------------------------------------------------
# The pack's "overrides" are the config that applies to both the client and
# the server; "server-overrides" is server-only. Syncing these is how a
# config change is promoted from dev to live.
#
# The server runs as the "opc" user, so the files must be owned by it (and
# group root, matching the rest of the server directory) or the server
# cannot write its own config.
PACK_SRC="$MC_SRC/modpack"
for pair in "overrides:config defaultconfigs" ; do
	src_name=${pair%%:*}
	dst_names=${pair#*:}
	[ -d "$PACK_SRC/$src_name" ] || continue
	for dst in $dst_names; do
		[ -d "$PACK_SRC/$src_name/$dst" ] || continue
		echo "    syncing $src_name/$dst -> $dst/"
		sudo mkdir -p "$TARGET/$dst"
		sudo rsync -a \
			--no-group --no-perms --omit-dir-times \
			--chown=opc:root \
			"$PACK_SRC/$src_name/$dst/" "$TARGET/$dst/"
	done
done

# The pack's "server-overrides" is the server-only half: it is copied to
# the server root keeping its structure, so server-overrides/config/x.toml
# lands in the server's config/x.toml. That is where the settings for
# mods that only exist on the server - LuckPerms, Open Parties and Claims
# - live.
#
# These files are complete, not patches. The server's own config is
# overwritten by them, so a partial file would throw away everything
# else the mod wrote for itself.
if [ -d "$PACK_SRC/server-overrides" ]; then
	echo "    syncing server-overrides -> (server root)"
	sudo rsync -a \
		--no-group --no-perms --omit-dir-times \
		--chown=opc:root \
		"$PACK_SRC/server-overrides/" "$TARGET/"
fi

# The same thing, per environment, applied on top. The config files here
# are complete HOCON files rather than key/value patches, which the
# server-config merge cannot express, so they overwrite whatever is there.
# This is how dev avoids binding the same web-server port as live: both
# servers share one network namespace.
if [ -d "$MC_SRC/env/$ENV/server-overrides" ]; then
	echo "    syncing env/$ENV/server-overrides -> (server root)"
	sudo rsync -a \
		--no-group --no-perms --omit-dir-times \
		--chown=opc:root \
		"$MC_SRC/env/$ENV/server-overrides/" "$TARGET/"
fi

# The settings we want for mods that write their own config on the
# server - LuckPerms, Open Parties and Claims, Simple Voice Chat. These
# are merged into the config the mod generated rather than replacing it,
# so the repo does not have to carry a copy of the mod's defaults.
#
# "minecraft/server-config" is shared by both environments;
# "minecraft/env/<env>/server-config" is that environment's own, applied
# on top. The per-environment one exists for things that have to differ,
# like the voice chat port - the dev and live servers run in the same
# container and cannot both have the same UDP port.
for overrides in "$MC_SRC/server-config" "$MC_SRC/env/$ENV/server-config"; do
	[ -d "$overrides" ] || continue
	echo "    applying $(basename "$overrides") overrides"
	# sudo, because the config directory belongs to the server user and
	# the deploy does not.
	sudo python3 "$REPO_ROOT/scripts/server-config.py" merge \
		"$overrides" "$TARGET/config" || true
done

# ---------------------------------------------------------------------------
# 3. Install the server-side mods
# ---------------------------------------------------------------------------
# The pack is the single source of truth for the mod set. It records which
# side each file belongs to, so the server only installs the ones marked
# for it, and every download is checked against the hash in the pack.
#
# This is scripts/modpack.py rather than shell, because it has to read JSON
# and verify SHA-512 hashes. It is the same code that builds the pack
# players download, so the two can never disagree.
echo "    installing mods from the pack"
sudo mkdir -p "$TARGET/mods"
# Remember what is there now, so the log says what was taken away. A mod
# that leaves the pack has to actually leave the server - otherwise the
# server keeps loading it, and the crash it causes shows up long after
# the change that caused it.
BEFORE=$(mktemp)
sudo ls -1 "$TARGET/mods" 2>/dev/null | sort > "$BEFORE"
MODS_STAGE=$(mktemp -d)
if python3 "$REPO_ROOT/scripts/modpack.py" install "$MODS_STAGE"; then
	# --delete makes the server's mods directory exactly the pack. Without
	# it the directory only ever grows.
	sudo rsync -a --delete \
		--no-group --no-perms --omit-dir-times \
		--chown=opc:root \
		--chmod=F644 \
		"$MODS_STAGE/" "$TARGET/mods/"
	AFTER=$(mktemp)
	sudo ls -1 "$TARGET/mods" | sort > "$AFTER"
	comm -23 "$BEFORE" "$AFTER" | while read -r gone; do
		[ -n "$gone" ] && echo "    removed $gone"
	done
	rm -f "$AFTER"
else
	echo "    FAILED to install mods from the pack" >&2
	rm -rf "$MODS_STAGE" "$BEFORE"
	exit 1
fi
rm -rf "$MODS_STAGE" "$BEFORE"

# ---------------------------------------------------------------------------
# 4. Restart (optional)
# ---------------------------------------------------------------------------
# Minecraft only reads its configuration at startup, so a config change needs
# a restart to take effect. Restarting kicks players, so it is opt-in.
if [ "$RESTART" = "1" ]; then
	echo "    restarting server via Crafty API"
	exec "$REPO_ROOT/scripts/crafty.sh" restart "$SERVER_ID"
fi

echo "==> minecraft config deployed to '$ENV'"
