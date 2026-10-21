#!/usr/bin/env python3
"""publish-modpack.py — publish the HoneyBeeSMP modpack to Modrinth.

Publishing to Modrinth rather than serving the .mrpack ourselves means
players who install the pack from Modrinth get updates pushed to them by
the launcher (Modrinth App and Prism Launcher both poll the project for new
versions), instead of having to re-download a file from our website.

The pack is built from the same modrinth.index.json the server deploys
from, so what players install and what the server runs cannot drift apart.

Subcommands:
    create     create the Modrinth project (once)
    publish    build the pack and upload it as a new version
    status     show the project and its latest published version

The API token is read from, in order of preference:
    $MODRINTH_TOKEN
    ~/.config/modrinth/token

Run it from the repo root, or with --repo <path>.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.modrinth.com/v2"
USER_AGENT = "HoneyBeeSMP-modpack/1.0 (honeybeesmp.co.uk)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_DIR = os.path.join(REPO, "minecraft", "modpack")
INDEX_PATH = os.path.join(PACK_DIR, "modrinth.index.json")
STATE_PATH = os.path.expanduser("~/.config/modrinth/project-id")

# The project metadata. Modrinth needs a title, a description and at least
# one category; the rest is our own.
PROJECT = {
    "title": "HoneyBeeSMP",
    "slug": "honeybeesmp",
    "description": "The official modpack for the HoneyBeeSMP Minecraft server.",
    "body": (
        "The mods and configs for the HoneyBeeSMP Minecraft server.\n\n"
        "Import this pack into Modrinth App, Prism Launcher or CurseForge "
        "and it will keep itself up to date: when the server changes its "
        "mods, the launcher offers you the new version before you play.\n\n"
        "Minecraft 1.21.1, NeoForge 21.1.264.\n"
        "Join us at honeybeesmp.co.uk on port 25566."
    ),
    "project_type": "modpack",
    "categories": ["utility", "technology"],
    "additional_categories": [],
    "environment": ["client_and_server"],
    "status": "listed",
    "requested_status": "listed",
    "license_id": "MIT",
}


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Token and state
# ---------------------------------------------------------------------------


def read_token() -> str:
    token = os.environ.get("MODRINTH_TOKEN", "").strip()
    if token:
        return token
    path = os.path.expanduser("~/.config/modrinth/token")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            token = fh.read().strip()
    if not token:
        die(
            "no Modrinth API token.\n"
            "  Create one at https://modrinth.com/settings/account with the\n"
            "  scopes 'Create versions' and 'Create projects', then either\n"
            "  export MODRINTH_TOKEN or save it to ~/.config/modrinth/token"
        )
    return token


def read_project_id() -> str:
    if not os.path.exists(STATE_PATH):
        die(
            "no Modrinth project yet - run: python3 scripts/publish-modpack.py create"
        )
    with open(STATE_PATH, encoding="utf-8") as fh:
        return fh.read().strip()


def write_project_id(project_id: str) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        fh.write(project_id + "\n")
    os.chmod(STATE_PATH, 0o600)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api_get(path: str, token: str = ""):
    request = urllib.request.Request(
        f"{API}{path}", headers={"User-Agent": USER_AGENT, **auth_header(token)}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode()[:400]
        die(f"Modrinth API error {err.code} for {path}: {body}")
    except urllib.error.URLError as err:
        die(f"could not reach Modrinth: {err.reason}")


def auth_header(token: str) -> dict:
    return {"Authorization": token} if token else {}


def api_post_multipart(path: str, token: str, data: dict, files: list):
    """POST a multipart request. files is a list of (field, filename, bytes)."""
    boundary = "----HoneyBeeSMPModpackBoundary7d91f3a2"
    body = bytearray()
    for key, value in data.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += json.dumps(value).encode() + b"\r\n"
    for field, filename, content in files:
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        ).encode()
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        f"{API}{path}",
        data=bytes(body),
        headers={
            "User-Agent": USER_AGENT,
            "Authorization": token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        detail = err.read().decode()[:600]
        die(f"Modrinth API error {err.code} for {path}: {detail}")
    except urllib.error.URLError as err:
        die(f"could not reach Modrinth: {err.reason}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_create(args) -> int:
    token = read_token()
    if os.path.exists(STATE_PATH) and not args.force:
        info(f"project already exists: {read_project_id()}")
        return 0

    index = load_index()
    deps = index.get("dependencies", {})
    game_versions = [deps["minecraft"]] if "minecraft" in deps else ["1.21.1"]
    loaders = [k for k in deps if k not in ("minecraft",)]

    data = dict(PROJECT)
    data["game_versions"] = game_versions
    data["loaders"] = loaders or ["neoforge"]

    info(f"creating project '{data['title']}' ...")
    result = api_post_multipart("/project", token, data, [])
    project_id = result["id"]
    write_project_id(project_id)
    info(f"created project {project_id}")
    info(f"  slug:     {result.get('slug')}")
    info(f"  url:      https://modrinth.com/modpack/{result.get('slug')}")
    info(f"  saved to: {STATE_PATH}")
    info("")
    info("Now publish the first version:")
    info("  python3 scripts/publish-modpack.py publish")
    return 0


def cmd_publish(args) -> int:
    token = read_token()
    project_id = read_project_id()

    index = load_index()
    version_number = index.get("versionId", "1.0.0")
    deps = index.get("dependencies", {})
    game_versions = [deps["minecraft"]] if "minecraft" in deps else ["1.21.1"]
    loaders = [k for k in deps if k not in ("minecraft",)] or ["neoforge"]

    # Build the pack.
    pack_path = os.path.join("/tmp", f"HoneyBeeSMP-{version_number}.mrpack")
    info(f"building {pack_path}")
    os.system(
        f'python3 "{os.path.join(REPO, "scripts", "modpack.py")}" build "{pack_path}"'
    )
    if not os.path.exists(pack_path):
        die("the pack was not built")
    with open(pack_path, "rb") as fh:
        pack_bytes = fh.read()

    # The project must exist and the version must not already be published.
    existing = api_get(f"/project/{project_id}/version", token)
    for version in existing:
        if version.get("version_number") == version_number:
            die(
                f"version {version_number} is already published on Modrinth.\n"
                f"  Bump the pack version before publishing:\n"
                f"    python3 scripts/modpack.py bump"
            )

    data = {
        "name": f"{index.get('name', 'HoneyBeeSMP')} {version_number}",
        "version_number": version_number,
        "changelog": args.changelog or f"Modpack {version_number}",
        "game_versions": game_versions,
        "loaders": loaders,
        "version_type": "release",
        "status": "listed",
        "requested_status": "listed",
        "environment": "client_and_server",
        "dependencies": [
            {
                "project_id": entry["project_id"],
                "version_id": entry.get("version_id"),
                "file_name": entry.get("file_name"),
                "dependency_type": "embedded",
            }
            for entry in args.embedded
        ]
        if args.embedded
        else [],
    }

    info(f"publishing version {version_number} ...")
    result = api_post_multipart(
        f"/project/{project_id}/version",
        token,
        data,
        [("file_parts", f"HoneyBeeSMP-{version_number}.mrpack", pack_bytes)],
    )
    info(f"published {result.get('version_number')} ({result.get('id')})")
    info(f"  url: https://modrinth.com/modpack/{project_id}/version/{result.get('id')}")
    os.unlink(pack_path)
    return 0


def cmd_status(args) -> int:
    token = read_token()
    project_id = read_project_id()
    project = api_get(f"/project/{project_id}", token)
    info(f"project {project.get('slug')} ({project_id})")
    info(f"  title:    {project.get('title')}")
    info(f"  status:   {project.get('status')}")
    info(f"  versions: {', '.join(project.get('game_versions', []))}")
    info(f"  loaders:  {', '.join(project.get('loaders', []))}")
    versions = api_get(f"/project/{project_id}/version", token)
    if versions:
        latest = versions[0]
        info(f"  latest:   {latest.get('version_number')} ({latest.get('date_published','')[:10]})")
    else:
        info("  latest:   (nothing published yet)")
    return 0


def load_index() -> dict:
    if not os.path.exists(INDEX_PATH):
        die(f"no pack index at {INDEX_PATH}")
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="path to the repository (default: autodetected)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="create the Modrinth project")
    p.add_argument("--force", action="store_true", help="create even if one exists")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("publish", help="build the pack and publish a new version")
    p.add_argument("--changelog", help="changelog text for this version")
    p.add_argument(
        "--embedded",
        nargs="*",
        help="mods to record as embedded dependencies, as project_id or project_id:version_id",
    )
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("status", help="show the project and latest version")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
