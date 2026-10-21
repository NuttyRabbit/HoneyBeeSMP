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
import time

import discord
from discord.ext import commands

from . import setup as server_setup

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
        # Where to write the status file the website reads. Blank to turn
        # it off.
        self.status_file = os.environ.get(
            "STATUS_FILE", "/var/www/honeybeesmp.co.uk/status.json"
        ).strip()
        # Where to put the slash commands: "guild" for this server only,
        # or "global" for every server the bot is in. Guild commands appear
        # straight away; global ones can take an hour to reach Discord.
        self.command_scope = os.environ.get("DISCORD_COMMAND_SCOPE", "guild").strip().lower()
        if self.command_scope not in ("guild", "global"):
            raise SystemExit("error: DISCORD_COMMAND_SCOPE must be guild or global")

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
        # Needed so that the bot can hand out the Member role when
        # somebody joins. Discord allows this for bots with the
        # Administrator permission.
        intents.members = True
        # We want to notice when the player count changes, and the server
        # list ping gives us that without any message intents.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config
        self._status_message: discord.Message | None = None

        # discord.py does not pick up slash commands that are defined as
        # methods on a Bot subclass, so they are added to the tree here.
        if config.command_scope == "global":
            self.tree.add_command(self.status)
            self.tree.add_command(self.invite)
            self.tree.add_command(self.setup)
        else:
            guild = discord.Object(id=config.guild_id)
            self.tree.add_command(self.status, guild=guild)
            self.tree.add_command(self.invite, guild=guild)
            self.tree.add_command(self.setup, guild=guild)

    async def setup_hook(self) -> None:
        if self.config.command_scope == "global":
            await self.tree.sync()
        else:
            await self.tree.sync(guild=discord.Object(id=self.config.guild_id))
        log.info("commands registered (%s)", self.config.command_scope)

    # -- joining ------------------------------------------------------------

    async def on_member_join(self, member: discord.Member) -> None:
        """Give new members the Member role."""
        guild = member.guild
        if guild.id != int(self.config.guild_id):
            return
        role = server_setup.find_role(guild, server_setup.MEMBER_ROLE)
        if role is None or role in member.roles:
            return
        try:
            await member.add_roles(role, reason="Welcome to the server")
            log.info("gave %s the %s role", member, role.name)
        except discord.HTTPException as exc:
            log.warning("could not give %s the Member role: %s", member, exc)

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

    @discord.app_commands.command(
        name="setup",
        description="Set up the server's channels, roles and permissions",
    )
    @discord.app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        """Create the channels and roles the server needs.

        This can be run as often as you like: anything that is already
        there is kept and repaired rather than made again.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This only works in a server.", ephemeral=True)
            return

        try:
            await server_setup.apply_setup(guild)
        except discord.HTTPException as exc:
            log.exception("the setup failed")
            await interaction.followup.send(f"The setup failed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            "The server is set up: the channels, the roles and the "
            "permissions are all in place.",
            ephemeral=True,
        )

    # -- the status channel -------------------------------------------------

    async def status_channel(self) -> discord.TextChannel | None:
        if not self.config.status_channel_id:
            return None
        channel = self.get_channel(int(self.config.status_channel_id))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _update_embed(
        self, channel: discord.TextChannel, online: int, maximum: int, version: str
    ) -> None:
        """Post the status embed, or update the one that is already there."""
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

    async def watch(self) -> None:
        """Keep the status channel and the website's status file up to date."""
        channel = await self.status_channel()

        last_count: int | None = None
        last_names: set[str] = set()

        while True:
            try:
                status = await server_status(
                    self.config.server_address, self.config.server_port
                )
            except Exception as exc:
                log.warning("could not reach the Minecraft server: %s", exc)
                self._publish_offline()
                await asyncio.sleep(self.config.poll_seconds)
                continue

            players = status.get("players", {})
            online = int(players.get("online", 0))
            maximum = int(players.get("max", 0))
            version = status.get("version", {}).get("name", "unknown")
            # The server only lists a handful of names, so the names are a
            # hint and the player count is the reliable part.
            names = set(players.get("sample") or [])

            self._publish_status(online, maximum, version)

            if channel is not None:
                if last_count is not None and online != last_count:
                    await self._announce(channel, online - last_count, names, last_names)
                last_count = online
                last_names = names
                await self._update_embed(channel, online, maximum, version)

            await asyncio.sleep(self.config.poll_seconds)

    # -- the website's status file -------------------------------------------

    def _publish_status(self, online: int, maximum: int, version: str) -> None:
        """Write the status file the website reads."""
        if not self.config.status_file:
            return
        self._write_status(
            {
                "online": online,
                "max": maximum,
                "version": version,
                "address": self.config.address,
                "online_server": True,
                "updated": int(time.time()),
            }
        )

    def _publish_offline(self) -> None:
        """Tell the website the server is not answering."""
        if not self.config.status_file:
            return
        self._write_status(
            {
                "online": 0,
                "max": 0,
                "version": "",
                "address": self.config.address,
                "online_server": False,
                "updated": int(time.time()),
            }
        )

    def _write_status(self, payload: dict) -> None:
        path = self.config.status_file
        # Write it to one side and move it into place, so a reader never
        # sees half a file.
        temporary = f"{path}.tmp"
        try:
            with open(temporary, "w") as handle:
                json.dump(payload, handle)
            os.replace(temporary, path)
        except OSError as exc:
            log.warning("could not write the status file %s: %s", path, exc)
            try:
                os.unlink(temporary)
            except OSError:
                pass

    async def _announce(
        self, channel: discord.TextChannel, change: int, names: set[str], last_names: set[str]
    ) -> None:
        """Say that somebody joined or left, if we can tell who."""
        if change > 0:
            arrived = names - last_names
            if len(arrived) == change:
                await channel.send(f"{', '.join(sorted(arrived))} joined the server.")
            else:
                await channel.send(
                    f"{change} player{'s' if change > 1 else ''} joined the server."
                )
        else:
            left = last_names - names
            if len(left) == -change:
                await channel.send(f"{', '.join(sorted(left))} left the server.")
            else:
                await channel.send(
                    f"{-change} player{'s' if change < -1 else ''} left the server."
                )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config()
    bot = HoneyBee(config)

    async with bot:
        # This keeps the website's status file up to date, and the status
        # channel too if one has been set.
        bot.loop.create_task(bot.watch())
        await bot.start(config.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
