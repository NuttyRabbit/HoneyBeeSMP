# HoneyBeeSMP

A Minecraft community server built around **Create**, automation and factory
building. Everyone plays with the same modpack, so a contraption you build
works for everyone else too.

| | |
|---|---|
| **Play on** | `play.honeybeesmp.co.uk` (port 25566) |
| **On Modrinth** | [modrinth.com/server/honeybeesmp](https://modrinth.com/server/honeybeesmp) |
| **Website** | https://honeybeesmp.co.uk |
| **Server panel** | https://panel.honeybeesmp.co.uk |
| **Source** | https://github.com/NuttyRabbit/HoneyBeeSMP |

---

## Contents

**Playing**

- [Join the server](#join-the-server)
- [Install the modpack](#install-the-modpack)
- [Staying up to date](#staying-up-to-date)
- [What is in the pack](#what-is-in-the-pack)

**Working on it**

- [This repository](#this-repository)
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
- [How a deploy works](#how-a-deploy-works)

**Housekeeping**

- [Keeping credentials out of git](#keeping-credentials-out-of-git)
- [Reporting problems](#reporting-problems)

---

# Playing

## Join the server

### Requirements

| | |
|---|---|
| Minecraft | 1.21.1 |
| Mod loader | NeoForge 21.1.264 |
| Server address | `play.honeybeesmp.co.uk` |
| Server port | 25566 |

### Install the modpack

The server is listed on [Modrinth](https://modrinth.com/server/honeybeesmp),
so Modrinth knows exactly which mods you need.

1. Open **Modrinth App** or **Prism Launcher**.
2. Find **HoneyBeeSMP** on Modrinth and click **play**.
3. Modrinth App installs the mods and puts you straight into the server.

If you would rather install it yourself, the pack is published as a
version of the project. It is a Modrinth pack, so Modrinth App and Prism
Launcher both handle it, and both will offer you the update when we
publish a new version.

## Staying up to date

This is a **shared pack**. The server and your client run the same mods from
the same list, so when we change something you get the same change.

- When we publish a new version of the pack, Modrinth tells every instance
  linked to the server, and the launcher prompts you to accept the update
  before you launch.
- If a mod changes so much that the old version is no longer compatible, the
  pack is republished with the new one and your launcher picks it up.

If you ever see a "mismatched mod list" error when connecting, you are
running a different version of the pack to the server. Update the instance
and try again.

## What is in the pack

27 mods, chosen to work well together rather than to be the biggest set
possible.

### Create and factory building

- **Create** - belts, shafts, cogs, trains and contraptions
- **Create: Crafts & Additions** - extra Create machines and fluids
- **Create: Big Cannons** - cannons and projectiles
- **Create: Compression** - compressors and the machines around them
- **Sophisticated Storage** - storage blocks, and the drawers Create fills
- **Productive Bees** - bees, and the automation built around them
- **FastSuite** and **FastWorkbench** - crafting speed, so a large factory is
  not painful to run

### Quality of life

- **EMI** - recipe viewer
- **Jade** - block information in the world
- **AppleSkin** - shows real food values
- **Waystones** - teleport stones for getting around
- **Shulker Box Tooltip** - see what is in a shulker without opening it
- **Mouse Tweaks** - inventory right-click behaviour
- **BetterF3** - the F3 debug screen
- **No Chat Reports** - chat without the reporting system

### Performance

- **FerriteCore** - a large chunk of the frame-time saving
- **Spark** - the profiler, so you can see where the time goes
- **AntiXray** - stops ore and cave reveals through the server

### Exploration and world generation

- **Terralith** - better terrain, caves and biomes
- **Xaero's Minimap** - minimap and waypoints

A few mods in this pack are server-only. You do not need to install anything
extra - the launcher works out which files belong on your machine from the
pack itself.

The pack carries our server configs, so everyone plays with the same
settings. `config/` and `defaultconfigs/` are marked as editable, so you can
change your own copy without it affecting anyone else.

---

# Working on it

## This repository

Everything that makes up the server is here: the website, the Discord bot,
the Minecraft server configuration, and the tooling that deploys them.

```
website/      the public website
bot/          the Discord bot
minecraft/    the Minecraft server's configuration and modpack
scripts/      deployment, modpack and maintenance tooling
```

The repo is the **single source of truth**. The server's live directories are
populated from here, so there is never a question of which copy is
authoritative.

Things deliberately **not** in git:

| Excluded | Why |
|---|---|
| Minecraft worlds and jars | large; backed up separately, not version controlled |
| Panel configuration and databases | holds admin credentials and TLS keys |
| Secrets (`.env`) | never commit credentials |
| Logs and caches | no value in version control |

## The one rule

**Work on `develop`. Merge to `main` when it works.**

| | branch | website | Minecraft | world |
|---|---|---|---|---|
| **dev** | `develop` | dev.honeybeesmp.co.uk | port 25565 | superflat |
| **live** | `main` | honeybeesmp.co.uk | port 25566 | normal |

A push to `develop` deploys to dev. A push to `main` deploys to live.
Nothing reaches players until it is on `main`.

## Make a change

1. **Get the code.**

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

## Add a mod

Mods are listed in `minecraft/modpack/modrinth.index.json`. The jar files are
not in git - the server downloads and verifies them.

1. **Add it to the pack.**

   ```sh
   python3 scripts/modpack.py add create --env dev
   ```

   Use the Modrinth project slug (`create`, `journeymap`, `jei`, ...).

   This picks the right build for Minecraft 1.21.1 / NeoForge, and **pulls in
   required dependencies automatically**, so you will not hit "requires X or
   above" on the server.

   It also moves the pack's version on, because the pack's contents have
   changed. Modrinth will not accept a version number it has already seen,
   so the version has to move for there to be anything new to publish.

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

4. **Confirm it actually loaded**, rather than assuming - check the server
   log for the mod list.

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

`modpack.py add` should have pulled that in automatically. If it did not, add
the dependency by hand the same way.

## Remove a mod

1. Delete its entry from `minecraft/modpack/modrinth.index.json`.
2. Push. The deploy deletes the jar from the server.
3. **Restart the server** - the jar is gone from disk, but a running server
   keeps the mod loaded until it restarts.

## Change the Minecraft config

The server's settings are in the repo, so changes are reviewed and promoted
like any other code.

```
minecraft/
├── server.properties       the template (one file for both environments)
├── config/                NeoForge settings        -> server's config/
├── defaultconfigs/        server-only defaults     -> server's defaultconfigs/
├── modpack/               the modpack definition and overrides
└── env/
    ├── dev/env.conf       DEV server port, address, world settings, MC version
    ├── dev/jvm_args.txt   DEV heap size
    ├── dev/whitelist.txt  who may join the dev server
    ├── live/env.conf      LIVE server port, address, world settings, MC version
    └── live/jvm_args.txt  LIVE heap size
```

Edit the file, push to `develop`, test, then merge to `main`.

Two things to know:

- **Config changes need a restart.** Minecraft only reads its config at
  startup. See [Restart a Minecraft server](#restart-a-minecraft-server).
- **Never edit the config on the server directly.** The next deploy
  overwrites it. If you must, change it in the repo instead.

### The whitelist

Who may join is set per environment, in `minecraft/env/<env>/env.conf`:

```
WHITELIST=true     # only the listed names can join
WHITELIST=false    # anyone can join
```

The names themselves are in `minecraft/env/<env>/whitelist.txt`, one per
line. The deploy resolves them to UUIDs through Mojang's API and writes
the server's `whitelist.json`, so a typo fails the deploy rather than
silently locking someone out.

```sh
make whitelist              # who may join the dev server
make whitelist ENV=live     # the live server
```

Minecraft reads its whitelist at startup, so a change only takes effect
after a restart.

### Memory

Heap size per environment, in `minecraft/env/<env>/jvm_args.txt`:

| | min | max |
|---|---|---|
| dev | 2G | 4G |
| live | 4G | 8G |

If you raise the live heap, keep the two in step - a spike on live must not
be able to OOM-kill dev.

## Change the world type

World settings are per-environment in `minecraft/env/<env>/env.conf`:

| | level-type | structures |
|---|---|---|
| dev | `minecraft:flat` (superflat) | no |
| live | `minecraft:normal` | yes |

**Changing this does nothing to a world that already exists.**
`level-type` and `generator-settings` are read once, when the world is first
created - the generator settings live inside the world save itself. To apply
a change you have to delete the world so the server makes a new one.

The old world is not deleted by the deploy, so back it up first if you care
about it. **Never do this to the live world.**

## Restart a Minecraft server

Minecraft reads its config at startup, so a config change needs a restart.
Restarting kicks players, so it is opt-in.

```sh
make mc-restart-dev    # dev server
make mc-restart        # live server
make mc-status-dev     # is it running?
make mc-status         # is it running?
```

You can also restart as part of a deploy:

```sh
./scripts/deploy.sh live minecraft --restart
```

## Publish the modpack

The server is listed on
[Modrinth](https://modrinth.com/server/honeybeesmp). Players click play, and
Modrinth hands their launcher the pack this server is running - so the
launcher keeps them up to date, and nobody has to re-download anything by
hand.

The live deploy publishes automatically. It only publishes when the pack
in the repo is a version Modrinth has not seen, so a deploy that does not
touch the pack leaves the published one alone.

To publish by hand:

```sh
make modpack-publish    # bumps the version, then publishes
make modpack-status     # what is published right now
make modpack            # what is in the pack
```

Modrinth rejects a version number it has seen before, so the version is
bumped first. `modpack.py add` bumps it too, whenever it changes what is
in the pack - so the version in the repo always describes the pack that is
actually there.

**The project is still a draft.** Until a moderator approves it, nobody can
see the server listing and the pack cannot be downloaded. Publishing skips
cleanly while that is the case, and the pack goes out on the first live
deploy after approval.

## Backups

The live world is backed up to Google Drive twice a day, as a single zip per
run.

```sh
make backup        # run one now
make backup-log    # show the log
```

To restore, download `latest.zip` from the `HoneyBeeSMP` folder in Drive,
unzip it, and copy the parts you need back with the server stopped.

The backup covers the **live** world only. The dev world is disposable by
design.

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
make whitelist         # who may join the dev server

# housekeeping
make status            # git, services, and repo-vs-live drift
make check             # the same checks CI runs
make backup            # back up to Drive
make backup-log        # backup log
make crafty-logs       # tail the panel logs
```

## How a deploy works

Two paths do the same job, so the servers stay in step with the repo even if
one is unavailable.

**GitHub Actions** (`.github/workflows/deploy.yml`) runs on every push. It
connects to the server and runs `scripts/update.sh`. This is the fast path -
it deploys within seconds and shows a green check on the commit.

**A server-side timer** runs `scripts/autodeploy.sh` every minute, polls
GitHub, and deploys anything it finds. This is the backstop: it keeps working
if Actions is disabled, misconfigured, or out of minutes.

Both take the same lock, so whichever gets there first does the work and the
other finds nothing to do. They cannot race over the working copy.

A deploy is: fetch the branch, reset the working copy to it, run the sanity
checks, publish the website, bot and Minecraft config, then reload the web
server.

---

# Housekeeping

## Keeping credentials out of git

This repository is public. The credentials it needs to run are **not** in it,
and they must stay that way. Never commit:

- the server panel's admin password
- API tokens for Modrinth, Google Drive or Discord
- the bot's `.env` file
- any private key

`scripts/check.sh` runs on every push and fails if anything that looks like a
credential gets tracked - either by filename or by content.

## Reporting problems

If something is broken, or you cannot connect, let us know and include your
game log (`/logs/latest.log` in your instance) and any error from your
launcher.
