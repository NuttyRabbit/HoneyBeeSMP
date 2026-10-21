# HoneyBeeSMP modpack

This directory is a [Modrinth pack](https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack).
It is the **single source of truth** for which mods we run, on both the
server and the players' clients.

## What is in the pack

27 mods, chosen to be a coherent set rather than the biggest one possible.

### Create and factory building

| Mod | Why |
|---|---|
| Create | The centrepiece. Belts, shafts, cogs, trains, contraptions. |
| Create: Crafts & Additions | Extra Create machines and fluids. |
| Create: Big Cannons | Cannons and projectiles for Create. |
| Create: Compression | Compressors and the machines around them. |
| Sophisticated Storage | Storage blocks, and the drawers Create fills them with. |
| Productive Bees | Bees, and the automation built around them. |
| FastSuite / FastWorkbench | Crafting speed, so a big factory is not painful to use. |
| Ritchie's Projectile Library | Required by Big Cannons. |
| Sophisticated Core | Required by Sophisticated Storage. |

### Quality of life

| Mod | Why |
|---|---|
| EMI | Recipe viewer. |
| Jade | Block information in the world. |
| AppleSkin | Shows real food values. |
| Waystones | Teleport stones, for getting around. |
| Shulker Box Tooltip | See what is in a shulker without opening it. |
| Mouse Tweaks | Inventory right-click behaviour. |
| BetterF3 | F3 debug screen. |
| No Chat Reports | Chat without the reporting system. |
| Balm | Required by Waystones. |
| Cloth Config | Required by several mods. |
| Placebo | Required by FastSuite. |

### Performance

| Mod | Why |
|---|---|
| FerriteCore | A large chunk of the frame-time saving. |
| Spark | Profiler. Run `/spark` to see where the time goes. |
| AntiXray | Stops ore and cave reveals through the server. |

### Exploration and world generation

| Mod | Why |
|---|---|
| Terralith | Better terrain, caves and biomes. |
| Lithostitched | Required by Terralith. |
| Xaero's Minimap | Minimap and waypoints, for exploring. |

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

25 of the 27 mods go on the server. The two that do not - Mouse Tweaks and
BetterF3 - are client only, and players get them from the pack.

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

- **One mod per job.** Xaero's Minimap is in, JourneyMap is not.
- **No redundant world generators.** Terralith is in; Tectonic and Modern
  World Creation are not, because they fight with it.
- **Check for conflicts before adding.** A client-only mod on the server
  crashes it with `NoClassDefFoundError: org/lwjgl/Version`.
- **Prefer mods that serve both sides.** Mods that work on the client and
  the server mean one pack covers everyone.
