#!/bin/sh
# install-backup-timer.sh — schedule the rclone backup with a systemd timer.
#
# Runs scripts/backup.sh twice daily (03:00 and 15:00 UTC) and on boot if a
# run was missed. systemd is used rather than cron because this host already
# runs systemd, the timer survives reboots, and `systemctl list-timers` makes
# the schedule inspectable.
#
# Needs sudo. Run once:  sudo ./scripts/install-backup-timer.sh

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
RUN_USER=ubuntu

[ "$(id -u)" = "0" ] || { echo "run with sudo" >&2; exit 1; }

cat > /etc/systemd/system/honeybeesmp-backup.service <<EOF
[Unit]
Description=HoneyBeeSMP backup to Google Drive (rclone)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$REPO_ROOT
ExecStart=/bin/sh $REPO_ROOT/scripts/backup.sh
# A backup should never run twice at once, and should be allowed to finish.
TimeoutStartSec=6h
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=6

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/honeybeesmp-backup.timer <<'EOF'
[Unit]
Description=Run the HoneyBeeSMP backup twice daily

[Timer]
OnCalendar=*-*-* 03:00:00 UTC
OnCalendar=*-*-* 15:00:00 UTC
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now honeybeesmp-backup.timer

echo
echo "installed. schedule:"
systemctl list-timers honeybeesmp-backup.timer --no-pager
echo
echo "manual run:   sudo systemctl start honeybeesmp-backup.service"
echo "watch it:     journalctl -u honeybeesmp-backup.service -f"
