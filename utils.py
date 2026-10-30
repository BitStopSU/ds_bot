import discord
import config


def role_names(member: discord.Member) -> set[str]:
    return {r.name for r in member.roles}


def is_owner(member: discord.Member) -> bool:
    if member.id == member.guild.owner_id:
        return True
    return "Owner" in role_names(member)


def is_branch_staff(member: discord.Member, branch_key: str) -> bool:
    bn = {"support": "Support", "mod": "Moderator", "event": "Eventer"}[branch_key]
    names = role_names(member)
    return any(f"{bn} | {r}" in names for r in ("Admin", "Curator", "Master", "Staff"))


def is_branch_master_plus(member: discord.Member, branch_key: str) -> bool:
    bn = {"support": "Support", "mod": "Moderator", "event": "Eventer"}[branch_key]
    names = role_names(member)
    return any(f"{bn} | {r}" in names for r in ("Admin", "Curator", "Master"))


def is_branch_admin(member: discord.Member, branch_key: str) -> bool:
    bn = {"support": "Support", "mod": "Moderator", "event": "Eventer"}[branch_key]
    return f"{bn} | Admin" in role_names(member)


def get_log_channel_id(branch: str) -> int:
    return {
        "support": config.CHANNEL_SUPPORT_LOG,
        "mod": config.CHANNEL_MOD_LOG,
        "event": config.CHANNEL_EVENT_LOG,
    }.get(branch, config.CHANNEL_ADMIN_LOG)
