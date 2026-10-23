#!/usr/bin/env python3
"""whitelist.py — build a Minecraft whitelist from the repo.

The whitelist for each environment lives in the repo, as a list of player
names:

    minecraft/env/dev/whitelist.txt

Minecraft's own whitelist file records each player's *UUID*, not their
name, so this resolves the names against Mojang's public API and writes
the whitelist.json the server expects.

Why not just use the server's console? Crafty's API route for console
commands only matches a single lowercase word, so "whitelist add <name>"
cannot be sent through it. Writing the file the server reads at startup
works, and it means the whitelist is reviewable in the repo like
everything else.

Usage:
    ./scripts/whitelist.py list  <dev|live>
    ./scripts/whitelist.py build <dev|live> <output-path>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

MOJANG_API = "https://api.mojang.com/users/profiles/minecraft"
USER_AGENT = "HoneyBeeSMP-whitelist/1.0 (honeybeesmp.co.uk)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_DIR = os.path.join(REPO, "minecraft", "env")


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str) -> None:
    print(msg, flush=True)


def read_names(env: str) -> list:
    """The names on the whitelist, in the order they are listed."""
    path = os.path.join(ENV_DIR, env, "whitelist.txt")
    if not os.path.exists(path):
        return []

    names = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line and line not in names:
                names.append(line)
    return names


def resolve(name: str) -> dict:
    """Look a name up on Mojang's API. Returns {"uuid", "name"}."""
    request = urllib.request.Request(
        f"{MOJANG_API}/{urllib.request.quote(name)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        if err.code == 204 or err.code == 404:
            die(
                f"'{name}' is not a Minecraft account.\n"
                f"  Check the spelling in the whitelist file."
            )
        die(f"Mojang API error {err.code} for {name}")
    except urllib.error.URLError as err:
        die(f"could not reach the Mojang API: {err.reason}")

    # The API returns the UUID as 32 hexadecimal characters with no
    # hyphens. Minecraft parses whitelist UUIDs with UUID.fromString,
    # which only accepts the canonical hyphenated form and otherwise
    # silently loads an empty whitelist. Store the canonical form.
    return {"uuid": str(uuid.UUID(body["id"])), "name": body["name"]}


def build(env: str) -> list:
    names = read_names(env)
    if not names:
        return []

    entries = []
    for name in names:
        entry = resolve(name)
        info(f"  {entry['name']} ({entry['uuid']})")
        entries.append(entry)
        # Mojang does not publish a rate limit for this endpoint, but it
        # is not meant to be hammered. A small pause is enough.
        time.sleep(0.2)
    return entries


def cmd_list(args) -> int:
    names = read_names(args.env)
    if not names:
        info(f"no whitelist for '{args.env}'")
        return 0
    info(f"whitelist for '{args.env}':")
    for name in names:
        info(f"  {name}")
    return 0


def cmd_build(args) -> int:
    entries = build(args.env)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")
    info(f"  wrote {len(entries)} entr(y/ies) to {args.output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show the names on the whitelist")
    p.add_argument("env", choices=["dev", "live"])
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("build", help="write whitelist.json")
    p.add_argument("env", choices=["dev", "live"])
    p.add_argument("output", help="path to write whitelist.json to")
    p.set_defaults(func=cmd_build)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
