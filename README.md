# HoneyBeeSMP

Monorepo for the HoneyBeeSMP Minecraft community: website, Discord bot, and
deployment tooling.

**Repo:** https://github.com/NuttyRabbit/HoneyBeeSMP (private)
**Live site:** https://honeybeesmp.co.uk
**Dev site:** https://dev.honeybeesmp.co.uk
**Server panel:** https://panel.honeybeesmp.co.uk

---

## Quick start

The repo is cloned at `~/honeybeesmp` on both your laptop and the server.

```sh
cd ~/honeybeesmp
git checkout develop     # work on develop, not main
```

Make a change, then:

```sh
git add -A
git commit -m "describe the change"
git push origin develop
```

**That is the whole loop.** Pushing to `develop` automatically deploys to the
dev environment. You can then look at https://dev.honeybeesmp.co.uk and the
DEV Minecraft server to test it. When it works, merge to `main`:

```sh
git checkout main
git merge develop
git push origin main      # deploys to live
```

You can also work directly on the server over SSH (`ssh ubuntu@132.145.16.69`,
repo at `~/honeybeesmp`) — but committing and pushing from your laptop is
usually easier, and the CI deploy works the same either way.

### What runs where

| | branch | website | Minecraft server |
|---|---|---|---|
| dev | `develop` | dev.honeybeesmp.co.uk | DEV, port 25565 |
| live | `main` | honeybeesmp.co.uk | LIVE, port 25566 |

---

## The idea

This repo is the **single source of truth** for everything we author. The
server's live directories are populated from here by a deploy script, so there
is never a question of which copy is authoritative.

```
website/      -> deployed to /var/www/honeybeesmp.co.uk   (nginx)
bot/          -> deployed to /opt/honeybee-discord-bot    (runtime dir)
minecraft/    -> the server's configuration (not the world data)
scripts/      -> check / deploy / update helpers
```

Things that are **not** in the repo, on purpose:

| Excluded | Where it lives | Why |
|---|---|---|
| Minecraft worlds, jars, mods | `/opt/crafty/servers` | ~189 MB each; backed up to Google Drive, not git |
| Crafty config + databases | `/opt/crafty/config` | contains the panel admin password & TLS key |
| Secrets (`.env`) | server only | never commit credentials |
| Logs, backups, caches | various | no value in version control |

---

## Everyday workflow

Edit files in this repo, then:

```sh
git add -A
git commit -m "describe the change"
git push
```

The CI workflow runs `scripts/check.sh` on every push to confirm no secrets or
oversized files slipped in, and then deploys.

### Publishing a change to the live site

```sh
./scripts/deploy.sh live              # website, bot and Minecraft config
./scripts/deploy.sh live web          # website only
./scripts/deploy.sh live bot          # bot only
./scripts/deploy.sh live minecraft    # Minecraft config only
```

`deploy.sh` uses `rsync --delete`, so the live directories end up **exactly**
matching the repo (minus runtime files like `.env` and `bot/data`).

### Applying an update from GitHub to the server

```sh
./scripts/update.sh live   # pull main, check, deploy, reload nginx
./scripts/update.sh dev    # same, but from the develop branch
```

This pulls, runs the checks, deploys, and reloads nginx. Safe to automate —
this is exactly what CI runs.

### Handy shortcuts

```sh
make help        # list all targets
make status      # git state, service state, and repo-vs-live drift
make check       # same checks CI runs
make deploy      # publish the website to live
make deploy-dev  # publish the website to dev
make crafty-logs # tail the Minecraft panel logs
make backup      # run a backup now
make backup-log  # show the backup log
```

---

## Environments and the dev -> live workflow

There are two environments, each with its own branch, website and Minecraft
server:

| | dev | live |
|---|---|---|
| branch | `develop` | `main` |
| website | https://dev.honeybeesmp.co.uk | https://honeybeesmp.co.uk |
| Minecraft server | DEV (`d48afa12-...`), port 25565 | LIVE (`119045e1-...`), port 25566 |
| bot directory | `/opt/honeybee-discord-bot-dev` | `/opt/honeybee-discord-bot` |

The normal flow:

1. Make a change, push it to `develop`.
2. CI deploys `develop` to the dev environment.
3. Test it on `dev.honeybeesmp.co.uk` and the DEV Minecraft server.
4. When you are happy, merge `develop` into `main` and push.
5. CI deploys `main` to the live environment.

