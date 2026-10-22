"""The Discord server's layout: categories, channels, roles and permissions.

The setup is written as code rather than clicked together by hand, so it
can be run again at any time. Anything that already exists is reused and
repaired rather than duplicated, and anything that is missing is created.

The shape of it:

    Information   rules, announcements, server-info
    Community     general, media, builds
    Minecraft     help, whitelist, bugs
    Staff         staff-chat, logs
    Voice         lounge, gaming, afk

    Owner  >  Admin  >  Moderator  >  Builder  >  Member  >  everyone
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord
from discord import PermissionOverwrite

log = logging.getLogger("honeybee.setup")

# The role that every member gets when they join.
MEMBER_ROLE = "Member"
# The roles that can deal with the community.
STAFF_ROLES = ("Moderator", "Admin")
# The roles that run the server.
ADMIN_ROLES = ("Admin", "Owner")
# The role the bot itself has.
BOT_ROLE = "HoneyBee"

# The order the roles sit in, from the top down. The bot's role is at the
# top so that it can hand out the roles below it.
ROLE_ORDER = (BOT_ROLE, "Owner", "Admin", "Moderator", "Builder", MEMBER_ROLE)


@dataclass
class RoleSpec:
    name: str
    colour: int
    permissions: Permissions
    hoist: bool = True
    mentionable: bool = True


@dataclass
class ChannelSpec:
    name: str
    kind: str  # "text", "voice", "forum"
    topic: str = ""
    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class CategorySpec:
    name: str
    channels: list[ChannelSpec] = field(default_factory=list)


EVERYONE = "@everyone"

# Discord's own default channels, and what they are used for instead. The
# server already has these, so they are renamed and moved rather than
# being duplicated.
ADOPTED = {
    "Text channels": ("category", "Community"),
    "Voice channels": ("category", "Voice"),
    "moderator-only": ("text", "staff-chat"),
    "General": ("voice", "lounge"),
    "Minecraft": ("category", "Support"),
}

# Channels that used to be part of the layout and are not wanted now.
# They are deleted if they are still there.
REMOVED = ("whitelist",)


# What each role can do. The Owner role is the server owner, so it has
# everything. The Admin role runs the server. The Moderator role keeps
# the community in order. The Member role is what everybody gets.
MODERATOR_PERMISSIONS = dict(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
    attach_files=True,
    use_application_commands=True,
    manage_messages=True,
    kick_members=True,
    moderate_members=True,
    mute_members=True,
    move_members=True,
    view_audit_log=True,
)

ADMIN_PERMISSIONS = dict(
    MODERATOR_PERMISSIONS,
    manage_channels=True,
    manage_roles=True,
    manage_webhooks=True,
    ban_members=True,
    manage_nicknames=True,
    change_nickname=True,
    create_instant_invite=True,
    manage_threads=True,
    manage_events=True,
)

MEMBER_PERMISSIONS = dict(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    embed_links=True,
    attach_files=True,
    use_application_commands=True,
    connect=True,
    speak=True,
    create_public_threads=True,
    send_messages_in_threads=True,
)


def role_specs() -> list[RoleSpec]:
    """The roles the server has, from the top down."""
    return [
        RoleSpec("Owner", 0xF1C40F, discord.Permissions.all()),
        RoleSpec("Admin", 0xE74C3C, discord.Permissions(**ADMIN_PERMISSIONS)),
        RoleSpec("Moderator", 0x3498DB, discord.Permissions(**MODERATOR_PERMISSIONS)),
        RoleSpec("Builder", 0x2ECC71, discord.Permissions.none()),
        RoleSpec(BOT_ROLE, 0x95A5A6, discord.Permissions.all()),
        RoleSpec(MEMBER_ROLE, 0xFFFFFF, discord.Permissions(**MEMBER_PERMISSIONS)),
    ]


def category_specs() -> list[CategorySpec]:
    """The categories and channels the server has."""
    everyone = (EVERYONE,)
    staff = ("Moderator", "Admin")
    admins = ("Admin", "Owner")
    return [
        CategorySpec(
            "Information",
            [
                ChannelSpec(
                    "rules",
                    "text",
                    "The rules of the server. Please read them before you play.",
                    read=everyone,
                    write=staff,
                ),
                ChannelSpec(
                    "announcements",
                    "text",
                    "News from the server team.",
                    read=everyone,
                    write=staff,
                ),
                ChannelSpec(
                    "server-info",
                    "text",
                    "How to join, and how the server is doing.",
                    read=everyone,
                    write=("Moderator", "Admin", BOT_ROLE),
                ),
            ],
        ),
        CategorySpec(
            "Community",
            [
                ChannelSpec("general", "text", "Anything goes.", read=everyone, write=everyone),
                ChannelSpec("media", "text", "Screenshots and videos.", read=everyone, write=everyone),
                ChannelSpec("builds", "text", "Show off what you have built.", read=everyone, write=everyone),
            ],
        ),
        CategorySpec(
            "Support",
            [
                ChannelSpec("help", "text", "Questions about the modpack and the server.", read=everyone, write=everyone),
                ChannelSpec(
                    "bugs",
                    "forum",
                    "Something broken? Report it here.",
                    read=everyone,
                    write=everyone,
                    tags=("Crash", "Graphics", "Gameplay", "Other"),
                ),
                ChannelSpec(
                    "suggestions",
                    "forum",
                    "Ideas for the server, the pack and the Discord.",
                    read=everyone,
                    write=everyone,
                    tags=("Mods", "Builds", "Server", "Other"),
                ),
            ],
        ),
        CategorySpec(
            "Staff",
            [
                ChannelSpec("staff-chat", "text", "Staff only.", read=staff, write=staff),
                ChannelSpec("logs", "text", "Staff only.", read=admins, write=admins),
            ],
        ),
        CategorySpec(
            "Voice",
            [
                ChannelSpec("lounge", "voice", "Just talking.", read=everyone, write=everyone),
                ChannelSpec("gaming", "voice", "Playing games together.", read=everyone, write=everyone),
                ChannelSpec("afk", "voice", "Away from keyboard.", read=everyone, write=everyone),
            ],
        ),
    ]


RULES = """**HoneyBeeSMP Discord rules**

