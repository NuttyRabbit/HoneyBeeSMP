# HoneyBeeSMP

Central workspace for the HoneyBeeSMP server, website and tooling.

Open this folder (`~/honeybeesmp`) as a remote project in Zed.

## Repository layout

| Path                    | What it is                                            | Tracked? |
|-------------------------|-------------------------------------------------------|----------|
| `website/`              | Website source (deployed to /var/www/honeybeesmp.co.uk)| yes      |
| `bot/`                  | Discord bot source                                     | yes      |
| `README.md`             | This file                                             | yes      |
| `crafty-panel`          | Symlink -> /opt/crafty (Minecraft panel + data)        | no       |
| `minecraft-servers`     | Symlink -> /opt/crafty/servers (worlds, jars)          | no       |
| `discord-bot`           | Symlink -> /opt/honeybee-discord-bot (live bot dir)    | no       |

The symlinks are for convenience while navigating. They point outside the repo
and are deliberately ignored by git: their contents are either huge/generable
(Minecraft) or secret (Crafty credentials, TLS keys, databases).

## What is intentionally NOT in git

- **Minecraft worlds and server files** (`/opt/crafty/servers`, ~189M) — back
  these up separately. They are the one thing that genuinely cannot be
  regenerated.
- **Crafty config and databases** (`/opt/crafty/config`) — includes
  `default-creds.txt` (the panel admin password), API tokens, and the TLS
  private key. Never commit these.
- Logs, caches, backups, `.env` files.

See `.gitignore` for the full list.

## Deploying the website

`website/` is the source of truth. The live site is served from
`/var/www/honeybeesmp.co.uk` by nginx. After editing:

```sh
sudo cp website/index.html /var/www/honeybeesmp.co.uk/index.html
```

Consider replacing this with a git hook or a small deploy script.

## Services on this host

| Service              | Where                                          |
|----------------------|------------------------------------------------|
| Website + panel HTTPS| nginx, Let's Encrypt (auto-renew)              |
| Crafty Controller    | Docker container `crafty_container`, :8443     |
| Discord bot          | not deployed yet                               |

Relevant commands:

```sh
sudo docker ps
sudo docker logs crafty_container -f
sudo nginx -t && sudo systemctl reload nginx
```
