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
├── modpack/               the modpack (see minecraft/modpack/README.md)
│   ├── modrinth.index.json  the mods, hashes and client/server split
│   ├── overrides/           config for both client and server
│   ├── client-overrides/    config for players only
│   └── server-overrides/    config for the server only
└── env/
    ├── dev/env.conf       DEV server id, port, MC and loader version
    ├── dev/jvm_args.txt   DEV heap size
    ├── live/env.conf      LIVE server id, port, MC and loader version
    └── live/jvm_args.txt  LIVE heap size
```

So changing a setting is an ordinary edit, commit and push. The deploy
applies it to the target server. It never touches the world, player data or
the server jars.

### Adding a mod

Mods live in a [Modrinth pack](minecraft/modpack/) at
`minecraft/modpack/modrinth.index.json`. That format records, for every
mod, which side it belongs to and a hash to verify the download. It is also
the format players import, so the server and the client can never drift
apart.

Everything is done through one tool, `scripts/modpack.py`, which is the
same code the deploy uses.

**1. Add the mod.** Use its Modrinth project slug:

```sh
python3 scripts/modpack.py add create --env dev
```

This resolves the correct build for our Minecraft version and loader, and
**pulls in required dependencies automatically** - so you will not hit
"Mod X requires Y or above" on the server.

It also records the client/server split, so a client-only mod like Sodium
is never installed on the server, and a server-only mod is never asked of
players.

**2. Push to `develop` and let it install on the dev server.**

```sh
git add minecraft/modpack
git commit -m "Add Create"
git push origin develop
```

The deploy downloads each mod, verifies its SHA-512 against the pack, and
installs it. You will see:

```
    installing mods from the pack
    downloading Terralith_1.21.1_v2.6.2_Neoforge.jar
    2 server-side mod(s) in place
```

**3. Restart the dev server so it loads the mod.**

Mods are read at startup, so the server must be restarted:

```sh
make mc-restart-dev          # on the server
```

Then confirm it actually loaded, rather than assuming:

```sh
sudo grep -A8 "Mod List" /opt/crafty/servers/d48afa12-59a5-496e-829a-1ced86d108b5/logs/latest.log
```

**4. Test it, then promote to live.**

Once it works on dev, merge to `main` and push. The live server gets the
same pack, and the deploy publishes it to Modrinth so players are offered
the update. **Restart the live server too** - it is a separate machine state:

```sh
make mc-restart              # on the server
```

If the deploy does not publish for you, do it by hand - see
[Giving the pack to players](#giving-the-pack-to-players) below.

### Removing a mod

Remove its entry from `minecraft/modpack/modrinth.index.json` and push.
The next deploy deletes the jar.

**Restart the server afterwards** so it stops loading the mod. The jar is
gone from disk, but a running server keeps the mod loaded until it restarts.

### Giving the pack to players

The pack is published to **Modrinth**, where players install it from.
Modrinth App and Prism Launcher both watch the project for new versions,
so when we publish, players are offered the update - nobody has to
re-download a file by hand.

**One-time setup:**

1. Create a Modrinth account, then a personal access token at
   <https://modrinth.com/settings/account> with the **Create projects**
   and **Create versions** scopes.
2. On the server, save the token:

   ```sh
   mkdir -p ~/.config/modrinth
   nano ~/.config/modrinth/token     # paste the token, one line
   chmod 600 ~/.config/modrinth/token
   ```

3. Create the project and publish the first version:

   ```sh
   cd ~/honeybeesmp
   python3 scripts/publish-modpack.py create
   python3 scripts/publish-modpack.py publish
   ```

   `create` saves the project id to `~/.config/modrinth/project-id`.

**Publishing a change:** the pack version has to move forward first,
because Modrinth refuses a duplicate version number.

```sh
python3 scripts/modpack.py bump            # 1.0.0 -> 1.0.1
python3 scripts/publish-modpack.py publish
```

Or, more usually, the live deploy does it for you - it publishes the pack
after deploying, and skips the step with a clear message if Modrinth is
not set up yet.

Check the state any time with:

```sh
python3 scripts/publish-modpack.py status
```

**For players:** they install the pack from
<https://modrinth.com/modpack/honeybeesmp> in Modrinth App, Prism
Launcher or CurseForge. It carries every mod and config we run, and
because it is generated from the same index the server deploys from, they
are always on the same version as the server.

### Checking the server against the pack

```sh
python3 scripts/modpack.py verify /opt/crafty/servers/<id>/mods
```

See `minecraft/modpack/README.md` for the full details of the pack format
and the config directories (`overrides/`, `client-overrides/`,
`server-overrides/`).

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
│   ├── modpack/                   the modpack: mods, hashes, config
│   ├── env/dev/env.conf           DEV server id, port, MC and loader
│   ├── env/live/env.conf          LIVE server id, port, MC and loader
│   └── env/*/jvm_args.txt         per-env heap size
├── scripts/
│   ├── backup.sh                  rclone snapshot of the live world -> Drive
│   ├── check.sh                   no secrets / no huge files / ignore rules
│   ├── crafty.sh                  Crafty panel API: start/stop/restart
│   ├── modpack.py                 add/list/install/build/bump the modpack
│   ├── publish-modpack.py         publish the modpack to Modrinth
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
