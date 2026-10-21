#!/bin/sh
# install-bot.sh — set up the Discord bot on the server.
#
# Makes a virtual environment, installs the bot's requirements into it,
# and installs a systemd unit so the bot runs on boot.
#
# The bot's secrets live in <dir>/.env, which is not in git. This script
# refuses to start the bot without it.
#
# The server's Python has no pip and no ensurepip, and installing into the
# system Python is blocked by PEP 668. So pip is bootstrapped into the
# virtual environment instead, which is both allowed and tidy.
#
# Usage:
#   sudo ./scripts/install-bot.sh [dev|live]

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ENVIRONMENT=${1:-live}
case "$ENVIRONMENT" in
dev) BOT_DIR=/opt/honeybee-discord-bot-dev ;;
live) BOT_DIR=/opt/honeybee-discord-bot ;;
*)
	echo "usage: $0 [dev|live]" >&2
	exit 2
	;;
esac

VENV="$BOT_DIR/.venv"
UNIT=/etc/systemd/system/honeybeesmp-discord-bot.service

[ -f "$BOT_DIR/.env" ] || {
	echo "error: $BOT_DIR/.env does not exist." >&2
	echo "  It holds the bot token, and it is not in git. Create it with:" >&2
	echo "    cp $BOT_DIR/.env.example $BOT_DIR/.env" >&2
	echo "  and fill it in, then run this again." >&2
	exit 1
}

echo "==> virtual environment"
if [ ! -x "$VENV/bin/python" ]; then
	python3 -m venv --without-pip "$VENV"
fi
if [ ! -x "$VENV/bin/pip" ]; then
	echo "    bootstrapping pip"
	curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
	"$VENV/bin/python" /tmp/get-pip.py --quiet
	rm -f /tmp/get-pip.py
fi

echo "==> requirements"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$BOT_DIR/requirements.txt"
"$VENV/bin/python" -c "import discord; print('    discord.py', discord.__version__)"

echo "==> systemd unit"
cat > "$UNIT" <<EOF
[Unit]
Description=HoneyBeeSMP Discord bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env
Environment=PYTHONPATH=$BOT_DIR/src
ExecStart=$VENV/bin/python -m honeybee_bot
Restart=always
RestartSec=15
# Give the bot a moment to be killed before systemd kills it harder.
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable honeybeesmp-discord-bot.service
systemctl restart honeybeesmp-discord-bot.service

sleep 4
echo
systemctl status honeybeesmp-discord-bot.service --no-pager -l | head -12
echo
echo "logs:  journalctl -u honeybeesmp-discord-bot.service -f"
