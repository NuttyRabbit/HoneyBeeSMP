#!/usr/bin/env python3
"""publish-modpack.py — publish the HoneyBeeSMP server to Modrinth.

Modrinth has a Server Project type (`minecraft_java_server`). A server
project is a *listing*: it names the address players connect to, and it
declares the content they need in order to join. Players who click play
in Modrinth App get that content installed and are dropped straight into
the server, and they are told when the server's content changes.

This project is one of those. The content it declares is our pack, and
the pack is the same `modrinth.index.json` the server deploys from - so
what players install and what the server runs cannot drift apart.

The pack is published as a version of the server project, and the
project's "content" is pointed at that version. When the pack changes,
publishing a new version and re-pointing the content is what tells every
linked client that there is an update.

Subcommands:
    create     create the Modrinth project (once)
    publish    build the pack and upload it as a new version
    status     show the project, its address and the content it serves
    submit     ask Modrinth to review the project
    sync-description  push the repo's description file to the project
    check      report which API scopes the token has

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
API_V3 = "https://api.modrinth.com/v3"
USER_AGENT = "HoneyBeeSMP-server/1.0 (honeybeesmp.co.uk)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_DIR = os.path.join(REPO, "minecraft", "modpack")
MC_DIR = os.path.join(REPO, "minecraft")
INDEX_PATH = os.path.join(PACK_DIR, "modrinth.index.json")
DESCRIPTION_PATH = os.path.join(PACK_DIR, "modrinth-description.md")
STATE_PATH = os.path.expanduser("~/.config/modrinth/project-id")

# The server project's own metadata. The address and the player count are
# read from the live environment's config instead, so the listing always
# says what the server actually does.
SERVER = {
    "name": "HoneyBeeSMP",
    "slug": "honeybeesmp",
    "country": "GB",
    "region": "europe",
    "languages": ["en"],
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
# The server's own settings
# ---------------------------------------------------------------------------


def read_env_conf(env: str = "live") -> dict:
    """Read an environment's settings out of minecraft/env/<env>/env.conf."""
    path = os.path.join(MC_DIR, "env", env, "env.conf")
    if not os.path.exists(path):
        die(f"no environment config at {path}")
    settings = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            settings[key.strip()] = value.strip()
    return settings


def server_address() -> str:
    """The address players connect to, as Modrinth wants it.

    The address and the port both come from the live environment's config,
    so the Modrinth listing cannot claim an address the server does not
    actually use.
    """
    env = read_env_conf("live")
    address = env.get("SERVER_ADDRESS", "")
    port = env.get("SERVER_PORT", "")
    if not address:
        die("no SERVER_ADDRESS in the live environment config")
    return f"{address}:{port}" if port else address


def max_players() -> int:
    """The player limit, from the server.properties template."""
    path = os.path.join(MC_DIR, "server.properties")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("max-players="):
                    return int(line.split("=", 1)[1].strip())
    except (OSError, ValueError):
        pass
    return 20


def read_description() -> tuple:
    """The project's description body and summary.

    The description lives in the repo so it is reviewed and versioned like
    everything else, and so the Modrinth page cannot drift from what we
    think it says.
    """
    if not os.path.exists(DESCRIPTION_PATH):
        die(f"no description at {DESCRIPTION_PATH}")
    with open(DESCRIPTION_PATH, encoding="utf-8") as fh:
        body = fh.read().strip()
    # The first line is the summary Modrinth shows in listings.
    summary = body.splitlines()[0].lstrip("# ").strip()
    return body, summary


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def auth_header(token: str) -> dict:
    return {"Authorization": token} if token else {}


