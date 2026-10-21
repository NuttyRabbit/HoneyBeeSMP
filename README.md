# HoneyBeeSMP

Monorepo for the HoneyBeeSMP Minecraft community: website, Discord bot, and
deployment tooling.

**Repo:** https://github.com/NuttyRabbit/HoneyBeeSMP (private)
**Live site:** https://honeybeesmp.co.uk
**Server panel:** https://panel.honeybeesmp.co.uk

---

## The idea

This repo is the **single source of truth** for everything we author. The
server's live directories are populated from here by a deploy script, so there
is never a question of which copy is authoritative.

```
website/      -> deployed to /var/www/honeybeesmp.co.uk   (nginx)
bot/          -> deployed to /opt/honeybee-discord-bot    (runtime dir)
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

Edit files in this repo (e.g. from Zed over SSH), then:

```sh
git add -A
git commit -m "describe the change"
git push
```

The CI workflow runs `scripts/check.sh` on every push to confirm no secrets or
oversized files slipped in.

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

To add a mod, add its line to `minecraft/mods/mods.manifest`:

```
create-1.21.1-1.0.0.jar  https://example.com/create-1.21.1-1.0.0.jar
```

The deploy downloads any missing mod and removes any mod that is no longer
listed, so dev and live stay on the same mod set.

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

`.github/workflows/deploy.yml` runs on every push to `main` or `develop`. It
SSHes into the server and runs `scripts/update.sh`, which pulls, checks and
deploys.

The workflow needs these repository secrets (Settings -> Secrets and
variables -> Actions):

| Secret | Value |
|---|---|
| `DEPLOY_SSH_KEY` | the private key (see below) |
| `DEPLOY_HOST` | `132.145.16.69` |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_REPO_PATH` | `/home/ubuntu/honeybeesmp` |
| `DEPLOY_SSH_KNOWN_HOSTS` | the server's host key (optional but recommended) |

To create the key pair and authorise it on the server:

```sh
sudo ./scripts/install-ci-key.sh --show-private
```

It prints the private key to paste into `DEPLOY_SSH_KEY`, and adds the
public key to the server's `authorized_keys`. It is safe to run more than
once.

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
