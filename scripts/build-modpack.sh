#!/bin/sh
# build-modpack.sh — build the .mrpack file.
#
# The modpack is published to Modrinth, where players install it from and
# their launcher keeps it up to date. This script just builds the file;
# scripts/publish-modpack.py uploads it.
#
# Usage:  ./scripts/build-modpack.sh [output.mrpack]
#
# The output defaults to /tmp/HoneyBeeSMP.mrpack.

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
OUT=${1:-/tmp/HoneyBeeSMP.mrpack}

mkdir -p "$(dirname "$OUT")"

python3 "$REPO_ROOT/scripts/modpack.py" build "$OUT"

# A modpack is a zip, so it needs a name the launcher recognises.
case "$OUT" in
*.mrpack) ;;
*) echo "warning: $OUT does not end in .mrpack" >&2 ;;
esac