def api_get(path: str, token: str = "", missing_ok: bool = False, v3: bool = False):
    base = API_V3 if v3 else API
    request = urllib.request.Request(
        f"{base}{path}", headers={"User-Agent": USER_AGENT, **auth_header(token)}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        if missing_ok and err.code == 404:
            return None
        body = err.read().decode()[:400]
        die(f"Modrinth API error {err.code} for {path}: {body}")
    except urllib.error.URLError as err:
        die(f"could not reach Modrinth: {err.reason}")


def api_json(method: str, path: str, token: str, data: dict, v3: bool = False):
    """Send a JSON request. Returns the response body, or None on a 204."""
    base = API_V3 if v3 else API
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(data).encode(),
        headers={
            "User-Agent": USER_AGENT,
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as err:
        detail = err.read().decode()[:600]
        die(f"Modrinth API error {err.code} for {path}: {detail}")
    except urllib.error.URLError as err:
        die(f"could not reach Modrinth: {err.reason}")


def api_post_multipart(path: str, token: str, data: dict, files: list, v3: bool = False):
    """POST a multipart request.

    Modrinth expects the metadata as a single form field named "data"
    holding the JSON, plus one field per uploaded file. The data field has
    to come first.

    files is a list of (field, filename, bytes).
    """
    base = API_V3 if v3 else API
    boundary = "----HoneyBeeSMPModpackBoundary7d91f3a2"
    body = bytearray()

    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="data"\r\n\r\n'
    body += json.dumps(data).encode() + b"\r\n"

    for field, filename, content in files:
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        ).encode()
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        f"{base}{path}",
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
# The pack
# ---------------------------------------------------------------------------


def load_index() -> dict:
    if not os.path.exists(INDEX_PATH):
        die(f"no pack index at {INDEX_PATH}")
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def pack_versions(index: dict) -> tuple:
    """The Minecraft version and the mod loader the pack is for."""
    deps = index.get("dependencies", {})
    game_versions = [deps["minecraft"]] if "minecraft" in deps else ["1.21.1"]
    loaders = [k for k in deps if k not in ("minecraft",)] or ["neoforge"]
    return game_versions, loaders


def build_pack(version_number: str) -> tuple:
    """Build the .mrpack and return (bytes, filename)."""
    pack_path = os.path.join("/tmp", f"HoneyBeeSMP-{version_number}.mrpack")
    info(f"building {pack_path}")
    os.system(
        f'python3 "{os.path.join(REPO, "scripts", "modpack.py")}" build "{pack_path}"'
    )
    if not os.path.exists(pack_path):
        die("the pack was not built")
    with open(pack_path, "rb") as fh:
        content = fh.read()
    os.unlink(pack_path)
    return content, f"HoneyBeeSMP-{version_number}.mrpack"


def upload_pack_version(
    token: str, project_id: str, version_number: str, changelog: str
) -> dict:
    """Build the pack and upload it as a new version of the project.

    The version is created with the "mrpack" loader and the pack's own
    loader in the mrpack_loaders field. That is what makes Modrinth treat
    the file as a modpack rather than as a jar, and it is what the client
    needs in order to install it.
    """
    index = load_index()
    game_versions, loaders = pack_versions(index)
    pack_bytes, pack_name = build_pack(version_number)

    data = {
        "project_id": project_id,
        "file_parts": [pack_name],
        "version_number": version_number,
        "version_title": f"{index.get('name', 'HoneyBeeSMP')} {version_number}",
        "version_body": changelog,
        "dependencies": [],
        "release_channel": "release",
        "loaders": ["mrpack"],
        "mrpack_loaders": loaders,
        "game_versions": game_versions,
        "environment": "client_and_server",
        "featured": False,
        "status": "listed",
    }

    info(f"uploading version {version_number} ...")
    result = api_post_multipart(
        "/version",
        token,
        data,
        [("file_parts", pack_name, pack_bytes)],
        v3=True,
    )
    info(f"  version id: {result.get('id')}")
    return result


def point_content_at(token: str, project_id: str, version_id: str) -> None:
    """Tell the project which version of the pack players need.

    This is what the client resolves when a player clicks play, and what
    it compares against to decide whether the player has an out-of-date
    instance. Moving it to a new version is what pushes the update.
    """
    api_json(
        "PATCH",
        f"/project/{project_id}",
        token,
        {
            "minecraft_java_server": {
                "address": server_address(),
                "content": {"kind": "modpack", "version_id": version_id},
            }
        },
        v3=True,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_create(args) -> int:
    token = read_token()
    if os.path.exists(STATE_PATH) and not args.force:
        info(f"project already exists: {read_project_id()}")
        return 0

    index = load_index()
    version_number = index.get("versionId", "1.0.0")
    body, summary = read_description()

    info(f"creating project '{SERVER['slug']}' ...")
    project = api_json(
        "PUT",
        "/project",
        token,
        {
            "base": {
                "name": SERVER["name"],
                "slug": SERVER["slug"],
                "summary": summary,
                "description": body,
                "requested_status": "approved",
                "organization_id": None,
            },
            "minecraft_server": {
                "max_players": max_players(),
                "country": SERVER["country"],
                "region": SERVER["region"],
                "languages": SERVER["languages"],
            },
            "minecraft_java_server": {
                "address": server_address(),
            },
        },
        v3=True,
    )
    project_id = project["id"]
    write_project_id(project_id)
    info(f"created project {project_id}")
    info(f"  slug:     {SERVER['slug']}")
    info(f"  address:  {server_address()}")
    info(f"  saved to: {STATE_PATH}")
    info("")

    # The pack is the content the server serves, so it has to be there
    # before the project is worth submitting for review.
    version = upload_pack_version(
        token, project_id, version_number, f"First release: {version_number}."
    )
    point_content_at(token, project_id, version["id"])
    info(f"  content:  pack {version_number} ({version['id']})")
    info("")
    info("The project is a draft. Approve it on Modrinth to make it public:")
    info(f"  https://modrinth.com/project/{project_id}/settings")
    return 0


def cmd_publish(args) -> int:
    token = read_token()
    project_id = read_project_id()

    index = load_index()
    version_number = index.get("versionId", "1.0.0")

    project = api_get(f"/project/{project_id}", token, v3=True)
    types = project.get("project_types") or []
    if "minecraft_java_server" not in types:
        die(
            f"project {project_id} is a {', '.join(types) or 'unknown'} project,\n"
            f"  not a server project. This script publishes to a server\n"
            f"  project, whose content is the pack."
        )

    # What the server is currently serving. If that is already the version
    # the repo describes, there is nothing to publish.
    content = (project.get("minecraft_java_server") or {}).get("content") or {}
    current_id = content.get("version_id")
    if current_id:
        current = api_get(f"/version/{current_id}", token, missing_ok=True, v3=True)
        if current and current.get("version_number") == version_number:
            info(f"version {version_number} is already published - nothing to do")
            return 0

    changelog = args.changelog or f"Modpack {version_number}"
    version = upload_pack_version(token, project_id, version_number, changelog)
    point_content_at(token, project_id, version["id"])
    info(f"published {version.get('version_number')} ({version.get('id')})")
    info(f"  url: https://modrinth.com/server/{SERVER['slug']}")
    return 0


def cmd_sync_description(args) -> int:
    """Push the repo's description file to the Modrinth project."""
    token = read_token()
    project_id = read_project_id()
    body, summary = read_description()

    info(f"syncing the description to project {project_id} ...")
    api_json(
        "PATCH",
        f"/project/{project_id}",
        token,
        {
            "name": SERVER["name"],
            "summary": summary,
            "description": body,
        },
        v3=True,
    )
    info(f"  description: {len(body)} characters")
    info(f"  summary:     {summary[:70]}")
    return 0


def cmd_submit(args) -> int:
    """Ask Modrinth to review the project.

    A new project starts as a draft. Only `requested_status` can be set
    through the API - changing `status` itself needs a permission an API
    token does not have - so this asks for the review rather than making
    the project public.
    """
    token = read_token()
    project_id = read_project_id()

    project = api_get(f"/project/{project_id}", token, v3=True)
    status = project.get("status")
    requested = project.get("requested_status")

    if status != "draft":
        info(f"project is already '{status}' - nothing to submit")
        return 0
    if requested == "approved":
        info("project is already queued for review")
        info(f"  https://modrinth.com/project/{project_id}/settings")
        return 0

    info("submitting the project for review ...")
    api_json(
        "PATCH",
        f"/project/{project_id}",
        token,
        {"requested_status": "approved"},
        v3=True,
    )
    info("submitted for review")
    info(f"  https://modrinth.com/project/{project_id}/settings")
    info("")
    info("Until a moderator approves it the project stays a draft, and")
    info("nobody but us can see it. The pack goes out as soon as it is.")
    return 0


def cmd_status(args) -> int:
    token = read_token()
    project_id = read_project_id()
    project = api_get(f"/project/{project_id}", token, v3=True)

    info(f"project {project.get('slug')} ({project_id})")
    info(f"  title:    {project.get('name')}")
    info(f"  type:     {', '.join(project.get('project_types') or [])}")
    info(f"  status:   {project.get('status')}")

    server = project.get("minecraft_server") or {}
    java = project.get("minecraft_java_server") or {}
    info(f"  address:  {java.get('address')}")
    info(f"  players:  {server.get('max_players')}")
    info(
        f"  where:    {server.get('country')} / {server.get('region')} / "
        f"{', '.join(server.get('languages') or [])}"
    )

    content = java.get("content") or {}
    if content.get("kind") == "modpack":
        info(f"  content:  modpack {content.get('project_name')}")
        version = api_get(
            f"/version/{content.get('version_id')}", token, missing_ok=True, v3=True
        )
        if version:
            info(
                f"  version:  {version.get('version_number')} "
                f"({version.get('status')})"
            )
        else:
            info(f"  version:  {content.get('version_id')} (not found)")
    else:
        info(f"  content:  {content.get('kind') or '(none)'}")
    return 0


def cmd_check(args) -> int:
    """Report which API scopes the token actually has.

    Modrinth answers each endpoint according to the token's scopes, so
    probing them is the only way to see what is missing.
    """
    token = read_token()
    info("token scopes (probed against the API):")

    # USER_READ: GET /v2/user is the canonical "who am I" call.
    try:
        request = urllib.request.Request(
            f"{API}/user", headers={"User-Agent": USER_AGENT, "Authorization": token}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            code = response.status
    except urllib.error.HTTPError as err:
        code = err.code
    except urllib.error.URLError:
        code = 0
    info(f"  {'USER_READ':<16} {'present' if code == 200 else 'MISSING'} (HTTP {code})")

    # PROJECT_CREATE: a project creation with an empty body. A valid
    # token gets a 400 about the payload; an invalid one gets 401.
    try:
        request = urllib.request.Request(
            f"{API}/project",
            data=(
                b"--x\r\nContent-Disposition: form-data; name=\"data\"\r\n\r\n"
                b"{\"title\":\"scope-probe\",\"description\":\"scope-probe\"}\r\n--x--\r\n"
            ),
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": token,
                "Content-Type": "multipart/form-data; boundary=x",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            code = response.status
    except urllib.error.HTTPError as err:
        code = err.code
    except urllib.error.URLError:
        code = 0
    info(f"  {'PROJECT_CREATE':<16} {'present' if code == 400 else 'MISSING'} (HTTP {code})")

    info("")
    info("Needed for publishing: PROJECT_CREATE, VERSION_CREATE, PROJECT_WRITE")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="path to the repository (default: autodetected)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="create the Modrinth project")
    p.add_argument("--force", action="store_true", help="create even if one exists")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("publish", help="build the pack and publish a new version")
    p.add_argument("--changelog", help="changelog text for this version")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("status", help="show the project and what it serves")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("submit", help="submit the project for review")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser(
        "sync-description", help="push the repo description to the project"
    )
    p.set_defaults(func=cmd_sync_description)

    p = sub.add_parser("check", help="report which API scopes the token has")
    p.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
