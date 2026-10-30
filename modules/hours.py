import discord
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

import config

BRANCH_LABELS = {"support": "Support", "mod": "Moderator", "event": "Eventer"}
VOICE_CAT_KEY = {"support": "vcat_voice_support", "mod": "vcat_voice_mod", "event": "vcat_voice_event"}


class Hours(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_report.start()

    def cog_unload(self):
        self.weekly_report.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        open_sessions = await self.bot.db.get_open_voice_sessions()
        for session in open_sessions:
            await self.bot.db.end_voice_session(session["discord_id"])
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        cat_map = {}
        for branch, key in VOICE_CAT_KEY.items():
            cid = int(await self.bot.db.get_setting(key) or 0)
            if cid:
                cat_map[cid] = branch
        for channel in guild.voice_channels:
            if channel.category_id in cat_map:
                for member in channel.members:
                    if not member.bot:
                        await self.bot.db.start_voice_session(member.id, channel.id, cat_map[channel.category_id])

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        cat_map = {}
        for branch, key in VOICE_CAT_KEY.items():
            cid = int(await self.bot.db.get_setting(key) or 0)
            if cid:
                cat_map[cid] = branch
        was_tracked = before.channel and before.channel.category_id in cat_map
        now_tracked = after.channel and after.channel.category_id in cat_map
        afk_id = after.guild.afk_channel.id if after.guild.afk_channel else 0
        if was_tracked and not now_tracked:
            await self.bot.db.end_voice_session(member.id)
        elif not was_tracked and now_tracked:
            if after.channel.id != afk_id:
                await self.bot.db.start_voice_session(member.id, after.channel.id, cat_map[after.channel.category_id])
        elif was_tracked and now_tracked:
            if before.channel.id != after.channel.id and after.channel.id == afk_id:
                await self.bot.db.end_voice_session(member.id)
            elif before.channel.id == afk_id and after.channel.id != afk_id:
                await self.bot.db.start_voice_session(member.id, after.channel.id, cat_map[after.channel.category_id])

    @tasks.loop(minutes=1)
    async def weekly_report(self):
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            key = f"last_weekly_report_{now.date()}"
            if await self.bot.db.get_setting(key):
                return
            await self.bot.db.set_setting(key, "1")
            await self.send_reports()

    @weekly_report.before_loop
    async def before_weekly(self):
        await self.bot.wait_until_ready()

    async def send_reports(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        for bkey, label in BRANCH_LABELS.items():
            role = discord.utils.get(guild.roles, name=f"{label} | Staff")
            if not role:
                continue
            members = [member for member in role.members if not member.bot]
            for rank in ("Master", "Curator", "Admin"):
                role = discord.utils.get(guild.roles, name=f"{label} | {rank}")
                if role:
                    members.extend([m for m in role.members if not m.bot and m not in members])
            quota = await self.bot.db.get_quota(bkey, "staff")
            if quota == 0:
                quota = 10.0
            lines = []
            for member in members:
                hours = await self.bot.db.get_week_hours(member.id)
                if hours < quota:
                    lines.append(f"{member.mention} — {hours:.1f}ч / {quota:.0f}ч (недобор {quota - hours:.1f}ч)")
            if not lines:
                continue
            admins = []
            for rank in ("Admin", "Curator"):
                role = discord.utils.get(guild.roles, name=f"{label} | {rank}")
                if role:
                    admins.extend([m for m in role.members if not m.bot])
            owner_role = discord.utils.get(guild.roles, name="Owner")
            if owner_role:
                admins.extend([m for m in owner_role.members if not m.bot])
            owner = guild.get_member(guild.owner_id)
            if owner:
                admins.append(owner)
            text = f"⚠️ **{label}: недобор ПТ**\n\n" + "\n".join(lines)
            seen = set()
            for admin in admins:
                if admin.id not in seen:
                    seen.add(admin.id)
                    try:
                        await admin.send(text)
                    except Exception:
                        pass


async def setup(bot):
    await bot.add_cog(Hours(bot))
