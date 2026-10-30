import discord
from discord.ext import commands, tasks
from datetime import datetime
from zoneinfo import ZoneInfo

import config


class AIAnalysis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.weekly.start()

    def cog_unload(self):
        self.weekly.cancel()

    @tasks.loop(minutes=1)
    async def weekly(self):
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            key = f"last_ai_report_{now.date()}"
            if await self.bot.db.get_setting(key):
                return
            await self.bot.db.set_setting(key, "1")
            await self.send_report()

    @weekly.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    async def send_report(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        lines = ["📊 **Еженедельный отчёт**\n"]
        for branch, label in (("support", "Support"), ("mod", "Moderator"), ("event", "Eventer")):
            names = [f"{label} | {rank}" for rank in ("Staff", "Master", "Curator", "Admin")]
            members = set()
            for name in names:
                role = discord.utils.get(guild.roles, name=name)
                if role:
                    members.update(member for member in role.members if not member.bot)
            quota = await self.bot.db.get_quota(branch, "staff") or 10.0
            bad = []
            for member in members:
                hours = await self.bot.db.get_week_hours(member.id)
                if hours < quota:
                    bad.append((member, hours))
            if bad:
                lines.append(f"\n**{label}: недобор ПТ** ({len(bad)}):")
                for member, hours in sorted(bad, key=lambda x: x[1])[:5]:
                    lines.append(f"• {member.mention} — {hours:.1f}ч / {quota:.0f}ч")
        cur = await self.bot.db.conn.execute(
            """SELECT target_id, COUNT(*) as c FROM reports WHERE target_id IS NOT NULL
               AND created_at >= datetime('now', '-7 days') GROUP BY target_id ORDER BY c DESC LIMIT 5"""
        )
        rows = await cur.fetchall()
        if rows:
            lines.append("\n**Топ по репортам за неделю:**")
            lines.extend(f"• <@{row['target_id']}> — {row['c']} репортов" for row in rows)
        cur = await self.bot.db.conn.execute(
            """SELECT discord_id, SUM(duration_sec) as total FROM voice_sessions
               WHERE joined_at >= datetime('now', '-1 day') GROUP BY discord_id HAVING total > 43200"""
        )
        anomalies = await cur.fetchall()
        if anomalies:
            lines.append("\n**⚠️ Аномалии (>12ч в войсе за сутки):**")
            lines.extend(f"• <@{row['discord_id']}> — {row['total']/3600:.1f}ч" for row in anomalies)
        report_text = "\n".join(lines)
        recipients = set()
        owner = guild.get_member(guild.owner_id)
        if owner:
            recipients.add(owner)
        owner_role = discord.utils.get(guild.roles, name="Owner")
        if owner_role:
            recipients.update(member for member in owner_role.members if not member.bot)
        for label in ("Support", "Moderator", "Eventer"):
            for rank in ("Admin", "Curator"):
                role = discord.utils.get(guild.roles, name=f"{label} | {rank}")
                if role:
                    recipients.update(member for member in role.members if not member.bot)
        for recipient in recipients:
            try:
                await recipient.send(report_text[:1900])
            except Exception:
                pass
        ch = guild.get_channel(int(await self.bot.db.get_setting("channel_coder_log") or 0))
        if ch:
            await ch.send(report_text[:1900])


async def setup(bot):
    await bot.add_cog(AIAnalysis(bot))