These are the rules for the Discord. The rules for the Minecraft server
itself are on the website: https://honeybeesmp.co.uk/rules

1. Be kind. No harassment, no slurs, no bullying.
2. Keep chat in English, and keep it on topic.
3. No spam, no advertising, no scams, and no unsolicited DMs.
4. Keep anything adult or gory out of the channels that are not for it.
5. Put spoilers for anything recent in the channel for it, not in general.
6. Use the right channel: questions in `#help`, bugs in `#bugs`, and ideas
   in `#suggestions`.
7. Do not pick fights with the staff in public. If you want to raise
   something, ask a moderator for a private channel.
8. Staff decisions are final.
9. Staff can mute, timeout, kick or ban. Bans are for repeat or serious
   offences.
"""


def _overwrites(
    guild: discord.Guild,
    roles: dict[str, discord.Role],
    read: tuple[str, ...],
    write: tuple[str, ...],
) -> dict[discord.Role, PermissionOverwrite]:
    """Work out the channel overwrites for who can see and who can post."""
    everyone = guild.default_role
    result: dict[discord.Role, PermissionOverwrite] = {}

    if EVERYONE in read:
        result[everyone] = PermissionOverwrite(
            view_channel=True, send_messages=EVERYONE in write
        )
    else:
        result[everyone] = PermissionOverwrite(view_channel=False, send_messages=False)

    for name in read:
        if name == EVERYONE:
            continue
        role = roles.get(name)
        if role is not None:
            result[role] = PermissionOverwrite(view_channel=True)

    for name in write:
        if name == EVERYONE:
            continue
        role = roles.get(name)
        if role is not None:
            result[role] = PermissionOverwrite(view_channel=True, send_messages=True)

    # The bot always needs to be able to post where it is meant to post.
    bot_role = roles.get(BOT_ROLE)
    if bot_role is not None and BOT_ROLE in write:
        result[bot_role] = PermissionOverwrite(view_channel=True, send_messages=True)

    return result


def find_role(guild: discord.Guild, name: str) -> discord.Role | None:
    """The role with this name, if the server has one."""
    for role in guild.roles:
        if role.name == name:
            return role
    return None


def find_channel(guild: discord.Guild, name: str) -> discord.abc.GuildChannel | None:
    """The channel with this name, if the server has one.

    The match is exact, because Discord has both a #general and a #General
    here and they are not the same thing.
    """
    for channel in guild.channels:
        if channel.name == name:
            return channel
    return None


async def _ensure_roles(guild: discord.Guild) -> dict[str, discord.Role]:
    """Create the roles that are missing and put the permissions right."""
    roles: dict[str, discord.Role] = {}
    for spec in role_specs():
        existing = find_role(guild, spec.name)
        if existing is None:
            log.info("creating role %s", spec.name)
            existing = await guild.create_role(
                name=spec.name,
                colour=spec.colour,
                permissions=spec.permissions,
                hoist=spec.hoist,
                mentionable=spec.mentionable,
                reason="HoneyBeeSMP server setup",
            )
        elif existing.managed:
            # Discord owns the bot's role and will not let it be changed.
            log.info("leaving the managed role %s alone", spec.name)
        else:
            if existing.colour.value != spec.colour:
                await existing.edit(colour=spec.colour, reason="HoneyBeeSMP server setup")
            if existing.permissions != spec.permissions:
                await existing.edit(
                    permissions=spec.permissions, reason="HoneyBeeSMP server setup"
                )
            if existing.hoist != spec.hoist:
                await existing.edit(hoist=spec.hoist, reason="HoneyBeeSMP server setup")
        roles[spec.name] = existing

    # Put the roles in order, so the bot can hand out the roles below it.
    #
    # The bot's own role has to go up first: Discord will not let a role
    # be moved above the caller's highest role, and the bot's role starts
    # at the bottom. Once it is at the top the rest can be placed under it.
    top = len(ROLE_ORDER)
    bot_role = roles.get(BOT_ROLE)
    if bot_role is not None:
        try:
            await guild.edit_role_positions({bot_role: top}, reason="HoneyBeeSMP server setup")
        except discord.HTTPException as exc:
            log.warning("could not raise the bot's role: %s", exc)

    wanted = {}
    for position, name in enumerate(ROLE_ORDER, start=1):
        role = roles.get(name)
        if role is not None and role is not bot_role:
            wanted[role] = top - position + 1
    try:
        await guild.edit_role_positions(wanted, reason="HoneyBeeSMP server setup")
    except discord.HTTPException as exc:
        log.warning("could not reorder the roles: %s", exc)

    return roles


async def _adopt(guild: discord.Guild) -> None:
    """Rename the channels Discord made by default to the ones we want."""
    for channel in list(guild.channels):
        target = ADOPTED.get(channel.name)
        if target is None:
            continue
        kind, new_name = target
        if kind == "category" and isinstance(channel, discord.CategoryChannel):
            if channel.name != new_name:
                log.info("renaming category %s to %s", channel.name, new_name)
                await channel.edit(name=new_name, reason="HoneyBeeSMP server setup")
        elif kind == "text" and isinstance(channel, discord.TextChannel):
            if channel.name != new_name:
                log.info("renaming channel %s to %s", channel.name, new_name)
                await channel.edit(name=new_name, reason="HoneyBeeSMP server setup")
        elif kind == "voice" and isinstance(channel, discord.VoiceChannel):
            if channel.name != new_name:
                log.info("renaming voice channel %s to %s", channel.name, new_name)
                await channel.edit(name=new_name, reason="HoneyBeeSMP server setup")


def _same_overwrites(
    current: dict, wanted: dict[discord.Role, PermissionOverwrite]
) -> bool:
    """Whether the channel already has the overwrites we want."""
    current_by_id = {target.id: overwrite for target, overwrite in current.items()}
    wanted_by_id = {role.id: overwrite for role, overwrite in wanted.items()}
    if set(current_by_id) != set(wanted_by_id):
        return False
    return all(current_by_id[key] == wanted_by_id[key] for key in wanted_by_id)


SERVER_INFO = """**How to play on HoneyBeeSMP**

