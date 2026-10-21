#!/usr/bin/env python3
"""server-config.py — apply our settings to a server's own config files.

Some server-side mods - LuckPerms, Open Parties and Claims - write their
own config on first run, with every option and a comment explaining it.
Shipping a copy of that file in the repo means tracking the mod's
defaults, which is nobody's job and goes stale on every mod update.

So instead the repo holds a short file of just the settings we want,
and this merges them into the config the mod generated:

    minecraft/server-config/openpartiesandclaims-server.toml

        permissionSystem = "luck_perms"
        primaryPartySystem = "default"

The merge only replaces keys that are already in the target file. A key
the mod has dropped is reported and left alone rather than being
invented, because a config file with a key in the wrong place is worse
than one that is missing it.

Usage:
    ./scripts/server-config.py merge <overrides> <current> <output>
"""

from __future__ import annotations

import os
import sys


def parse_overrides(path: str) -> dict:
    """The key = value pairs in an overrides file."""
    overrides = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            overrides[key.strip()] = value.strip()
    return overrides


def merge(overrides_path: str, current_path: str, output_path: str) -> int:
    """Write the current file with our overrides applied."""
    overrides = parse_overrides(overrides_path)

    if not os.path.exists(current_path):
        # The mod has not written its config yet - it does that on first
        # run. Nothing to merge into.
        print(
            f"  {os.path.basename(current_path)} does not exist yet - "
            f"nothing to merge",
            file=sys.stderr,
        )
        return 0

    with open(current_path, encoding="utf-8") as fh:
        lines = fh.readlines()

    applied = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in overrides:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}{key} = {overrides[key]}\n")
                applied.add(key)
                continue
        out.append(line)

    missing = [k for k in overrides if k not in applied]
    for key in missing:
        print(
            f"  warning: {os.path.basename(current_path)} has no setting "
            f"called '{key}' - the mod may have renamed it",
            file=sys.stderr,
        )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.writelines(out)
    return 0


def main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] != "merge":
        print(
            "usage: server-config.py merge <overrides> <current> <output>",
            file=sys.stderr,
        )
        return 2
    return merge(sys.argv[2], sys.argv[3], sys.argv[4])


if __name__ == "__main__":
    sys.exit(main())
