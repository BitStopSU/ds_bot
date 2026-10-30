import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils import is_owner, is_branch_master_plus


class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="report", description="Оставить репорт")
    @app_commands.choices(category=[
        app_commands.Choice(name="Нарушение (на человека)", value="person"),
        app_commands.Choice(name="Жалоба на модератора", value="mod"),
        app_commands.Choice(name="Жалоба на саппорта", value="support"),
        app_commands.Choice(name="Жалоба на ивентера", value="event"),
        app_commands.Choice(name="Баг бота", value="bug"),
        app_commands.Choice(name="Другое", value="other"),
    ])
    async def report(self, interaction: discord.Interaction, category: str, target: discord.Member = None):
        if target and target.bot and category != "bug":
            await interaction.response.send_message("❌ Ботов можно только в категории «Баг».", ephemeral=True)
            return
        if category == "bug" and target:
            await interaction.response.send_message("❌ Для бага не указывай юзера.", ephemeral=True)
            return
        await interaction.response.send_modal(ReportModal(self.bot, category, target, interaction.guild))


class ReportModal(discord.ui.Modal, title="Репорт"):
    description = discord.ui.TextInput(label="Описание", style=discord.TextStyle.paragraph, required=True, max_length=1500)
    evidence = discord.ui.TextInput(label="Доказательства (ссылка на скрин)", required=False, max_length=300)

    def __init__(self, bot, category, target, guild):
        super().__init__()
        self.bot, self.category, self.target, self.guild = bot, category, target, guild

    async def on_submit(self, interaction: discord.Interaction):
        rid = await self.bot.db.add_report(interaction.user.id, self.category,
                                           self.target.id if self.target else None,
                                           self.description.value, self.evidence.value)
        route = {
            "person": ("channel_mod_log", "mod"), "mod": ("channel_mod_log", "mod"),
            "support": ("channel_support_log", "support"), "event": ("channel_event_log", "event"),
            "bug": ("channel_coder_log", None), "other": ("channel_support_log", "support"),
        }
        ch_key, branch = route[self.category]
        ch = self.guild.get_channel(int(await self.bot.db.get_setting(ch_key) or 0))
        embed = discord.Embed(title=f"🚨 Репорт #{rid} — {self.category}",
                              color=discord.Color.red() if self.category != "bug" else discord.Color.orange(),
                              timestamp=datetime.utcnow())
        embed.add_field(name="Автор", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=False)
        if self.target:
            embed.add_field(name="На кого", value=f"{self.target.mention}\n`{self.target.id}`", inline=False)
        embed.add_field(name="Описание", value=self.description.value, inline=False)
        if self.evidence.value:
            embed.add_field(name="Доказательства", value=self.evidence.value, inline=False)
        view = ReportView(self.bot, rid, interaction.user, self.category, branch)
        if ch:
            await ch.send(embed=embed, view=view)
        if branch:
            label = {"mod": "Moderator", "support": "Support", "event": "Eventer"}[branch]
            for rank in ("Admin", "Curator"):
                role = discord.utils.get(self.guild.roles, name=f"{label} | {rank}")
                if role:
                    for member in role.members:
                        if not member.bot:
                            try:
                                await member.send(f"🚨 Новый репорт #{rid} в канале {ch.mention if ch else '—'}")
                            except Exception:
                                pass
        await interaction.response.send_message(f"✅ Репорт #{rid} отправлен.", ephemeral=True)


class ReportView(discord.ui.View):
    def __init__(self, bot, rid, author, category, branch):
        super().__init__(timeout=None)
        self.bot, self.rid, self.author = bot, rid, author
        self.category, self.branch = category, branch

    async def _can(self, interaction):
        if is_owner(interaction.user):
            return True
        if self.category == "bug" or not self.branch:
            return False
        return is_branch_master_plus(interaction.user, self.branch)

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="rp_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._can(interaction):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await self.bot.db.set_report_status(self.rid, "accepted", interaction.user.id)
        try:
            await self.author.send(f"✅ Твой репорт #{self.rid} принят.")
        except Exception:
            pass
        await interaction.response.edit_message(content=f"✅ Репорт #{self.rid} принят ({interaction.user.mention})", embed=None, view=None)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="rp_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._can(interaction):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await interaction.response.send_modal(RejectReportModal(self.bot, self.rid, self.author))


class RejectReportModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, bot, rid, author):
        super().__init__()
        self.bot, self.rid, self.author = bot, rid, author

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.set_report_status(self.rid, "rejected", interaction.user.id)
        try:
            await self.author.send(f"❌ Твой репорт #{self.rid} отклонён.\nПричина: {self.reason.value}")
        except Exception:
            pass
        await interaction.response.edit_message(content=f"❌ Репорт #{self.rid} отклонён. {self.reason.value}", embed=None, view=None)


async def setup(bot):
    await bot.add_cog(Reports(bot))
