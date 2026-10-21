# HoneyBeeSMP

Everything for the HoneyBeeSMP Minecraft server lives in this repo: the
website, the Discord bot, the Minecraft server configuration, and the
tooling that deploys them.

| | |
|---|---|
| **Live site** | https://honeybeesmp.co.uk |
| **Dev site** | https://dev.honeybeesmp.co.uk |
| **Server panel** | https://panel.honeybeesmp.co.uk |
| **Repo** | https://github.com/NuttyRabbit/HoneyBeeSMP (private) |
| **Server** | `ssh ubuntu@132.145.16.69` (repo at `~/honeybeesmp`) |

---

## Contents

- [The one rule](#the-one-rule)
- [Make a change](#make-a-change)
- [Add a mod](#add-a-mod)
- [Remove a mod](#remove-a-mod)
- [Change the Minecraft config](#change-the-minecraft-config)
- [Change the world type](#change-the-world-type)
- [Restart a Minecraft server](#restart-a-minecraft-server)
- [Publish the modpack](#publish-the-modpack)
- [Backups](#backups)
- [Commands reference](#commands-reference)
- [How it fits together](#how-it-fits-together)
- [Setting up a new machine](#setting-up-a-new-machine)

---

## The one rule

**Work on `develop`. Merge to `main` when it works.**

| | branch | website | Minecraft | world |
|---|---|---|---|---|
| **dev** | `develop` | dev.honeybeesmp.co.uk | port 25565 | superflat |
| **live** | `main` | honeybeesmp.co.uk | port 25566 | normal |

A push to `develop` deploys to dev. A push to `main` deploys to live.
Nothing reaches players until it is on `main`.

---

## Make a change

1. **Get the code.** On your laptop:

   ```sh
   git clone git@github.com:NuttyRabbit/HoneyBeeSMP.git ~/honeybeesmp
   cd ~/honeybeesmp
   git checkout develop
   ```

2. **Edit something.** The website is `website/index.html`. The bot is in
   `bot/`. The Minecraft config is in `minecraft/`.

3. **Commit and push.**

   ```sh
   git add -A
   git commit -m "describe the change"
   git push origin develop
   ```

4. **Test it.** The deploy runs on its own within a minute. Check
   https://dev.honeybeesmp.co.uk, or connect to the dev Minecraft server on
   port 25565.

5. **Promote it to live** once you are happy:

   ```sh
   git checkout main
   git merge develop
   git push origin main
   ```

   The live site updates within a minute, and the live Minecraft server
   picks up any config change (see
   [Restart a Minecraft server](#restart-a-minecraft-server)).

### Deploying by hand

If you need to deploy without pushing:

```sh
./scripts/deploy.sh live              # website, bot and Minecraft config
./scripts/deploy.sh live web          # website only
./scripts/deploy.sh live bot          # bot only
./scripts/deploy.sh live minecraft    # Minecraft config only
```

The same thing on the server pulls first:

```sh
./scripts/update.sh live   # pull main, check, deploy, reload nginx
./scripts/update.sh dev    # same, from the develop branch
```

---

## Add a mod

Mods are listed in `minecraft/modpack/modrinth.index.json`. The jar files
are not in git - the server downloads and verifies them.

1. **Add it to the pack.** From your laptop:

   ```sh
   python3 scripts/modpack.py add create --env dev
   ```

   Use the Modrinth project slug (`create`, `journeymap`, `jei`, ...).

   This picks the right build for Minecraft 1.21.1 / NeoForge, and **pulls in
   required dependencies automatically**, so you will not hit "requires X or
   above" on the server.

2. **Push it.** The deploy installs it on the dev server.

   ```sh
   git add -A
   git commit -m "Add Create"
   git push origin develop
   ```

3. **Restart the dev server** so it loads the mod:

   ```sh
   make mc-restart-dev
   ```

4. **Confirm it actually loaded**, rather than assuming:

   ```sh
   sudo grep -A8 "Mod List" /opt/crafty/servers/d48afa12-59a5-496e-829a-1ced86d108b5/logs/latest.log
   ```

5. **Promote to live** when it works, then restart the live server too
   (`make mc-restart`).

### Which mods can go on the server

A dedicated server can only run **server-side** mods. A client-only mod
(Sodium, Xaero's, JourneyMap) will crash the server on startup with a
confusing error:

```
Exception in thread "main" java.lang.NoClassDefFoundError: org/lwjgl/Version
```

Check the mod's page on Modrinth: if it says "Client: Required", it is a
client mod and does not belong on the server. `modpack.py add` records the
client/server split for you, and the deploy only installs the server-side
ones.

### If the server will not start

A missing dependency is the usual cause, and the error names it:

```
[FATAL] Error during pre-loading phase: Mod terralith requires lithostitched 1.7.7 or above
```

`modpack.py add` should have pulled that in automatically. If it did not,
add the dependency by hand the same way.

---

## Remove a mod

1. Delete its entry from `minecraft/modpack/modrinth.index.json`.
2. Push. The deploy deletes the jar from the server.
3. **Restart the server** - the jar is gone from disk, but a running server
   keeps the mod loaded until it restarts.

---

## Change the Minecraft config

The server's settings are in the repo, so changes are reviewed and
promoted like any other code.

```
minecraft/
├── server.properties       the template (one file for both environments)
├── config/                NeoForge settings        -> server's config/
├── defaultconfigs/        server-only defaults     -> server's defaultconfigs/
└── env/
    ├── dev/env.conf       DEV server id, port, world settings, MC version
    ├── dev/jvm_args.txt   DEV heap size
    ├── live/env.conf      LIVE server id, port, world settings, MC version
    └── live/jvm_args.txt  LIVE heap size
```

Edit the file, push to `develop`, test, then merge to `main`.

Two things to know:

- **Config changes need a restart.** Minecraft only reads its config at
  startup. See [Restart a Minecraft server](#restart-a-minecraft-server).
- **Never edit the config on the server directly.** The next deploy
  overwrites it. If you must, change it in the repo instead.

### Memory

Heap size per environment, in `minecraft/env/<env>/jvm_args.txt`:

| | min | max |
|---|---|---|
| dev | 2G | 4G |
| live | 4G | 8G |

The host has 24 GB and 8 GB of swap. If you raise the live heap, keep the
two in step - a spike on live must not be able to OOM-kill dev.

---

## Change the world type

World settings are per-environment in `minecraft/env/<env>/env.conf`:

| | level-type | structures |
|---|---|---|
| dev | `minecraft:flat` (superflat) | no |
| live | `minecraft:normal` | yes |

**Changing this does nothing to a world that already exists.**
`level-type` and `generator-settings` are read once, when the world is first
created - the generator settings live inside the world save itself. To apply
a change you have to delete the world so the server makes a new one:

```sh
# on the server, with the server stopped
sudo rm -rf /opt/crafty/servers/d48afa12-59a5-496e-829a-1ced86d108b5/world
make mc-restart-dev
```

The old world is not deleted by the deploy, so back it up first if you care
about it. **Never do this to the live world.**

---

## Restart a Minecraft server

Minecraft reads its config at startup, so a config change needs a restart.
Restarting kicks players, so it is opt-in.

```sh
make mc-restart-dev    # dev server
make mc-restart        # live server
make mc-status-dev     # is it running?
make mc-status         # is it running?
```

Or, with the panel API directly:

```sh
./scripts/crafty.sh status  119045e1-1fac-41a0-83c0-5e2d85ce4c78
./scripts/crafty.sh restart 119045e1-1fac-41a0-83c0-5e2d85ce4c78
```

You can also restart as part of a deploy:

```sh
./scripts/deploy.sh live minecraft --restart
```

---

## Publish the modpack

Players install the pack from
[Modrinth](https://modrinth.com/modpack/honeybeesmp), and their launcher
offers them updates when you publish a new version. Nobody has to
re-download anything by hand.

The live deploy publishes automatically. To publish by hand:

```sh
make modpack-publish    # bumps the version, then publishes
make modpack-status     # what is published right now
make modpack            # what is in the pack
```

Modrinth rejects a version number it has seen before, so the version is
bumped first.

**The project is a draft.** Until it is approved for review it is not
visible to players:

```
https://modrinth.com/project/EAHVT4s6/settings
```

The API token lives on the server at `~/.config/modrinth/token` and needs
the **Create projects**, **Create versions** and **Modify projects**
scopes. `python3 scripts/publish-modpack.py check` reports what the token
actually has.

---

## Backups

The live world is backed up to Google Drive twice a day, as a single zip
per run.

```sh
make backup        # run one now
make backup-log    # show the log
```

To restore, download `latest.zip` from the `HoneyBeeSMP` folder in Drive,
unzip it, and copy the parts you need back with the server stopped.

The backup covers the **live** world only. The dev world is disposable by
design.

---

## Commands reference

Run these on the server unless it says otherwise.

```sh
make help              # list every target

# deploy
make deploy            # website to live
make deploy-dev        # website to dev
make deploy-mc         # Minecraft config to live
make deploy-mc-dev     # Minecraft config to dev
make update            # pull main, check, deploy
make update-dev        # pull develop, check, deploy

# Minecraft servers
make mc-status         # is live running?
make mc-status-dev     # is dev running?
make mc-restart        # restart live (kicks players)
make mc-restart-dev    # restart dev

# modpack
make modpack           # what is in the pack
make modpack-add SLUG=create
make modpack-publish   # bump and publish to Modrinth
make modpack-status    # what is published
make modpack-verify    # do the server's mods match the pack?

# housekeeping
make status            # git, services, and repo-vs-live drift
make check             # the same checks CI runs
make backup            # back up to Drive
make backup-log        # backup log
make crafty-logs       # tail the panel logs
```

The Crafty panel database holds the panel admin password, so treat the
server as sensitive.

---

## How it fits together

The repo is the **single source of truth**. The server's live directories are
populated from here, so there is never a question of which copy is
authoritative.

```
website/     ->  /var/www/honeybeesmp.co.uk     (nginx)
bot/         ->  /opt/honeybee-discord-bot      (runtime dir)
minecraft/   ->  the server's configuration
```

Things deliberately **not** in git:

| Excluded | Where it lives | Why |
|---|---|---|
| Minecraft worlds and jars | `/opt/crafty/servers` | ~190 MB; backed up to Drive, not git |
| Crafty config and databases | `/opt/crafty/config` | panel admin password and TLS keys |
| Secrets (`.env`) | server only | never commit credentials |
| Logs and caches | various | no value in version control |

### Who deploys

Two paths do the same job, so the servers stay in step with the repo even
if one is unavailable.

**GitHub Actions** (`.github/workflows/deploy.yml`) runs on every push. It
SSHes into the server and runs `scripts/update.sh`. This is the fast path -
it deploys within seconds and shows a green check on the commit.

**A server-side timer** runs `scripts/autodeploy.sh` every minute, polls
GitHub, and deploys anything it finds. This is the backstop: it keeps
working if Actions is disabled, misconfigured, or out of minutes.

Both take the same lock, so whichever gets there first does the work and
the other finds nothing to do. They cannot race over the working copy.

The workflow needs two repository secrets (Settings -> Secrets and
variables -> Actions):

| Secret | Value |
|---|---|
| `DEPLOY_SSH_KEY` | the private key (see below) |
| `DEPLOY_SSH_KNOWN_HOSTS` | the server's host key (optional but recommended) |

To create the key and authorise it on the server:

```sh
sudo ./scripts/install-ci-key.sh --show-private
```

### On the server

| Service | How it runs |
|---|---|
| Website and panel | nginx, TLS from Let's Encrypt, auto-renews |
| Crafty Controller | Docker, panel on 127.0.0.1:8443 behind nginx |
| Backups | systemd timer, twice a day |
| Auto-deploy | systemd timer, every minute |
| Discord bot | not deployed yet |

---

## Setting up a new machine

1. Get an SSH key for the server, then:

   ```sh
   ssh -i ~/path/to/key ubuntu@132.145.16.69
   ```

2. Clone the repo:

   ```sh
   git clone git@github.com:NuttyRabbit/HoneyBeeSMP.git ~/honeybeesmp
   cd ~/honeybeesmp
   ```

3. Deploy:

   ```sh
   ./scripts/deploy.sh live
   ```

The server already has a write-enabled deploy key at
`~/.ssh/honeybeesmp_deploy`, wired up through `~/.ssh/config`, so pushes
and pulls work without a token.
