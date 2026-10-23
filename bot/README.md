# HoneyBeeSMP Discord Bot

The bot that looks after the HoneyBeeSMP Discord server. It answers
questions about the Minecraft server, and it sets the server's channels,
roles and permissions up in the first place.

## What it does

- `/status` - how the Minecraft server is doing: players online, version,
  and the address to connect to.
- `/invite` - how to join, including where to get the modpack.
- `/setup` - create the server's channels, roles and permissions, and put
  the permissions right on anything that is already there. Admins only.
- New members are given the `Member` role when they join.
- Audit events are posted to the staff-only `#logs` channel: message
  edits/deletes, joins/leaves, role and channel changes, forum threads,
  invites, voice moves, bans and unbans. Message content is included when
  Discord provides it; enable the Message Content Intent in the developer
  portal if you want full before/after text.

The Minecraft server is asked using the ordinary server list ping, so
nothing has to be installed or configured on the Minecraft side, and no
credentials are needed for it.

## The server layout

`/setup` (or `scripts/discord-setup.py`) puts this in place:

    Information   rules, announcements, server-info
    Community     general, media, builds
    Support       help, bugs, suggestions
    Staff         staff-chat, logs
    Voice         lounge, gaming, afk

`bugs` and `suggestions` are forum channels, so each report or idea is a
post of its own.

And these roles, from the top down:

    HoneyBee     the bot
    Owner        the server owner
    Admin        runs the server
    Moderator    keeps the community in order
    Builder      trusted on the Minecraft server
    Member       everybody else

The bot's role sits at the top so that it can hand out the roles below it.
`#rules` and `#announcements` are read-only for ordinary members, and the
`Staff` category is hidden from them.

Running the setup again is safe. Anything that already exists is kept and
repaired rather than made again, so it can be used whenever the layout
changes.

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
| `DISCORD_LOG_CHANNEL_ID` | channel for audit logs (optional; defaults to `#logs`) |
| `SERVER_ADDRESS` | the Minecraft server's address |
| `SERVER_PORT` | the Minecraft server's port |
| `POLL_SECONDS` | how often to check the player list |
| `DISCORD_COMMAND_SCOPE` | `guild` for this server only, `global` for all |
