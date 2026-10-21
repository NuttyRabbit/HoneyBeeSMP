#!/bin/sh
# install-ci-key.sh — create the SSH key pair GitHub Actions uses to deploy.
#
# GitHub Actions runs the deploy by SSHing into this server. It needs a key
# pair: the public half goes on this server's authorized_keys, the private
# half is pasted into the repository's Actions secrets.
#
# This script creates the key (if needed) and prints exactly what to paste
# into GitHub. It never prints the private key unless asked.
#
# Usage:  sudo ./scripts/install-ci-key.sh [--show-private]
#
# After running, add these repository secrets under
# Settings -> Secrets and variables -> Actions:
#
#   DEPLOY_SSH_KEY        the private key (see --show-private)
#   DEPLOY_HOST           the server address
#   DEPLOY_USER           the ssh user
#   DEPLOY_REPO_PATH      the repo path on the server
#   DEPLOY_SSH_KNOWN_HOSTS  the server's host key (optional but safer)

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
KEY_NAME=github-actions-deploy
KEY_PATH="$HOME/.ssh/$KEY_NAME"

SHOW_PRIVATE=0
[ "${1:-}" = "--show-private" ] && SHOW_PRIVATE=1

[ "$(id -u)" = "0" ] || { echo "run with sudo" >&2; exit 1; }

mkdir -p /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh

if [ ! -f "$KEY_PATH" ]; then
	echo "==> creating key pair $KEY_NAME"
	ssh-keygen -t ed25519 -N '' -C 'github-actions-deploy' -f "$KEY_PATH"
	chown ubuntu:ubuntu "$KEY_PATH" "$KEY_PATH.pub"
	chmod 600 "$KEY_PATH"
	chmod 644 "$KEY_PATH.pub"
else
	echo "==> key pair already exists at $KEY_PATH"
fi

# Authorise the public key for the deploy user.
AUTH=/home/ubuntu/.ssh/authorized_keys
touch "$AUTH"
chown ubuntu:ubuntu "$AUTH"
chmod 600 "$AUTH"
if ! grep -qF "$(cat "$KEY_PATH.pub")" "$AUTH"; then
	echo "==> adding public key to $AUTH"
	cat "$KEY_PATH.pub" >> "$AUTH"
else
	echo "==> public key already authorised"
fi

# The deploy user must be able to run the deploy without a password.
echo
echo "==> ensuring passwordless sudo for the deploy user"
if ! grep -q '^ubuntu ALL=(ALL) NOPASSWD:ALL$' /etc/sudoers; then
	echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/99-ubuntu-deploy
	chmod 440 /etc/sudoers.d/99-ubuntu-deploy
	echo "    added /etc/sudoers.d/99-ubuntu-deploy"
else
	echo "    already configured"
fi

echo
echo "=============================================================="
echo " Add these as repository secrets (Settings -> Secrets and"
echo " variables -> Actions -> New repository secret):"
echo "=============================================================="
echo
echo "DEPLOY_SSH_KEY"
if [ "$SHOW_PRIVATE" = "1" ]; then
	echo "-----BEGIN OPENSSH PRIVATE KEY-----"
	cat "$KEY_PATH"
	echo "-----END OPENSSH PRIVATE KEY-----"
else
	echo "  (run again with --show-private to print the private key)"
fi
echo
echo "DEPLOY_HOST"
echo "  132.145.16.69"
echo
echo "DEPLOY_USER"
echo "  ubuntu"
echo
echo "DEPLOY_REPO_PATH"
echo "  $REPO_ROOT"
echo
echo "DEPLOY_SSH_KNOWN_HOSTS  (optional, but recommended)"
echo "  $(cat /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null || echo '(no ed25519 host key found)')"
echo
echo "=============================================================="
