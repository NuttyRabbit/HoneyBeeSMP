"""Post a readable audit trail to the staff-only Discord logs channel.

The bot is event-driven: Discord's gateway sends the details, and this
module turns them into compact embeds. Message content is included when
Discord gives it to us; without the Message Content Intent, the author,
channel and attachments are still logged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import discord

log = logging.getLogger("honeybee.audit")

GREEN = discord.Colour(0x2ECC71)
RED = discord.Colour(0xE74C3C)
ORANGE = discord.Colour(0xE67E22)
BLUE = discord.Colour(0x3498DB)
PURPLE = discord.Colour(0x9B59B6)
GREY = discord.Colour(0x95A5A6)


def _clip(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _block(value: str, limit: int = 1000) -> str:
    """Put user text in a code block, safely enough for an embed."""
    text = value.replace("```", "``\u200b`")
    return f"```\n{_clip(text, limit)}\n```"


def _user(value: discord.abc.User | None) -> str:
    if value is None:
        return "unknown"
    return f"{value.mention} ({value})"


def _channel(value: object | None) -> str:
    if value is None:
        return "none"
    name = getattr(value, "name", "unknown")
    mention = getattr(value, "mention", f"#{name}")
    return f"{mention} (`#{name}`)"


def _roles(value: Iterable[discord.Role]) -> str:
    names = [role.name for role in value]
    return ", ".join(names) if names else "none"


def _when(value: object | None) -> str:
    if value is None:
        return "unknown"
    return discord.utils.format_dt(value, "f")  # type: ignore[arg-type]


def _content(message: discord.Message) -> str:
    if message.content:
        return _block(message.content)
    if message.embeds:
        return "Embed only"
    if message.attachments:
        return "Attachment only"
    return "No text (or Message Content Intent is off)"


def _attachments(message: discord.Message) -> str:
    if not message.attachments:
        return ""
    return "\n".join(
        f"[{attachment.filename}]({attachment.url})"
        for attachment in message.attachments
    )


def _permission_changes(
    before: discord.Permissions, after: discord.Permissions
) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    for name, value in after:
        old = getattr(before, name)
        if value and not old:
            added.append(name)
        elif old and not value:
            removed.append(name)
    return added, removed


class AuditLogger:
    """Send embeds to the configured logs channel."""

    def __init__(self, channel: discord.TextChannel, guild_id: int) -> None:
        self.channel = channel
        self.guild_id = guild_id

    async def _send(
        self,
        title: str,
        *,
        description: str | None = None,
        colour: discord.Colour = BLUE,
        fields: Iterable[tuple[str, object, bool]] = (),
        footer: str | None = None,
    ) -> None:
        embed = discord.Embed(
            title=title,
            colour=colour,
            timestamp=discord.utils.utcnow(),
        )
        if description:
            embed.description = _clip(description, 4096)
        for name, value, inline in fields:
            if value is None or value == "":
                continue
            embed.add_field(name=name, value=_clip(value, 1024), inline=inline)
        if footer:
            embed.set_footer(text=_clip(footer, 2048))
        try:
            await self.channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as exc:
            log.warning("could not post to the logs channel: %s", exc)

    async def startup(self, user: discord.ClientUser | None, latency: float) -> None:
        await self._send(
            "Bot connected",
            colour=GREEN,
            fields=[
                ("Account", _user(user), False),
                ("Latency", f"{latency * 1000:.0f} ms", True),
            ],
        )

    # -- messages -----------------------------------------------------------

    def _message_ok(self, message: discord.Message) -> bool:
        return (
            message.guild is not None
            and message.guild.id == self.guild_id
            and not message.author.bot
            and message.channel.id != self.channel.id
        )

    async def message_delete(self, message: discord.Message) -> None:
        if not self._message_ok(message):
            return
        fields = [
            ("Author", _user(message.author), True),
            ("Channel", _channel(message.channel), True),
            ("Sent", _when(message.created_at), True),
            ("Content", _content(message), False),
            ("Attachments", _attachments(message), False),
            ("Jump", f"[Open message]({message.jump_url})", False),
        ]
        await self._send(
            "Message deleted",
            colour=RED,
            fields=fields,
            footer=f"Message ID: {message.id}",
        )

    async def message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if not self._message_ok(after):
            return
        if (
            before.content == after.content
            and before.attachments == after.attachments
            and before.embeds == after.embeds
        ):
            return
        fields = [
            ("Author", _user(after.author), True),
            ("Channel", _channel(after.channel), True),
            ("Before", _content(before), False),
            ("After", _content(after), False),
            ("Attachments", _attachments(after), False),
            ("Jump", f"[Open message]({after.jump_url})", False),
        ]
        await self._send(
            "Message edited",
            colour=ORANGE,
            fields=fields,
            footer=f"Message ID: {after.id}",
        )

    async def bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        channel = messages[0].channel
        if channel.id == self.channel.id:
            return
        authors = sorted({str(message.author) for message in messages})
        snippets = []
        for message in messages[:10]:
            if message.content:
                snippets.append(f"{message.author}: {_clip(message.content, 200)}")
        await self._send(
            "Messages bulk deleted",
            colour=RED,
            fields=[
                ("Channel", _channel(channel), True),
                ("Messages", str(len(messages)), True),
                ("Authors", _clip(", ".join(authors), 1024), False),
                ("First messages", "\n".join(snippets) if snippets else "No text available", False),
            ],
        )

    # -- members ------------------------------------------------------------

    async def member_join(self, member: discord.Member) -> None:
        if member.guild.id != self.guild_id:
            return
        await self._send(
            "Member joined",
            colour=GREEN,
            fields=[
                ("Member", _user(member), True),
                ("Account created", _when(member.created_at), True),
                ("Joined", _when(member.joined_at), True),
                ("Roles", _roles(member.roles[1:]), False),
                ("Bot", "yes" if member.bot else "no", True),
            ],
            footer=f"User ID: {member.id}",
        )

    async def member_remove(self, member: discord.Member) -> None:
        if member.guild.id != self.guild_id:
            return
        await self._send(
            "Member left",
            colour=RED,
            fields=[
                ("Member", _user(member), True),
                ("Joined", _when(member.joined_at), True),
                ("Roles", _roles(member.roles[1:]), False),
                ("Bot", "yes" if member.bot else "no", True),
            ],
            footer=f"User ID: {member.id}",
        )

    async def member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if after.guild.id != self.guild_id:
            return
        changes: list[str] = []
        if before.nick != after.nick:
            changes.append(f"Nickname: {before.nick!r} → {after.nick!r}")
        added = [role.name for role in after.roles if role not in before.roles]
        removed = [role.name for role in before.roles if role not in after.roles]
        if added:
            changes.append(f"Roles added: {', '.join(added)}")
        if removed:
            changes.append(f"Roles removed: {', '.join(removed)}")
        before_timeout = getattr(before, "timed_out_until", None)
        after_timeout = getattr(after, "timed_out_until", None)
        if before_timeout != after_timeout:
            changes.append(f"Timeout: {_when(before_timeout)} → {_when(after_timeout)}")
        if not changes:
            return
        await self._send(
            "Member updated",
            colour=ORANGE,
            fields=[
                ("Member", _user(after), True),
                ("Changes", "\n".join(changes), False),
            ],
            footer=f"User ID: {after.id}",
        )

    async def member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != self.guild_id:
            return
        await self._send(
            "Member banned",
            colour=RED,
            fields=[("User", _user(user), True)],
            footer=f"User ID: {user.id}",
        )

    async def member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != self.guild_id:
            return
        await self._send(
            "Member unbanned",
            colour=GREEN,
            fields=[("User", _user(user), True)],
            footer=f"User ID: {user.id}",
        )

    # -- roles --------------------------------------------------------------

    async def role_create(self, role: discord.Role) -> None:
        if role.guild.id != self.guild_id:
            return
        await self._send(
            "Role created",
            colour=GREEN,
            fields=[
                ("Role", f"{role.mention} (`{role.name}`)", True),
                ("Colour", str(role.colour), True),
                ("Hoisted", str(role.hoist), True),
                ("Mentionable", str(role.mentionable), True),
            ],
            footer=f"Role ID: {role.id}",
        )

    async def role_delete(self, role: discord.Role) -> None:
        if role.guild.id != self.guild_id:
            return
        await self._send(
            "Role deleted",
            colour=RED,
            fields=[
                ("Role", f"`{role.name}`", True),
                ("Colour", str(role.colour), True),
            ],
            footer=f"Role ID: {role.id}",
        )

    async def role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        if after.guild.id != self.guild_id:
            return
        changes: list[str] = []
        for attribute, label in (
            ("name", "Name"),
            ("colour", "Colour"),
            ("hoist", "Hoisted"),
            ("mentionable", "Mentionable"),
            ("position", "Position"),
        ):
            old = getattr(before, attribute)
            new = getattr(after, attribute)
            if old != new:
                changes.append(f"{label}: {old!r} → {new!r}")
        added, removed = _permission_changes(before.permissions, after.permissions)
        if added:
            changes.append(f"Permissions added: {', '.join(added)}")
        if removed:
            changes.append(f"Permissions removed: {', '.join(removed)}")
        if not changes:
            return
        await self._send(
            "Role updated",
            colour=ORANGE,
            fields=[
                ("Role", f"{after.mention} (`{after.name}`)", True),
                ("Changes", "\n".join(changes), False),
            ],
            footer=f"Role ID: {after.id}",
        )

    # -- channels and threads ----------------------------------------------

    async def channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != self.guild_id:
            return
        await self._send(
            "Channel created",
            colour=GREEN,
            fields=[
                ("Channel", _channel(channel), True),
                ("Type", str(channel.type), True),
                ("Category", _channel(getattr(channel, "category", None)), True),
            ],
            footer=f"Channel ID: {channel.id}",
        )

    async def channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != self.guild_id:
            return
        await self._send(
            "Channel deleted",
            colour=RED,
            fields=[
                ("Channel", f"`#{channel.name}`", True),
                ("Type", str(channel.type), True),
                ("Category", _channel(getattr(channel, "category", None)), True),
            ],
            footer=f"Channel ID: {channel.id}",
        )

    async def channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        if after.guild.id != self.guild_id:
            return
        changes: list[str] = []
        for attribute, label in (
            ("name", "Name"),
            ("position", "Position"),
            ("category_id", "Category"),
            ("nsfw", "NSFW"),
            ("slowmode_delay", "Slowmode"),
            ("topic", "Topic"),
            ("user_limit", "User limit"),
            ("bitrate", "Bitrate"),
        ):
            if not hasattr(before, attribute) or not hasattr(after, attribute):
                continue
            old = getattr(before, attribute)
            new = getattr(after, attribute)
            if old != new:
                changes.append(f"{label}: {old!r} → {new!r}")
        if not changes:
            return
        await self._send(
            "Channel updated",
            colour=ORANGE,
            fields=[
                ("Channel", _channel(after), True),
                ("Changes", "\n".join(changes), False),
            ],
            footer=f"Channel ID: {after.id}",
        )

    async def thread_create(self, thread: discord.Thread) -> None:
        if thread.guild.id != self.guild_id:
            return
        await self._send(
            "Thread created",
            colour=GREEN,
            fields=[
                ("Thread", _channel(thread), True),
                ("Parent", _channel(thread.parent), True),
                ("Owner", f"<@{thread.owner_id}>" if thread.owner_id else "unknown", True),
            ],
            footer=f"Thread ID: {thread.id}",
        )

    async def thread_delete(self, thread: discord.Thread) -> None:
        if thread.guild.id != self.guild_id:
            return
        await self._send(
            "Thread deleted",
            colour=RED,
            fields=[
                ("Thread", f"`{thread.name}`", True),
                ("Parent", _channel(thread.parent), True),
            ],
            footer=f"Thread ID: {thread.id}",
        )

    async def thread_update(
        self, before: discord.Thread, after: discord.Thread
    ) -> None:
        if after.guild.id != self.guild_id:
            return
        changes: list[str] = []
        for attribute, label in (
            ("name", "Name"),
            ("archived", "Archived"),
            ("locked", "Locked"),
            ("pinned", "Pinned"),
            ("slowmode_delay", "Slowmode"),
            ("auto_archive_duration", "Auto archive"),
        ):
            if not hasattr(before, attribute) or not hasattr(after, attribute):
                continue
            old = getattr(before, attribute)
            new = getattr(after, attribute)
            if old != new:
                changes.append(f"{label}: {old!r} → {new!r}")
        if not changes:
            return
        await self._send(
            "Thread updated",
            colour=ORANGE,
            fields=[
                ("Thread", _channel(after), True),
                ("Changes", "\n".join(changes), False),
            ],
            footer=f"Thread ID: {after.id}",
        )

    # -- invites and voice --------------------------------------------------

    async def invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is None or invite.guild.id != self.guild_id:
            return
        await self._send(
            "Invite created",
            colour=BLUE,
            fields=[
                ("Code", f"`{invite.code}`", True),
                ("Channel", _channel(invite.channel), True),
                ("Inviter", _user(invite.inviter), True),
                ("Max uses", str(invite.max_uses or "unlimited"), True),
                ("Max age", f"{invite.max_age}s" if invite.max_age else "never", True),
            ],
        )

    async def invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is None or invite.guild.id != self.guild_id:
            return
        await self._send(
            "Invite deleted",
            colour=ORANGE,
            fields=[
                ("Code", f"`{invite.code}`", True),
                ("Channel", _channel(invite.channel), True),
            ],
        )

    async def voice_state(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.guild.id != self.guild_id or member.bot:
            return
        if before.channel == after.channel:
            return
        if after.channel is not None and before.channel is None:
            title, colour = "Joined voice", GREEN
        elif before.channel is not None and after.channel is None:
            title, colour = "Left voice", RED
        else:
            title, colour = "Moved voice", BLUE
        await self._send(
            title,
            colour=colour,
            fields=[
                ("Member", _user(member), True),
                ("From", _channel(before.channel), True),
                ("To", _channel(after.channel), True),
            ],
        )
