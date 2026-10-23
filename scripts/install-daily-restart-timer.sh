#!/bin/sh
# install-daily-restart-timer.sh - schedule the daily Minecraft restart.
#
# A server that is never restarted slowly drifts: memory fragments, caches
# grow, and deployments made during the day sit unused until something
# restarts the process. Restarting once a day at a quiet hour keeps it
# predictable - and it means "pushing to live" no longer leaves mod and
# config changes waiting indefinitely, because they are picked up by the
# next daily restart.
#
# 05:00 Europe/London is the quietest hour for this server's players: late
# evening in North America has finished, and the UK/EU morning has not
# started. The timezone is part of the calendar spec, not the host clock
# (the host runs on UTC), so the restart stays at 05:00 local time across
# the BST/GMT change instead of drifting an hour twice a year.
#
# Needs sudo. Run once:  sudo ./scripts/install-daily-restart-timer.sh
#
# To disable it later:
#     sudo systemctl disable --now honeybeesmp-daily-restart.timer

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
RUN_USER=ubuntu

[ "$(id -u)" = "0" ] || { echo "run with sudo" >&2; exit 1; }

cat > "/etc/systemd/system/honeybeesmp-daily-restart.service" <<EOF
[Unit]
Description=HoneyBeeSMP daily Minecraft restart (live)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
# systemd does not always export HOME for a system service, and the deploy
# state is kept under HOME.
Environment=HOME=/home/$RUN_USER
WorkingDirectory=$REPO_ROOT
ExecStart=/bin/sh $REPO_ROOT/scripts/daily-restart.sh live
# The script spends 10 minutes warning players before it stops anything.
TimeoutStartSec=30min
Nice=10

[Install]
WantedBy=multi-user.target
EOF

cat > "/etc/systemd/system/honeybeesmp-daily-restart.timer" <<EOF
[Unit]
Description=Daily 05:00 restart of the live Minecraft server

[Timer]
# London time, not host time: the host is on UTC.
OnCalendar=*-*-* 05:00:00 Europe/London
AccuracySec=30s
# Do not catch up a missed run. If the machine is off at 05:00 and boots
# at 09:00, restarting the moment it comes up would be worse than waiting
# for tomorrow.
Persistent=false

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now honeybeesmp-daily-restart.timer

echo
echo "installed. schedule:"
systemctl list-timers 'honeybeesmp-daily-restart.timer' --no-pager
echo
echo "test without touching the server:  sudo -u $RUN_USER sh $REPO_ROOT/scripts/daily-restart.sh live --dry-run"
echo "run it now (kicks players):        sudo systemctl start honeybeesmp-daily-restart.service"
echo "watch it:                          journalctl -u honeybeesmp-daily-restart.service -f"
