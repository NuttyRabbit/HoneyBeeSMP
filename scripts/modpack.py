#!/usr/bin/env python3
"""modpack.py — manage the HoneyBeeSMP Minecraft modpack.

The pack is described by a Modrinth index file (modrinth.index.json).
That format is the community standard: Modrinth and Prism Launcher
and ATLauncher all understand it, and every entry records which side the
file belongs to (client, server, or both) along with a hash to verify the
download.

That last part is why we use it rather than a hand-written list. Server mods
and client mods are DIFFERENT sets - a world-generation mod is
server-only, a rendering mod is client-only - and the pack format is the
only place that distinction can be expressed. It also means players can
download the same pack the server runs.

Subcommands:
    add <slug> [...]   add a mod (and its required dependencies) to the pack
    list [client|server|both]
                        show what is in the pack
    install <dir>      download and verify the server-side files into <dir>
    build <out.mrpack> build the distributable pack for players
    verify <dir>       check the files in <dir> against the pack
    export <out.json>  dump the pack as JSON (for other tooling)

Run it from the repo root, or with --repo <path>.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

API = "https://api.modrinth.com/v2"
USER_AGENT = "HoneyBeeSMP-modpack/1.0 (server deploy tooling)"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_DIR = os.path.join(REPO, "minecraft", "modpack")
INDEX_PATH = os.path.join(PACK_DIR, "modrinth.index.json")
OVERRIDES = os.path.join(PACK_DIR, "overrides")
CLIENT_OVERRIDES = os.path.join(PACK_DIR, "client-overrides")
SERVER_OVERRIDES = os.path.join(PACK_DIR, "server-overrides")

# The default pack identity. Kept in the index file itself so a downloaded
# pack identifies itself correctly.
DEFAULT_NAME = "HoneyBeeSMP"
DEFAULT_SUMMARY = "The mods and configs for the HoneyBeeSMP Minecraft server."


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------


def read_env_conf(env: str) -> dict:
    """Read minecraft/env/<env>/env.conf into a dict."""
    path = os.path.join(REPO, "minecraft", "env", env, "env.conf")
    if not os.path.exists(path):
        die(f"no environment config at {path}")
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def mc_version(env: str) -> str:
    conf = read_env_conf(env)
    for key in ("MC_VERSION", "MINECRAFT_VERSION"):
        if key in conf:
            return conf[key]
    die(f"MC_VERSION is not set in minecraft/env/{env}/env.conf")


def loader(env: str) -> tuple[str, str]:
    """Return (loader name, loader version) for the environment."""
    conf = read_env_conf(env)
    name = conf.get("LOADER", "neoforge")
    version = conf.get("LOADER_VERSION", "")
    if not version:
        die(f"LOADER_VERSION is not set in minecraft/env/{env}/env.conf")
    return name, version


# ---------------------------------------------------------------------------
# The index file
# ---------------------------------------------------------------------------


def load_index() -> dict:
    if not os.path.exists(INDEX_PATH):
        die(f"no pack index at {INDEX_PATH}")
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def save_index(index: dict) -> None:
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, sort_keys=False)
        fh.write("\n")
    info(f"wrote {os.path.relpath(INDEX_PATH, REPO)}")


def side_value(project: dict, key: str) -> str:
    """Map Modrinth's client_side/server_side onto the pack format."""
    value = project.get(key) or "unsupported"
    if value not in ("required", "optional", "unsupported"):
        value = "unsupported"
    return value