Nothing reaches players until step 4.

### Minecraft configuration lives in the repo

The *world data* is too big for git and is backed up separately, but the
*configuration* is version-controlled in `minecraft/`:

```
minecraft/
├── server.properties      template; @SERVER_PORT@ is filled in per env
├── config/                NeoForge server settings
├── defaultconfigs/
├── mods/mods.manifest     the mod list (jars are not in git)
└── env/
    ├── dev/env.conf       DEV server id and port
    ├── dev/jvm_args.txt   DEV heap size
    ├── live/env.conf      LIVE server id and port
    └── live/jvm_args.txt  LIVE heap size
```

So changing a setting is an ordinary edit, commit and push. The deploy
applies it to the target server. It never touches the world, player data or
the server jars.

### Adding a mod

Mods are listed in `minecraft/mods/mods.manifest`, one per line:

```
<the-exact-jar-filename>.jar  <direct-download-url>
```

The jar files themselves are not in git - they are downloaded on the server
by the deploy.

**1. Find a server-side build.**

This is the step people get wrong. A dedicated server must only run mods
marked **"Server"** on Modrinth. A client-only mod will crash the server on
startup, and the failure is cryptic:

```
Exception in thread "main" java.lang.NoClassDefFoundError: org/lwjgl/Version
```

That is what happens if you install a client-only mod such as Sodium, Xaero's
or JourneyMap. Check the mod's page - if it says "Client: Required" and
"Server: Not required", it is a client mod and does not belong here.

You also need the build that matches:

| | |
|---|---|
| Minecraft | 1.21.1 |
| Mod loader | NeoForge |
| Loader version | 21.1.264 |

**2. Get the direct download URL and the exact filename.**

Modrinth's API gives both, and avoids the "which of the seven files do I
want" problem:

```sh
# list the versions available for our loader and game version
curl -s "https://api.modrinth.com/v2/project/terralith/version?game_versions=%5B%221.21.1%22%5D&loaders=%5B%22neoforge%22%5D"
```

Each version has a `files` array; the entry with `"primary": true` is the
one you want. Note its `filename` - the manifest must match it exactly.

**3. Add the line to the manifest.**

```
# minecraft/mods/mods.manifest
Terralith_1.21.1_v2.6.2_Neoforge.jar  https://cdn.modrinth.com/data/8oi3bsk5/versions/IY93YaEe/Terralith_1.21.1_v2.6.2_Neoforge.jar
```

The two columns are separated by whitespace. A `#` starts a comment.

**4. Push to `develop` and let it install on the dev server.**

```sh
git add minecraft/mods/mods.manifest
git commit -m "Add Terralith"
git push origin develop
```

The deploy downloads the jar, checks it really is a jar (and not an HTML
error page), and installs it. You will see it in the log:

```
==> reconciling mods
    downloading Terralith_1.21.1_v2.6.2_Neoforge.jar
```

**5. Restart the dev server so it loads the mod.**

Mods are read at startup, so the server must be restarted:

```sh
make mc-restart-dev          # on the server
```

Then confirm it actually loaded, rather than assuming:

```sh
sudo grep -A8 "Mod List" /opt/crafty/servers/d48afa12-59a5-496e-829a-1ced86d108b5/logs/latest.log
```

**6. Test it, then promote to live.**

Once it works on dev, merge to `main` and push. The live server gets the
same jar. **Restart the live server too** - it is a separate machine state:

```sh
make mc-restart              # on the server
```

### Removing a mod

Delete its line from the manifest and push. The next deploy removes the jar
from the server:

```
    removing unlisted mod sodium-neoforge-0.8.13+mc1.21.1.jar
```

**Restart the server afterwards** so it stops loading the mod. The jar is
gone from disk, but a running server keeps the mod loaded until it restarts.

### Mods and dependencies

If a mod needs another mod (a library, an API), **list both**. The manifest
has no notion of dependencies, so anything the mod needs must be on the
server too, or the server will not start. The error names what is missing:

```
[ERROR] Missing or unsupported mandatory dependencies:
  Mod ID: 'lithostitched', Requested by: 'terralith', Expected range: '[1.7.7,)', Actual version: '[MISSING]'
[FATAL] Error during pre-loading phase: Mod terralith requires lithostitched 1.7.7 or above
```

