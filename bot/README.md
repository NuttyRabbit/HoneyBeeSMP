# HoneyBeeSMP Discord Bot

The bot that looks after the HoneyBeeSMP Discord server. It answers
questions about the Minecraft server and keeps a channel up to date with
who is online.

## What it does

- `/status` - how the Minecraft server is doing: players online, version,
  and the address to connect to.
- `/invite` - how to join, including where to get the modpack.
- A status channel - an embed in a chosen channel showing the player
  count and version, refreshed in place, along with a message whenever
  somebody joins or leaves.

The Minecraft server is asked using the ordinary server list ping, so
nothing has to be installed or configured on the Minecraft side, and no
credentials are needed for it.

## Layout

- `src/`   - bot source code
- `data/`  - persistent data - gitignored
- `logs/`  - log output - gitignored
- `.env`   - secrets - gitignored

## Running it

The bot needs its token and the server it is for:

```sh
cp .env.example .env
$EDITOR .env
```

Then, on the machine that runs it:

```sh
sudo ./scripts/install-bot.sh live
```

That makes a virtual environment, installs `requirements.txt` into it, and
installs a systemd unit so the bot starts on boot and restarts if it
falls over. Logs are in `journalctl -u honeybeesmp-discord-bot.service`.

## Configuration

| Variable | What it is |
| --- | --- |
| `DISCORD_TOKEN` | the bot token from the Discord developer portal |
| `DISCORD_GUILD_ID` | the server the bot is for |
| `DISCORD_STATUS_CHANNEL_ID` | channel for the status embed and join/leave messages (optional) |
| `SERVER_ADDRESS` | the Minecraft server's address |
| `SERVER_PORT` | the Minecraft server's port |
| `POLL_SECONDS` | how often to check the player list |