- **Server address:** `play.honeybeesmp.co.uk` (port `25566`)
- **Website:** https://honeybeesmp.co.uk
- **Discord:** https://discord.gg/TsBmAGPtMG
- **Server rules:** https://honeybeesmp.co.uk/rules

**Getting the modpack**

The server runs a modpack, so you need it installed before you join:

1. Install [Prism Launcher](https://prismlauncher.org) or the
   [Modrinth App](https://modrinth.com/app).
2. Point it at [HoneyBeeSMP on
   Modrinth](https://modrinth.com/server/honeybeesmp) and install it.
3. Launch the profile it creates and connect.

The launcher keeps the pack up to date for you.

**In game**

The server is Create and automation focused, with a custom world, claims
and parties, and proximity voice chat.

Open the map with `M` and claim the chunks where you build. A claim stops
other players from breaking your build, and it can be expanded later.
"""


async def _post(channel: discord.abc.GuildChannel | None, text: str, label: str) -> None:
    """Put a message in a channel, or update the one that is already there."""
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        messages = [m async for m in channel.history(limit=50)]
    except discord.HTTPException as exc:
        log.warning("could not read the %s channel: %s", label, exc)
        return
    for message in messages:
        if message.author.id == channel.guild.me.id:
            if message.content != text:
                await message.edit(content=text)
                log.info("updated the %s", label)
            return
    await channel.send(text)
    log.info("posted the %s", label)


async def _post_rules(guild: discord.Guild) -> None:
    """Put the rules in the rules channel."""
    await _post(find_channel(guild, "rules"), RULES, "rules")


async def _post_server_info(guild: discord.Guild) -> None:
    """Put the joining instructions in the server-info channel."""
    await _post(find_channel(guild, "server-info"), SERVER_INFO, "server info")


async def _remove_channels(guild: discord.Guild) -> None:
    """Delete the channels that are not part of the layout any more."""
    for name in REMOVED:
        channel = find_channel(guild, name)
        if channel is None:
            continue
        log.info("removing the channel #%s", name)
        await channel.delete(reason="HoneyBeeSMP server setup")


def _kind_matches(channel: discord.abc.GuildChannel, kind: str) -> bool:
    """Whether the channel is the kind the layout wants."""
    if kind == "voice":
        return isinstance(channel, discord.VoiceChannel)
    if kind == "forum":
        return isinstance(channel, discord.ForumChannel)
    return isinstance(channel, discord.TextChannel)


async def apply_setup(guild: discord.Guild) -> dict[str, discord.Role]:
    """Make the server look the way it is meant to look."""
    await _adopt(guild)
    roles = await _ensure_roles(guild)

    categories = {
        channel.name: channel
        for channel in guild.channels
        if isinstance(channel, discord.CategoryChannel)
    }

    for spec in category_specs():
        # A category holds the channels, so it needs the same view rules:
        # if the category is hidden, its channels are too.
        everyone_can_see = any(EVERYONE in c.read for c in spec.channels)
        anyone_can_write = any(EVERYONE in c.write for c in spec.channels)

        category = categories.get(spec.name)
        category_overwrites = _overwrites(
            guild,
            roles,
            (EVERYONE,) if everyone_can_see else STAFF_ROLES,
            (EVERYONE,) if anyone_can_write else STAFF_ROLES,
        )

        if category is None:
            log.info("creating category %s", spec.name)
            category = await guild.create_category(
                name=spec.name,
                overwrites=category_overwrites,
                reason="HoneyBeeSMP server setup",
            )
        else:
            if not _same_overwrites(category.overwrites, category_overwrites):
                await category.edit(
                    overwrites=category_overwrites, reason="HoneyBeeSMP server setup"
                )
        categories[spec.name] = category

        for channel_spec in spec.channels:
            overwrites = _overwrites(
                guild, roles, channel_spec.read, channel_spec.write
            )
            existing = find_channel(guild, channel_spec.name)

            if existing is not None and not _kind_matches(existing, channel_spec.kind):
                # Discord cannot turn a channel into a different kind of
                # channel, so it has to be made again.
                log.info(
                    "replacing the %s channel %s", existing.type, channel_spec.name
                )
                await existing.delete(reason="HoneyBeeSMP server setup")
                existing = None

            if existing is None:
                log.info("creating %s channel %s", channel_spec.kind, channel_spec.name)
                if channel_spec.kind == "voice":
                    await guild.create_voice_channel(
                        channel_spec.name,
                        category=category,
                        overwrites=overwrites,
                        reason="HoneyBeeSMP server setup",
                    )
                elif channel_spec.kind == "forum":
                    await guild.create_forum(
                        channel_spec.name,
                        topic=channel_spec.topic,
                        category=category,
                        overwrites=overwrites,
                        available_tags=[
                            discord.ForumTag(name=tag) for tag in channel_spec.tags
                        ],
                        reason="HoneyBeeSMP server setup",
                    )
                else:
                    await guild.create_text_channel(
                        channel_spec.name,
                        category=category,
                        topic=channel_spec.topic,
                        overwrites=overwrites,
                        reason="HoneyBeeSMP server setup",
                    )
                continue

            if isinstance(existing, discord.CategoryChannel):
                continue
            if existing.category_id != category.id:
                await existing.edit(
                    category=category, reason="HoneyBeeSMP server setup"
                )
            if not _same_overwrites(existing.overwrites, overwrites):
                await existing.edit(
                    overwrites=overwrites, reason="HoneyBeeSMP server setup"
                )
            if (
                isinstance(existing, (discord.TextChannel, discord.ForumChannel))
                and existing.topic != channel_spec.topic
            ):
                await existing.edit(
                    topic=channel_spec.topic, reason="HoneyBeeSMP server setup"
                )

    await _remove_channels(guild)
    await _post_rules(guild)
    await _post_server_info(guild)

    return roles
