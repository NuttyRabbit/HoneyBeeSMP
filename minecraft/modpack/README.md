# HoneyBeeSMP modpack

This directory is a [Modrinth pack](https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack).
It is the **single source of truth** for which mods we run, on both the
server and the players' clients.

It is published to Modrinth as the content of our
[server project](https://modrinth.com/server/honeybeesmp), so a player who
clicks play gets exactly this pack installed, and is told when it changes.

## What is in the pack

53 mods, chosen to be a coherent set rather than the biggest one possible.

### Create and factory building

| Mod | Why |
|---|---|
| Create | The centrepiece. Belts, shafts, cogs, trains, contraptions. |
| Create: Crafts & Additions | Extra Create machines and fluids. |
| Create: Big Cannons | Cannons and projectiles for Create. |
| Create: Compression | Compressors and the machines around them. |
| Create: Ore Excavation | The drill rebalance, which is what makes Create's mining loop worth playing. |
| Create: Numismatics | Currency, so the factory has something to be worth. |
| Sophisticated Storage | Storage blocks, and the drawers Create fills them with. |
| Productive Bees | Bees, and the automation built around them. |
| FastSuite / FastWorkbench | Crafting speed, so a big factory is not painful to use. |
| Ritchie's Projectile Library | Required by Big Cannons. |
| Sophisticated Core | Required by Sophisticated Storage. |

### Server side

These do not go on players' clients. The pack records that, so the launcher
skips them and the server still installs them.

| Mod | Why |
|---|---|
| LuckPerms | Permissions. |
| Open Parties and Claims | Claims, parties and grief protection. |
| Open Parties and Claims: PvP Support | Lets players fight inside their claims. |
| Open Parties and Claims: Essentials | Commands and conveniences for claims. |
| KubeJS | Server-side scripting. |
| Lithium | Tick performance. |
| ModernFix | Memory and startup performance. |
| Noisium | Fewer random ticks, which matters on a server full of machinery. |
| AntiXray | Stops ore and cave reveals through the server. |
| Spark | Profiler. Run `/spark` to see where the time goes. |
| Necronomicon API | Required by Open Parties and Claims. |

### Quality of life

| Mod | Why |
|---|---|
| EMI | Recipe viewer. |
| Jade | Block information in the world. |
| AppleSkin | Shows real food values. |
| Waystones | Teleport stones, for getting around. |
| WTHIT | Shows what a waystone links to. |
| Shulker Box Tooltip | See what is in a shulker without opening it. |
| Mouse Tweaks | Inventory right-click behaviour. |
| BetterF3 | F3 debug screen. |
| No Chat Reports | Chat without the reporting system. |
| Legendary Tooltips | Nicer tooltips. |
| Clumps | Merges XP orbs. |
| Balm | Required by Waystones. |
| Cloth Config | Required by several mods. |
| Placebo | Required by FastSuite. |

### Performance, client side

| Mod | Why |
|---|---|
| FerriteCore | A large chunk of the frame-time saving. |
| Sodium | Rendering performance. |
| More Culling | Culls entities you cannot see. |
| Continuity | Connected textures - Create looks far better with them. |

### Exploration and world generation

| Mod | Why |
|---|---|
| Terralith | Better terrain, caves and biomes. |
| Tectonic | Terrain shaping - mountains and landforms at a scale Terralith does not do. |
| Lithostitched | Required by Terralith and Tectonic. |
| Xaero's Minimap | Minimap and waypoints, for exploring. |
| Xaero's World Map | The world map, to go with it. |

## Why a pack and not a list of mods

Server mods and client mods are **different sets**, and that is the whole
reason for this format:

| Mod | Client | Server |
|---|---|---|
| Create | optional | required |
| AntiXray | unsupported | required |
| Mouse Tweaks | required | unsupported |

A plain list of "our mods" cannot express that. The pack format records
`env` per file, so the same file describes what the server installs and
what a player installs - and they can never drift apart.

The pack also records a SHA-512 hash for every file, so a download that is
corrupted or tampered with is caught rather than silently installed.

Of the 53 mods, 26 are installed on the server and 27 on players' clients.
Mods that are on neither, or on both, sit in between - the pack records
each file's split exactly.

## Layout

```
modpack/
├── modrinth.index.json    the pack itself: mods, hashes, client/server split
├── overrides/             config for BOTH the client and the server
│   ├── config/
│   └── defaultconfigs/
├── client-overrides/      config for the client only
└── server-overrides/      config for the server only
```

`overrides/` is what the server's `config/` and `defaultconfigs/` map onto.
Anything in `client-overrides/` is never sent to the server, and anything
in `server-overrides/` is never sent to players.

## Working with it

All of this is done through one tool, `scripts/modpack.py`, which is the
same code the deploy uses - so the pack and the running server cannot
disagree.

```sh
# Add a mod, and any dependencies it needs
python3 scripts/modpack.py add create --env dev

# See what is in the pack
python3 scripts/modpack.py list
python3 scripts/modpack.py list server

# Build the pack players download
python3 scripts/modpack.py build /tmp/HoneyBeeSMP.mrpack

# Check the mods on a server against the pack
python3 scripts/modpack.py verify /opt/crafty/servers/<id>/mods
```

### Adding a mod

1. `python3 scripts/modpack.py add <slug> --env dev`
   - Use the Modrinth project slug.
   - This pulls in required dependencies automatically, so you will not hit
     "Mod X requires Y or above" on the server.
   - It records the client/server split for you.
   - It moves the pack's version on, because the pack's contents have
     changed. Modrinth will not accept a version number it has already
     seen, so the version has to move for the pack to be publishable.

2. Commit `minecraft/modpack` and push to `develop`.

3. The deploy installs it on the dev server. Restart the server so it
   loads:

   ```sh
   make mc-restart-dev
   ```

4. Test it, then merge to `main` and push.

### Removing a mod

Remove its entry from `modrinth.index.json` and push. The deploy deletes
the jar. Restart the server afterwards so it stops loading the mod.

## Keeping it clean

The pack is deliberately curated rather than exhaustive. A few rules we
follow:

- **One mod per job.** Xaero's Minimap is in, JourneyMap is not. More
  Culling is in, Entity Culling is not - More Culling does the same job
  and keeps the other one out of the way.
- **One recipe viewer.** EMI is in, JEI is not - they clash.
- **Check for conflicts before adding.** A client-only mod on the server
  crashes it with `NoClassDefFoundError: org/lwjgl/Version`.
- **Prefer mods that serve both sides.** Mods that work on the client and
  the server mean one pack covers everyone.
- **Be careful with world generators.** Terralith and Tectonic are both in
  and they do work together - the Tectonic jar ships the Terratonic
  overlay, which is the Terralith-compatible variant of it. That is a
  deliberate pairing, not an accident: Tectonic on its own reshapes the
  terrain in a way that fights Terralith's biomes.

### A note on the pack's size

53 mods is a lot, and some of them pull in a fair bit underneath - Create
Ore Excavation needs Sinytra Connector and Forgified Fabric API to run on
NeoForge, which is how it ships for 1.21.1. If the server starts slowly
or a mod misbehaves, that pairing is worth looking at first.
