"""The HoneyBeeSMP Discord bot.

A small bot for the server's Discord: it answers questions about the
Minecraft server, and it keeps a channel up to date with who is online.

Everything it needs comes from the environment:

    DISCORD_TOKEN            the bot token
    DISCORD_GUILD_ID          the server it is for
    DISCORD_STATUS_CHANNEL   channel to post the player list in (optional)
    SERVER_ADDRESS           the Minecraft server's address
    SERVER_PORT              the Minecraft server's port

The Minecraft server is queried with the ordinary server list ping, so
no credentials are needed for it and nothing has to be installed on the
Minecraft side.
"""

import asyncio
import json
import logging
import os
import sys

import discord
from discord.ext import commands

log = logging.getLogger("honeybee")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Config:
    """The settings, read once at startup."""

    def __init__(self) -> None:
        self.token = _required("DISCORD_TOKEN")
        self.guild_id = _required("DISCORD_GUILD_ID")
        self.status_channel_id = os.environ.get("DISCORD_STATUS_CHANNEL_ID", "").strip()
        self.server_address = os.environ.get("SERVER_ADDRESS", "play.honeybeesmp.co.uk").strip()
        self.server_port = int(os.environ.get("SERVER_PORT", "25566"))
        # How often to check whether the player list has changed.
        self.poll_seconds = int(os.environ.get("POLL_SECONDS", "30"))

    @property
    def address(self) -> str:
        return f"{self.server_address}:{self.server_port}"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"error: {name} is not set", file=sys.stderr)
        raise SystemExit(1)
    return value


# ---------------------------------------------------------------------------
# Talking to the Minecraft server
# ---------------------------------------------------------------------------


async def server_status(host: str, port: int) -> dict:
    """Ask a Minecraft server how it is doing.

    This is the same request the client makes to build its server list,
    so it needs no credentials and nothing running on the server side.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=10
    )
    try:
        # A handshake, then a status request. Every packet is a varint
        # length followed by the packet.
        host_bytes = host.encode()
        handshake = (
            _varint(0)  # packet id: handshake
            + _varint(767)  # protocol version
            + _varint(len(host_bytes))
            + host_bytes
            + port.to_bytes(2, "big")
            + _varint(1)  # next state: status
        )
        writer.write(_varint(len(handshake)) + handshake)
        writer.write(_varint(1) + _varint(0))  # status request
        await writer.drain()

        # The reply is one length-prefixed packet.
        length = await _read_varint_stream(reader)
        packet = await reader.readexactly(length)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    # Inside it: a varint packet id, a varint string length, and the JSON.
    offset = _skip_varint(packet, 0)  # packet id
    size = _read_varint(packet, offset)
    offset = _skip_varint(packet, offset)

    return json.loads(packet[offset : offset + size].decode("utf-8"))


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


async def _read_varint_stream(reader) -> int:
    """Read a varint from a stream."""
    number = 0
    shift = 0
    while True:
        byte = await reader.readexactly(1)
        number |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return number
        shift += 7


def _read_varint(data: bytes, offset: int) -> int:
    number = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        number |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return number
        shift += 7


def _skip_varint(data: bytes, offset: int) -> int:
    """The offset just past the varint at offset."""
    while data[offset] & 0x80:
        offset += 1
    return offset + 1


# ---------------------------------------------------------------------------
# The bot
# ---------------------------------------------------------------------------


class HoneyBee(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        # We want to notice when the player count changes, and the server
        # list ping gives us that without any message intents.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self._last_players: set[str] = set()
        self._status_message: discord.Message | None = None

    async def setup_hook(self) -> None:
        await self.tree.sync(guild=discord.Object(id=self.config.guild_id))
        log.info("commands registered")

    # -- commands -----------------------------------------------------------

    @discord.app_commands.command(name="status", description="How the Minecraft server is doing")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            status = await server_status(
                self.config.server_address, self.config.server_port
            )
        except Exception as exc:
            log.warning("could not reach the Minecraft server: %s", exc)
            await interaction.followup.send(
                f"The Minecraft server is not answering right now. It may be "
                f"starting up, or it may be down."
            )
            return

        version = status.get("version", {})
        players = status.get("players", {})
        embed = discord.Embed(
            title="HoneyBeeSMP",
            colour=discord.Colour(0xFFC107),
        )
        embed.add_field(name="Players", value=f"{players.get('online', 0)} / {players.get('max', 0)}")
        embed.add_field(name="Version", value=version.get("name", "unknown"))
        embed.add_field(name="Address", value=f"`{self.config.address}`")
        await interaction.followup.send(embed=embed)

    @discord.app_commands.command(name="invite", description="How to join the Minecraft server")
    async def invite(self, interaction: discord.Interaction) -> None:
        await interaction.response.send(
            f"Join us at `{self.config.address}`.\n"
            f"You will need the modpack - the Modrinth App or Prism Launcher "
            f"will install it for you from the server's Modrinth page."
        )

    # -- the status channel -------------------------------------------------

    async def status_channel(self) -> discord.TextChannel | None:
        if not self.config.status_channel_id:
            return None
        channel = self.get_channel(int(self.config.status_channel_id))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def refresh_status(self) -> None:
        """Post or update the player list in the status channel."""
        channel = await self.status_channel()
        if channel is None:
            return

        try:
            status = await server_status(
                self.config.server_address, self.config.server_port
            )
        except Exception as exc:
            log.warning("could not reach the Minecraft server: %s", exc)
            return

        players = status.get("players", {})
        online = players.get("online", 0)
        maximum = players.get("max", 0)
        version = status.get("version", {}).get("name", "unknown")

        embed = discord.Embed(
            title="HoneyBeeSMP",
            colour=discord.Colour(0xFFC107),
        )
        embed.add_field(name="Players", value=f"{online} / {maximum}")
        embed.add_field(name="Version", value=version)
        embed.add_field(name="Address", value=f"`{self.config.address}`")

        if self._status_message is not None:
            try:
                await self._status_message.edit(embed=embed)
                return
            except discord.NotFound:
                # It was deleted, so post a new one.
                self._status_message = None

        self._status_message = await channel.send(embed=embed)

    async def poll(self) -> None:
        """Watch the player list, and say when somebody joins or leaves."""
        while True:
            await self.refresh_status()
            await asyncio.sleep(self.config.poll_seconds)

    async def announce_changes(self) -> None:
        """Post when the player list changes."""
        while True:
            await asyncio.sleep(self.config.poll_seconds)
            channel = await self.status_channel()
            if channel is None:
                continue
            try:
                status = await server_status(
                    self.config.server_address, self.config.server_port
                )
            except Exception:
                continue

            names = set(status.get("players", {}).get("sample", []) or [])
            joined = names - self._last_players
            left = self._last_players - names
            self._last_players = names

            for name in joined:
                await channel.send(f"{name} joined the server.")
            for name in left:
                await channel.send(f"{name} left the server.")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config()
    bot = HoneyBee(config)

    async with bot:
        # The status channel only matters if it has been set.
        if config.status_channel_id:
            bot.loop.create_task(bot.poll())
        await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