Add a line for each dependency, in the same way. Some mods have several.

### Mods are not backed up as source

The mod jars live on the server and are re-downloaded from the manifest on
every deploy, so they do not need to be in the backup. If a mod disappears
from Modrinth, the manifest entry stops working - keep the URL stable, or
vendor the jar somewhere permanent and point the manifest at that.

### Memory allocation

Each environment has its own JVM heap size, in
`minecraft/env/<env>/jvm_args.txt`:

| | min | max | G1 region |
|---|---|---|---|
| dev | 2G | 4G | 2M |
| live | 4G | 8G | 4M |

The deploy applies these, so the allocation is reviewable and reproducible
rather than being set once in the panel and forgotten. A change takes effect
on the next restart.

The host has 24 GB and 8 GB of swap (`/swapfile`, persistent via `fstab`,
`vm.swappiness=10`). Both servers running together use around 7 GB of heap
and leave plenty of headroom. If you raise the live heap, keep the two
allocations in step — a spike on the live server must not be able to
OOM-kill the dev one, or vice versa.

### Restarting a Minecraft server

Minecraft only reads its config at startup, so a config change needs a
restart to take effect. Restarting kicks players, so it is opt-in:

```sh
./scripts/deploy.sh live minecraft --restart
./scripts/crafty.sh status  119045e1-1fac-41a0-83c0-5e2d85ce4c78
./scripts/crafty.sh restart 119045e1-1fac-41a0-83c0-5e2d85ce4c78
```

`crafty.sh` wraps the Crafty Controller's API. It mints a short-lived token
using the panel's own signing secret, so no credential needs storing.

### CI

There are two paths that do the same thing, so the servers stay in step with
the repo even if one of them is unavailable.

**GitHub Actions** (`.github/workflows/deploy.yml`) runs on every push to
`main` or `develop`. It SSHes into the server and runs `scripts/update.sh`.
This is the fast path - it deploys within seconds and shows a green check on
the commit.

**A server-side timer** (`scripts/autodeploy.sh`, run every minute by
systemd) polls GitHub and deploys anything it finds. This is the backstop:
it keeps working if Actions is disabled, misconfigured, or out of minutes.

Both take the same lock, so whichever gets there first does the work and the
other finds nothing to do. They cannot race over the working copy's branch.

The workflow needs **two** repository secrets (Settings -> Secrets and
variables -> Actions):

| Secret | Value |
|---|---|
| `DEPLOY_SSH_KEY` | the private key (see below) |
| `DEPLOY_SSH_KNOWN_HOSTS` | the server's host key (optional but recommended) |

The server address, user and repo path are written into the workflow
itself. They are not secret - the address is in public DNS - and keeping
them out of the secret store means they cannot be pasted with a stray
character, and they appear in the log so any mistake is obvious.

To create the key pair and authorise it on the server:

```sh
sudo ./scripts/install-ci-key.sh --show-private
```

It prints the private key to paste into `DEPLOY_SSH_KEY`, and adds the
public key to the server's `authorized_keys`. It is safe to run more than
once.

Watching a deploy:

```sh
# on the server
sudo journalctl -u honeybeesmp-autodeploy-dev.service -f   # the backstop
sudo journalctl -u honeybeesmp-autodeploy-live.service -f
tail -f ~/honeybeesmp/logs/backup.log                     # backups
```

---

## Backups

The live world is backed up to **Google Drive** (2 TB) by `scripts/backup.sh`,
which runs twice daily via a systemd timer.

Each run packs everything into a **single zip** and uploads that. One zip is
one file on Drive, so an upload is one API call rather than hundreds, and a
restore is one download plus `unzip`.

```
Google Drive: HoneyBeeSMP/
  backup-2026-10-21_0005.zip   dated archives (7 most recent kept)
  latest.zip                   rolling copy of the newest archive
```

Each archive contains:

```
minecraft/<server-id>/   the world's files, config and mods
crafty/config/           panel config, users and schedules
content/                 website, bot and repo
```

Only the **live** server is backed up. Its Crafty ID is set at the top of
`backup.sh`:

```sh
MINECRAFT_SERVERS=${MINECRAFT_SERVERS:-119045e1-1fac-41a0-83c0-5e2d85ce4c78}
```

