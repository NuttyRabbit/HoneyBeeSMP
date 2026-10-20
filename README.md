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
| Minecraft worlds, jars, mods | `/opt/crafty/servers` | ~189 MB, regenerable; back up separately |
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
./scripts/deploy.sh          # publishes website/ and bot/
./scripts/deploy.sh web      # website only
./scripts/deploy.sh bot      # bot only
```

`deploy.sh` uses `rsync --delete`, so the live directories end up **exactly**
matching the repo (minus runtime files like `.env` and `bot/data`).

### Applying an update from GitHub to the server

```sh
./scripts/update.sh
```

This pulls, runs the checks, deploys, and reloads nginx. Safe to automate.

### Handy shortcuts

```sh
make help        # list all targets
make status      # git state, service state, and repo-vs-live drift
make check       # same checks CI runs
make deploy      # publish the website
make crafty-logs # tail the Minecraft panel logs
```

---

## Layout

```
.
├── .github/workflows/checks.yml   CI: sanity checks on push
├── Makefile                       task shortcuts
├── README.md
├── bot/                           Discord bot
│   ├── .env.example               template (real .env stays on the server)
│   ├── .rsync-exclude
│   ├── data/                      runtime state (gitignored)
│   ├── logs/                      runtime logs (gitignored)
│   └── src/                       bot source
├── scripts/
│   ├── check.sh                   no secrets / no huge files / ignore rules
│   ├── deploy.sh                  repo -> live directories
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
