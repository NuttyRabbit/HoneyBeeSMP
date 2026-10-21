#!/usr/bin/env python3
"""Set up the Discord server: channels, roles and permissions.

This is the same thing the bot's /setup command does, but it can be run
without the bot being connected, which is handy the first time and
whenever the layout changes.

    sudo -u ubuntu /opt/honeybee-discord-bot/.venv/bin/python \
        /opt/honeybee-discord-bot/scripts/discord-setup.py

The settings come from the .env file next to the bot.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

# Allow running straight out of a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import discord  # noqa: E402

from honeybee_bot import setup as server_setup  # noqa: E402

log = logging.getLogger("discord-setup")


def load_env(path: Path) -> None:
    """Read the .env file into the environment."""
    if not path.exists():
        raise SystemExit(f"error: {path} does not exist")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    bot_dir = Path(__file__).resolve().parent.parent
    load_env(bot_dir / ".env")

    token = os.environ["DISCORD_TOKEN"]
    guild_id = int(os.environ["DISCORD_GUILD_ID"])

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True

    async with discord.Client(intents=intents) as client:
        await client.login(token)
        # The channels are only in the cache once the gateway has said
        # hello, so it is started in the background and waited for.
        gateway = asyncio.create_task(client.connect())
        try:
            await client.wait_until_ready()
            guild = client.get_guild(guild_id)
            if guild is None:
                raise SystemExit(f"error: the bot is not in the server {guild_id}")

            await server_setup.apply_setup(guild)

            print()
            print(f"the server {guild.name} is set up")
            print()
            print("roles:")
            for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
                if role.name == "@everyone":
                    continue
                print(f"  {role.position:>2}  {role.name}")
            print()
            print("channels:")
            for category in sorted(
                (c for c in guild.channels if isinstance(c, discord.CategoryChannel)),
                key=lambda c: c.position,
            ):
                print(f"  {category.name}")
                for channel in sorted(category.channels, key=lambda c: c.position):
                    print(f"      #{channel.name}")
        finally:
            await client.close()
            gateway.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await gateway


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
