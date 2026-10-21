#!/bin/sh
# install-autodeploy-timer.sh — schedule the polling auto-deploy.
#
# The GitHub Actions workflow is the primary deploy path: it fires within
# seconds of a push and shows a green check in the GitHub UI.
#
# This installs a systemd timer that runs scripts/autodeploy.sh every
# minute for each environment. It is the backstop: it keeps the servers in
# step with GitHub even if Actions is disabled, misconfigured, or has run
# out of minutes. Both paths take the same lock, so they never conflict.
#
# Needs sudo. Run once:  sudo ./scripts/install-autodeploy-timer.sh
#
# To disable it later:
#     sudo systemctl disable --now honeybeesmp-autodeploy-dev.timer
#     sudo systemctl disable --now honeybeesmp-autodeploy-live.timer

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
RUN_USER=ubuntu

[ "$(id -u)" = "0" ] || { echo "run with sudo" >&2; exit 1; }

for env in dev live; do
	cat > "/etc/systemd/system/honeybeesmp-autodeploy-$env.service" <<EOF
[Unit]
Description=HoneyBeeSMP auto-deploy ($env) from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
# systemd does not always export HOME for a system service, and the deploy
# state (which commit each environment is running) is kept under HOME.
Environment=HOME=/home/$RUN_USER
WorkingDirectory=$REPO_ROOT
ExecStart=/bin/sh $REPO_ROOT/scripts/autodeploy.sh $env
# A deploy should never overlap with itself.
TimeoutStartSec=30min
Nice=10

[Install]
WantedBy=multi-user.target
EOF

	cat > "/etc/systemd/system/honeybeesmp-autodeploy-$env.timer" <<EOF
[Unit]
Description=Poll GitHub for $env changes and deploy

[Timer]
# Every minute. The script is a no-op unless the branch has moved, so this
# is cheap - it is one git fetch.
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload
systemctl enable --now honeybeesmp-autodeploy-dev.timer
systemctl enable --now honeybeesmp-autodeploy-live.timer

echo
echo "installed. schedule:"
systemctl list-timers 'honeybeesmp-autodeploy-*' --no-pager
echo
echo "manual run:  sudo systemctl start honeybeesmp-autodeploy-dev.service"
echo "watch it:    journalctl -u honeybeesmp-autodeploy-dev.timer -f"
echo "log:         journalctl -u honeybeesmp-autodeploy-dev.service -f"
