from typing import List, Union

from cassandra.cqlengine import query

from .database import (
    Guild,
    GuildChannel,
    Member,
    Message,
    PermissionOverWrites,
    Role,
    User,
)
from .errors import BadData, Forbidden, NotFound
from .flags import GuildPermissions, UserFlags
from .randoms import get_bucket
from .tokens import verify_token


def valid_session(token: str) -> User:
    return verify_token(token=token)


def validate_user(token: str, stop_bots: bool = False) -> User:
    user = valid_session(token=token)

    if stop_bots:
        if user.bot:
            raise Forbidden()

    return user


def validate_member(
    token: str, guild_id: int, *, stop_bots: bool = False
) -> tuple[Member, User]:
    user = validate_user(token=token)
    objs = Member.objects(Member.id == user.id, Member.guild_id == guild_id)

    try:
        member: Member = objs.get()
    except (query.DoesNotExist):
        raise Forbidden()

    return member, user


def validate_admin(token: str):
    admin = validate_user(token=token)

    flags = UserFlags(admin.flags)

    if not flags.staff:
        raise Forbidden()

    return admin


def validate_channel(
    token: str,
    guild_id: int,
    channel_id: int,
    permission: str,
    *,
    stop_bots: bool = False
) -> tuple[Member, User, GuildChannel]:
    member, user = validate_member(token=token, guild_id=guild_id, stop_bots=stop_bots)

    try:
        channel: GuildChannel = GuildChannel.objects(
            id=channel_id, guild_id=guild_id
        ).get()
    except (query.DoesNotExist):
        raise NotFound()

    if member.owner:
        return member, user, channel

    user_found = False
    for overwrite in channel.permission_overwrites:
        assert isinstance(overwrite, PermissionOverWrites)

        if overwrite.id == user.id:
            user_found = True
            allow_permissions = GuildPermissions(overwrite.allow)
            disallow_permissions = GuildPermissions(overwrite.deny)
            break

    if not user_found:
        if list(member.roles) == []:
            guild: Guild = Guild.objects(Guild.id == guild_id).get()
            permissions = GuildPermissions(guild.permissions)
        else:
            role_id: int = list(member.roles)[0]

            role: Role = Role.objects(role_id).get()

            permissions = GuildPermissions(role.permissions)

        if permissions.administator:
            return member, user, channel

        if not getattr(permissions, permission):
            raise Forbidden()

        return member, user, channel
    else:
        if getattr(disallow_permissions, permission):
            raise Forbidden()

        if not getattr(allow_permissions, permission):
            raise Forbidden()

        return member, user, channel


def search_messages(
    channel_id: int, message_id: int = None, limit: int = 50
) -> Union[List[Message], Message, None]:
    current_bucket = get_bucket(channel_id)
    collected_messages = []
    if message_id is None:
        for bucket in range(current_bucket):
            msgs = (
                Message.objects(
                    Message.channel_id == channel_id, Message.bucket_id == bucket
                )
                .limit(limit)
                .order_by('-id')
            )

            msgs = msgs.all()

            collected_messages.append(msgs)

            if len(collected_messages) > limit:
                collected_messages = collected_messages[limit:]
                break

        return collected_messages
    else:
        for bucket in range(current_bucket):
            pmsg = Message.objects(
                Message.id == message_id,
                Message.channel_id == channel_id,
                Message.bucket_id == bucket,
            )

            try:
                msg = pmsg.get()
            except:
                pass
            else:
                return msg


def verify_parent_id(parent: int, guild_id: int) -> GuildChannel:
    channel: GuildChannel = GuildChannel.objects(
        GuildChannel.id == parent, GuildChannel.guild_id == guild_id
    )

    try:
        channel: GuildChannel = channel.get()
    except (query.DoesNotExist):
        raise BadData()

    return channel


def verify_channel_position(pos: int, guild_id: int):
    guild_channels: List[GuildChannel] = GuildChannel.objects(
        GuildChannel.guild_id == guild_id
    ).all()

    highest_pos = 0
    for channel in guild_channels:
        if channel.position > highest_pos:
            highest_pos = channel.position

    if pos != highest_pos + 1:
        # this might be prone to error...
        raise BadData()

    del highest_pos
    del guild_channels
