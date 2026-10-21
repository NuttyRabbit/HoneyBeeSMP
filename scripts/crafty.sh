#!/bin/sh
# crafty.sh — control the Crafty Controller panel from the command line.
#
# The panel's REST API is the supported way to start, stop and restart
# Minecraft servers. This script wraps it so deployment scripts do not have
# to know the details.
#
# Authentication: the panel signs its API tokens with a secret stored in its
# database. We mint a short-lived JWT with that secret and the admin user id.
# The secret is read from the database at call time, so this keeps working if
# the panel is ever re-keyed.
#
# Usage:
#   ./scripts/crafty.sh start   <server-id>
#   ./scripts/crafty.sh stop    <server-id>
#   ./scripts/crafty.sh restart <server-id>
#   ./scripts/crafty.sh status  <server-id>
#
# Exit: 0 on success, non-zero on failure.

set -eu

CONTAINER=crafty_container
API="https://127.0.0.1:8443/api/v2"

ACTION=${1:-}
SERVER_ID=${2:-}

usage() {
	echo "usage: $0 {start|stop|restart|status} <server-id>" >&2
	exit 2
}

[ -n "$ACTION" ] && [ -n "$SERVER_ID" ] || usage

case "$ACTION" in
start | stop | restart | status) ;;
*) usage ;;
esac

# Mint a short-lived API token using the panel's own signing secret, read
# fresh from the database so a re-key does not break this script.
mint_token() {
	sudo docker exec "$CONTAINER" /crafty/.venv/bin/python3 -c "
import jwt, time, sqlite3
c = sqlite3.connect('/crafty/app/config/db/crafty.sqlite')
secret = c.execute('select secret_api_key from crafty_settings').fetchone()[0]
uid = c.execute('select user_id from users where superuser = 1 limit 1').fetchone()[0]
print(jwt.encode({'user_id': uid, 'iat': int(time.time())}, secret, algorithm='HS256'))
"
}

TOKEN=$(mint_token 2>/dev/null | tail -1)
if [ -z "$TOKEN" ]; then
	echo "could not mint a Crafty API token" >&2
	exit 1
fi

# Call the panel API. Kept as a function rather than a string variable so
# the token stays a single quoted argument.
api() {
	curl -sk --max-time 30 \
		-H "Authorization: Bearer $TOKEN" \
		"$@"
}

# The panel API has no per-server "is it running" endpoint. Instead, look
# for a java process whose working directory is this server's directory —
# that is exact, whereas matching the command line would confuse the two
# servers with each other.
#
# This runs on the host, not inside the container: reading another
# process's /proc/<pid>/cwd needs CAP_SYS_PTRACE, which Docker does not
# grant by default. From the host, the path still ends in the server's
# directory, so the match works.
is_running() {
	sudo sh -c '
		for p in /proc/[0-9]*; do
			grep -qa java "$p/cmdline" 2>/dev/null || continue
			cwd=$(readlink "$p/cwd" 2>/dev/null) || continue
			case "$cwd" in
			*/servers/'"$SERVER_ID"') echo yes; exit 0 ;;
			esac
		done
		exit 1
	' 2>/dev/null | grep -q yes
}

case "$ACTION" in
start)
	# The API action name is start_server (not "start"); "start" is treated
	# as a console command and silently does nothing.
	echo "starting server $SERVER_ID"
	api -X POST "$API/servers/$SERVER_ID/action/start_server"
	;;
stop)
	echo "stopping server $SERVER_ID"
	api -X POST "$API/servers/$SERVER_ID/action/stop_server"
	;;
restart)
	# The panel's own restart action handles the stop-then-start sequence
	# and is what the web UI uses.
	if is_running; then
		echo "restarting server $SERVER_ID"
		api -X POST "$API/servers/$SERVER_ID/action/restart_server"
	else
		echo "server $SERVER_ID is not running - starting it"
		api -X POST "$API/servers/$SERVER_ID/action/start_server"
	fi
	;;
status)
	if is_running; then
		echo "running"
	else
		echo "stopped"
	fi
	;;
esac

echo
