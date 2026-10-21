#!/usr/bin/env python3
"""server-config.py — apply our settings to a server's own config files.

Some server-side mods - LuckPerms, Open Parties and Claims, Simple Voice
Chat - write their own config on first run, with every option and a
comment explaining it. Shipping a copy of those files in the repo means
tracking the mods' defaults, which is nobody's job and goes stale on
every update.

So instead the repo holds just the settings we want changed:

    minecraft/server-config/            shared, applied to every environment
    minecraft/env/<env>/server-config/  per environment, applied on top

and this merges them into the config the mod generated. Only keys that
are already in the target are replaced; a key the mod has renamed is
reported and left alone, because a setting in the wrong place is worse
than a missing one.

The target is found by path: an override at `voicechat/voicechat-server.properties`
lands in the server's `config/voicechat/voicechat-server.properties`.

Usage:
    ./scripts/server-config.py merge <overrides-dir> <config-dir>
"""

from __future__ import annotations

import os
import sys


def parse_overrides(path: str) -> dict:
    """The key/value pairs in an override file.

    Both `key = value` and `key=value` are understood, so the same tool
    handles TOML and properties files.
    """
    overrides = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            overrides[key.strip()] = value.strip()
    return overrides


def merge_file(overrides_path: str, target_path: str) -> bool:
    """Merge an override file into a target file.

    Returns True if the target was changed.
    """
    overrides = parse_overrides(overrides_path)
    if not overrides:
        return False

    if not os.path.exists(target_path):
        # The mod has not written its config yet - it does that on first
        # run. The override will be applied on the next deploy.
        print(
            f"  {os.path.basename(target_path)} does not exist yet - "
            f"the override will be applied on the next deploy",
            file=sys.stderr,
        )
        return False

    with open(target_path, encoding="utf-8") as fh:
        original = fh.read()
    lines = original.splitlines(keepends=True)

    applied = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            # Keep everything up to and including the "=", so the target's
            # own indentation and spacing survive, and swap only the value.
            index = line.index("=")
            prefix = line[: index + 1]
            after = line[index + 1 :]
            # Whether the target puts a space after the "=" - keep it.
            space = " " if after.startswith(" ") else ""
            key = line[:index].strip()
            if key in overrides:
                out.append(f"{prefix}{space}{overrides[key]}\n")
                applied.add(key)
                continue
        out.append(line)

    for key in overrides:
        if key not in applied:
            print(
                f"  warning: {os.path.basename(target_path)} has no setting "
                f"called '{key}' - the mod may have renamed it",
                file=sys.stderr,
            )

    updated = "".join(out)
    if updated == original:
        return False
    with open(target_path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    return True


def merge(overrides_dir: str, config_dir: str) -> int:
    """Merge every override file under a directory into the config dir."""
    if not os.path.isdir(overrides_dir):
        return 0

    changed = 0
    for root, _dirs, files in os.walk(overrides_dir):
        for name in sorted(files):
            if name.startswith("."):
                continue
            overrides_path = os.path.join(root, name)
            relative = os.path.relpath(overrides_path, overrides_dir)
            target_path = os.path.join(config_dir, relative)
            if not os.path.exists(target_path):
                print(
                    f"  {relative} does not exist yet - the override will be "
                    f"applied on the next deploy",
                    file=sys.stderr,
                )
                continue
            if merge_file(overrides_path, target_path):
                print(f"  {relative} updated")
                changed += 1
            else:
                print(f"  {relative} unchanged")
    return changed


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] != "merge":
        print(
            "usage: server-config.py merge <overrides-dir> <config-dir>",
            file=sys.stderr,
        )
        return 2
    merge(sys.argv[2], sys.argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
