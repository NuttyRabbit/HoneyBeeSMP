# HoneyBeeSMP modpack

This directory is a [Modrinth pack](https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack).
It is the **single source of truth** for which mods we run, on both the
server and the players' clients.

## Why a pack and not a list of mods

Server mods and client mods are **different sets**, and that is the whole
reason for this format:

| Mod | Client | Server |
|---|---|---|
| Terralith (world generation) | optional | required |
| Lithostitched (its library) | unsupported | required |
| Sodium (rendering) | required | unsupported |

A plain list of "our mods" cannot express that. The pack format records
`env` per file, so the same file describes what the server installs and
what a player installs - and they can never drift apart.

The pack also records a SHA-512 hash for every file, so a download that is
corrupted or tampered with is caught rather than silently installed.

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

All of this is done through `scripts/modpack.py`, which is the same code
the deploy uses - so the pack and the running server cannot disagree.

```sh
# Add a mod, and any dependencies it needs
python3 scripts/modpack.py add create --env dev

# See what is in the pack
python3 scripts/modpack.py list
python3 scripts/modpack.py list server
python3 scripts/modpack.py list client

# Build the pack players download
python3 scripts/modpack.py build /tmp/HoneyBeeSMP.mrpack

# Check the mods on a server match the pack
python3 scripts/modpack.py verify /opt/crafty/servers/<id>/mods
```

### Adding a mod

1. `python3 scripts/modpack.py add <slug> --env dev`
   - Use the Modrinth project slug, e.g. `create` or `journeymap`.
   - This pulls in required dependencies automatically, so you will not hit
     "Mod X requires Y or above" on the server.
   - It records the client/server split for you.

2. Commit `minecraft/modpack/modrinth.index.json` and push to `develop`.

3. The deploy installs it on the dev server. Restart the server so it
   loads:

   ```sh
   make mc-restart-dev
   ```

4. Test it, then merge to `main` and push. The live server gets the same
   pack. Restart it too: `make mc-restart`.

### Removing a mod

Remove its entry from `modrinth.index.json` and push. The deploy deletes
the jar. Restart the server afterwards so it stops using the mod.

## Handing the pack to players

Build it and put it somewhere players can download it:

```sh
python3 scripts/modpack.py build /var/www/honeybeesmp.co.uk/HoneyBeeSMP.mrpack
```

Players import it into Modrinth App, Prism Launcher, ATLauncher or
CurseForge, and it installs the right mods and configs for them.

Because the pack is generated from the same index the server uses, players
are always on the same version as the server.

## A note on mod choices

Not every mod belongs on a server. A client-only mod (Sodium, Xaero's,
JourneyMap) will crash a dedicated server with
`NoClassDefFoundError: org/lwjgl/Version` if it is installed on it. The
pack format records this per file, and `modpack.py` only installs the
server-side ones - but if you add a mod by hand, check its Modrinth page
first: it must not say "Client: Required".