def api_get(path: str):
    request = urllib.request.Request(f"{API}{path}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        die(f"Modrinth API error {err.code} for {path}")
    except urllib.error.URLError as err:
        die(f"could not reach Modrinth: {err.reason}")


def find_version(slug: str, game: str, loader_name: str, loader_version: str) -> tuple[dict, dict]:
    """Find the best version of a project for our game and loader.

    Returns (project, version). Picks the newest version that supports both
    the game version and the loader, preferring one that is not a beta.
    """
    project = api_get(f"/project/{slug}")
    versions = api_get(
        f"/project/{slug}/version"
        f"?game_versions=%5B%22{game}%22%5D&loaders=%5B%22{loader_name}%22%5D"
    )
    if not versions:
        die(
            f"'{project.get('title', slug)}' has no build for "
            f"Minecraft {game} on {loader_name}"
        )

    # Prefer release versions, and the newest of those.
    releases = [v for v in versions if v.get("version_type") == "release"]
    candidates = releases or versions
    candidates.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    version = candidates[0]

    if loader_version:
        wanted = loader_version.lstrip("v")
        if not any(
            wanted == str(v).lstrip("v") or str(v).lstrip("v").startswith(wanted)
            for v in version.get("loaders", [])
        ):
            info(
                f"  note: {project.get('title', slug)} {version.get('version_number')} "
                f"targets loader {version.get('loaders')}, we use {loader_version}"
            )
    return project, version


def entry_from_version(project: dict, version: dict) -> dict:
    """Build a pack entry for a version."""
    primary = None
    for f in version.get("files", []):
        if f.get("primary"):
            primary = f
            break
    if primary is None and version.get("files"):
        primary = version["files"][0]
    if primary is None:
        die(f"no downloadable file for {project.get('slug')}")

    return {
        "path": f"mods/{primary['filename']}",
        "hashes": {
            "sha1": primary["hashes"]["sha1"],
            "sha512": primary["hashes"]["sha512"],
        },
        "env": {
            "client": side_value(project, "client_side"),
            "server": side_value(project, "server_side"),
        },
        "downloads": [primary["url"]],
        "fileSize": primary["size"],
    }


def existing_paths(index: dict) -> set:
    return {f["path"] for f in index.get("files", [])}


def next_version(index: dict, major: bool = False, minor: bool = False) -> str:
    """Move the pack version on, and return the new one.

    Modrinth refuses a version number it has already seen, so the pack
    version has to move forward every time the pack's contents change.
    Bumping it here - rather than only when publishing - keeps the version
    in the repo an honest description of the pack, so a deploy knows
    whether there is anything new to publish.
    """
    current = index.get("versionId", "1.0.0")
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")

    try:
        major_num, minor_num, patch = (int(p) for p in parts[:3])
    except ValueError:
        die(f"versionId '{current}' is not a plain version number")

    if major:
        major_num, minor_num, patch = major_num + 1, 0, 0
    elif minor:
        major_num, minor_num, patch = major_num, minor_num + 1, 0
    else:
        patch += 1

    return f"{major_num}.{minor_num}.{patch}"


def cmd_add(args) -> int:
    env = args.env
    game = mc_version(env)
    loader_name, loader_version = loader(env)

    index = load_index()
    known = existing_paths(index)
    added = 0
    queue = list(args.slug)
    seen = set()
    # Only the mods that were asked for by name are forced to be
    # server-only. A dependency pulled in behind one of them might well be
    # wanted on the client too.
    explicit = set(args.slug)

    while queue:
        slug = queue.pop(0)
        if slug in seen:
            continue
        seen.add(slug)

        project, version = find_version(slug, game, loader_name, loader_version)
        entry = entry_from_version(project, version)
        if args.server_only and slug in explicit:
            # Modrinth's metadata says this mod is fine on a client, but
            # it is really a server tool - Chunky pre-generates the world,
            # and there is nothing for a player to do with it.
            entry["env"]["client"] = "unsupported"
        title = project.get("title", slug)

        if entry["path"] in known:
            info(f"  {title}: already in the pack")
        else:
            index.setdefault("files", []).append(entry)
            known.add(entry["path"])
            added += 1
            info(
                f"  {title} {version.get('version_number')} -> {entry['path']} "
                f"(client: {entry['env']['client']}, server: {entry['env']['server']})"
            )

        # Pull in required dependencies. This is the bit that stops the
        # server refusing to start with "requires X or above".
        for dep in version.get("dependencies", []):
            if dep.get("dependency_type") != "required":
                continue
            dep_slug = dep.get("project_id")
            if not dep_slug:
                continue
            if dep_slug not in seen:
                queue.append(dep_slug)

    if added:
        index.setdefault("dependencies", {})
        index["dependencies"]["minecraft"] = game
        index["dependencies"][loader_name] = loader_version
        index.setdefault("formatVersion", 1)
        index.setdefault("game", "minecraft")
        index.setdefault("name", DEFAULT_NAME)
        index.setdefault("summary", DEFAULT_SUMMARY)
        index.setdefault("versionId", "1.0.0")
        # The pack's contents have changed, so its version has to move on.
        # Otherwise the next publish would try to send a version Modrinth
        # has already seen, and be refused.
        index["versionId"] = next_version(index)
        info(f"  pack version -> {index['versionId']}")
        save_index(index)
    else:
        info("nothing to add")

    info(f"{added} mod(s) added")
    return 0


def cmd_list(args) -> int:
    index = load_index()
    wanted = args.side
    for entry in index.get("files", []):
        env = entry.get("env") or {}
        if wanted == "client" and env.get("client") == "unsupported":
            continue
        if wanted == "server" and env.get("server") == "unsupported":
            continue
        if wanted == "both" and not (
            env.get("client") != "unsupported" and env.get("server") != "unsupported"
        ):
            continue
        print(
            f"{entry['path']:<60} client={env.get('client', 'unsupported'):<11} "
            f"server={env.get('server', 'unsupported')}"
        )
    return 0

def download(url: str, dest: str) -> str:
    """Download a file, returning its sha512."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha512()
    with urllib.request.urlopen(request, timeout=180) as response, open(dest, "wb") as fh:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            digest.update(chunk)
            fh.write(chunk)
    return digest.hexdigest()


def cmd_install(args) -> int:
    """Install the server-side files into a mods directory, and remove
    anything that is no longer part of the pack."""
    index = load_index()
    mods_dir = args.directory
    os.makedirs(mods_dir, exist_ok=True)

    wanted = {}
    for entry in index.get("files", []):
        env = entry.get("env") or {}
        if env.get("server") == "unsupported":
            continue
        wanted[os.path.basename(entry["path"])] = entry

    for name, entry in sorted(wanted.items()):
        target = os.path.join(mods_dir, name)
        expected = entry.get("hashes", {}).get("sha512")

        if os.path.exists(target) and expected:
            actual = hashlib.sha512()
            with open(target, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 256), b""):
                    actual.update(chunk)
            if actual.hexdigest() == expected:
                info(f"    {name}: already correct")
                continue

        info(f"    downloading {name}")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            actual = download(entry["downloads"][0], tmp_path)
            if expected and actual != expected:
                die(f"hash mismatch for {name} - download is corrupt")
            shutil.move(tmp_path, target)
            os.chmod(target, 0o644)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Remove files that are no longer in the pack.
    for name in sorted(os.listdir(mods_dir)):
        if not name.endswith(".jar"):
            continue
        if name not in wanted:
            info(f"    removing {name} (not in the pack)")
            os.unlink(os.path.join(mods_dir, name))

    info(f"    {len(wanted)} server-side mod(s) in place")
    return 0


def cmd_verify(args) -> int:
    index = load_index()
    mods_dir = args.directory
    bad = 0
    for entry in index.get("files", []):
        env = entry.get("env") or {}
        if env.get("server") == "unsupported":
            continue
        name = os.path.basename(entry["path"])
        target = os.path.join(mods_dir, name)
        expected = entry.get("hashes", {}).get("sha512")
        if not os.path.exists(target):
            info(f"    MISSING {name}")
            bad += 1
            continue
        digest = hashlib.sha512()
        with open(target, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 256), b""):
                digest.update(chunk)
        if expected and digest.hexdigest() != expected:
            info(f"    CORRUPT {name}")
            bad += 1
        else:
            info(f"    ok {name}")
    if bad:
        info(f"{bad} file(s) do not match the pack")
        return 1
    return 0


def add_dir_to_zip(zf: zipfile.ZipFile, source: str, arcname: str) -> None:
    if not os.path.isdir(source):
        return
    for root, _dirs, files in os.walk(source):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, source)
            zf.write(full, os.path.join(arcname, rel))


def cmd_build(args) -> int:
    index = load_index()
    out = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("modrinth.index.json", json.dumps(index, indent=2) + "\n")
        add_dir_to_zip(zf, OVERRIDES, "overrides")
        add_dir_to_zip(zf, CLIENT_OVERRIDES, "client-overrides")
        add_dir_to_zip(zf, SERVER_OVERRIDES, "server-overrides")

    size = os.path.getsize(out)
    info(f"built {out} ({size} bytes, {len(index.get('files', []))} mod(s))")
    return 0


def cmd_export(args) -> int:
    index = load_index()
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")
    return 0


def cmd_remove(args) -> int:
    """Take a mod out of the pack.

    The mod is matched by its Modrinth project, so every version of it
    that is in the pack comes out. Anything that was only in the pack
    because this mod needed it is left alone - an extra mod is harmless,
    and guessing which dependencies are now redundant is not.
    """
    index = load_index()
    project = api_get(f"/project/{args.slug}")
    versions = api_get(f"/project/{args.slug}/version")

    filenames = set()
    for version in versions:
        for f in version.get("files", []):
            if f.get("filename"):
                filenames.add(f["filename"])

    if not filenames:
        die(f"'{args.slug}' has no downloadable files")

    kept = []
    removed = []
    for entry in index.get("files", []):
        if os.path.basename(entry.get("path", "")) in filenames:
            removed.append(entry)
        else:
            kept.append(entry)

    if not removed:
        info(f"'{project.get('title', args.slug)}' is not in the pack")
        return 0

    for entry in removed:
        info(f"  removed {entry['path']}")

    index["files"] = kept
    index["versionId"] = next_version(index)
    info(f"  pack version -> {index['versionId']}")
    save_index(index)
    return 0


def cmd_bump(args) -> int:
    """Bump the pack version.

    Modrinth refuses to publish a version number that already exists on the
    project, so the pack version has to move forward before each publish.
    """
    index = load_index()
    current = index.get("versionId", "1.0.0")
    index["versionId"] = next_version(index, major=args.major, minor=args.minor)
    save_index(index)
    info(f"version: {current} -> {index['versionId']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="path to the repository (default: autodetected)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="add a mod to the pack")
    p.add_argument("slug", nargs="+", help="Modrinth project slug or id")
    p.add_argument("--env", default="dev", help="environment to resolve for (default: dev)")
    p.add_argument(
        "--server-only",
        action="store_true",
        help="mark the named mods as server-only, even if Modrinth says "
        "they are fine on a client (dependencies are left alone)",
    )
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="show what is in the pack")
    p.add_argument(
        "side",
        nargs="?",
        default="all",
        choices=["all", "client", "server", "both"],
        help="which side to show (default: all)",
    )
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("remove", help="take a mod out of the pack")
    p.add_argument("slug", help="Modrinth project slug")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("install", help="download the server-side mods into a directory")
    p.add_argument("directory")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("verify", help="check files against the pack")
    p.add_argument("directory")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("build", help="build a .mrpack for players")
    p.add_argument("output")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("export", help="dump the pack as JSON")
    p.add_argument("output")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("bump", help="bump the pack version")
    p.add_argument("--major", action="store_true", help="bump the major version")
    p.add_argument("--minor", action="store_true", help="bump the minor version")
    p.set_defaults(func=cmd_bump)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
