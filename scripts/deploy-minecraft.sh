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

# Read the environment's settings (SERVER_ID, SERVER_PORT).
SERVER_ID=""
SERVER_PORT=""
while IFS='=' read -r key value; do
	case "$key" in
	"") continue ;;
	\#*) continue ;;
	SERVER_ID) SERVER_ID=$value ;;
	SERVER_PORT) SERVER_PORT=$value ;;
	esac
done < "$ENV_FILE"

if [ -z "$SERVER_ID" ] || [ -z "$SERVER_PORT" ]; then
	echo "env.conf for '$ENV' is missing SERVER_ID or SERVER_PORT" >&2
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
# The template carries @SERVER_PORT@; the environment supplies the real value.
RENDERED=$(mktemp)
sed "s/@SERVER_PORT@/$SERVER_PORT/g" "$MC_SRC/server.properties" > "$RENDERED"

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
# 2. Sync NeoForge config
# ---------------------------------------------------------------------------
# These are the server's behaviour settings (world generation, tick rates,
# dimension rules...). Syncing these is how a config change is promoted from
# dev to live.
for sub in config defaultconfigs; do
	if [ ! -d "$MC_SRC/$sub" ]; then
		continue
	fi
	echo "    syncing $sub/"
	sudo mkdir -p "$TARGET/$sub"
	# The server runs as the "opc" user, so the files must be owned by it
	# (and group root, matching the rest of the server directory) or the
	# server cannot write its own config.
	sudo rsync -a \
		--no-group --no-perms --omit-dir-times \
		--chown=opc:root \
		"$MC_SRC/$sub/" "$TARGET/$sub/"
done

# ---------------------------------------------------------------------------
# 3. Reconcile mods
# ---------------------------------------------------------------------------
# Every mod listed in the manifest must exist on the server; any mod on the
# server that is not listed is removed. This keeps dev and live identical.
MANIFEST="$MC_SRC/mods/mods.manifest"
if [ -f "$MANIFEST" ]; then
	echo "    reconciling mods"
	sudo mkdir -p "$TARGET/mods"

	# Build the list of wanted mod filenames.
	wanted=$(mktemp)
	grep -vE '^\s*(#|$)' "$MANIFEST" | awk '{print $1}' | sort > "$wanted"

	# Download anything that is missing.
	while read -r name url; do
		[ -n "$name" ] || continue
		if sudo test -f "$TARGET/mods/$name"; then
			continue
		fi
		if [ -z "${url:-}" ]; then
			echo "    mod '$name' listed with no URL - skipping download" >&2
			continue
		fi
		echo "    downloading $name"
		tmp_jar=$(mktemp)
		if curl -fsSL "$url" -o "$tmp_jar"; then
			sudo mv "$tmp_jar" "$TARGET/mods/$name"
			sudo chown opc:root "$TARGET/mods/$name" 2>/dev/null || true
		else
			echo "    FAILED to download $name" >&2
			rm -f "$tmp_jar"
		fi
	done <<EOF
$(grep -vE '^\s*(#|$)' "$MANIFEST")
EOF

	# Remove mods that are no longer listed.
	sudo ls -1 "$TARGET/mods" 2>/dev/null | while read -r present; do
		[ -n "$present" ] || continue
		case "$present" in
		*.jar) ;;
		*) continue ;;
		esac
		if ! grep -qxF "$present" "$wanted"; then
			echo "    removing unlisted mod $present"
			sudo rm -f "$TARGET/mods/$present"
		fi
	done
	rm -f "$wanted"
fi

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