That is the live world. `d48afa12-...` is the development/testing server and is
deliberately **excluded**, so dev experiments can never overwrite a good live
snapshot. For more than one, list the IDs space-separated.

### Restoring

```sh
rclone copyto gdrive:HoneyBeeSMP/latest.zip /tmp/restore.zip
unzip -q /tmp/restore.zip -d /tmp/restore
# then copy the parts you need back, with the server stopped
```

### Things to know

- **Consistency.** A running server writes to its world while we copy it. The
  script detects a live Java process and logs a `WARNING` when this happens.
  For a guaranteed-consistent snapshot, stop the server first. The warning
  tells you which kind of copy you got.
- **Every run uploads a new archive.** A zip cannot be updated in place, so
  each run uploads the whole thing. At ~160 MB that is quick, and older
  archives are pruned to keep only the most recent few.

### Running it by hand

```sh
sudo systemctl start honeybeesmp-backup.service   # run now
journalctl -u honeybeesmp-backup.service -f       # watch it
systemctl list-timers honeybeesmp-backup.timer    # see the schedule

./scripts/backup.sh --dry-run                     # preview, changes nothing
BACKUP_KEEP=14 ./scripts/backup.sh                # keep 14 archives
MINECRAFT_SERVERS="id1 id2" ./scripts/backup.sh   # override which worlds
```

Logs are written to `logs/backup.log` (gitignored).

### Credentials

rclone authenticates with our **own OAuth client** — not rclone's shared ID,
which is throttled and being retired during 2026. The client ID and secret live
in `~/.config/rclone/rclone.conf` on the server and on the laptop. To
re-authenticate, run `rclone config reconnect gdrive:` somewhere with a
browser, then copy that file across.

---

## Layout

```
.
├── .github/workflows/
│   ├── checks.yml                 CI: sanity checks on push
│   └── deploy.yml                 CI: deploys dev or live over SSH
├── Makefile                       task shortcuts
├── README.md
├── bot/                           Discord bot
│   ├── .env.example               template (real .env stays on the server)
│   ├── .rsync-exclude
│   ├── data/                      runtime state (gitignored)
│   ├── logs/                      runtime logs (gitignored)
│   └── src/                       bot source
├── minecraft/                     version-controlled server config
│   ├── server.properties          template (@SERVER_PORT@ filled per env)
│   ├── config/                    NeoForge settings
│   ├── defaultconfigs/
│   ├── env/dev/env.conf           DEV server id and port
│   ├── env/live/env.conf          LIVE server id and port
│   └── mods/mods.manifest         the mod list
├── scripts/
│   ├── backup.sh                  rclone snapshot of the live world -> Drive
│   ├── check.sh                   no secrets / no huge files / ignore rules
│   ├── crafty.sh                  Crafty panel API: start/stop/restart
│   ├── deploy-minecraft.sh        apply minecraft/ config to a server
│   ├── deploy.sh                  repo -> a dev or live environment
│   ├── install-backup-timer.sh    schedule backup.sh via systemd
│   ├── install-ci-key.sh          create the key GitHub Actions deploys with
│   └── update.sh                  pull + check + deploy + reload nginx
└── website/
    └── index.html                 the public landing page
```

Navigation symlinks that live alongside the repo (not tracked):
`crafty-panel`, `minecraft-servers`, `discord-bot`.

---

## Services on the host

| Service | How it runs | Notes |
|---|---|---|
| Website + panel (TLS) | nginx | Let's Encrypt cert, auto-renew via certbot.timer |
| Crafty Controller | Docker (`crafty_container`) | panel on `127.0.0.1:8443`, proxied by nginx |
| Discord bot | not deployed yet | use `./scripts/deploy.sh bot` when ready |

Useful commands:

```sh
sudo docker ps
sudo docker logs crafty_container -f
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certificates
```

---

## First-time setup on a new machine

1. Install the deploy key (see below) or use your own credentials.
2. `git clone git@github.com:NuttyRabbit/HoneyBeeSMP.git ~/honeybeesmp`
3. `./scripts/deploy.sh`

The server already has a write-enabled **deploy key** at
`~/.ssh/honeybeesmp_deploy`, wired up through `~/.ssh/config`, so pushes and
pulls work without a token.
