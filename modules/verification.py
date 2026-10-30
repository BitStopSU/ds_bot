import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from utils import get_log_channel_id, is_branch_staff


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Открыть панель верификации")
    async def verify(self, interaction: discord.Interaction, user: discord.Member):
        if not is_branch_staff(interaction.user, "support"):
            await interaction.response.send_message("❌ Только ветка Support.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("❌ Это бот.", ephemeral=True)
            return

        db_user = await self.bot.db.get_user(user.id)
        joins = await self.bot.db.count_join_events(user.id, "join")
        age = (datetime.now(timezone.utc) - user.created_at).days

        embed = discord.Embed(
            title="🔍 Панель верификации",
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
        embed.add_field(name="Ник", value=f"`{user}`", inline=True)
        embed.add_field(name="Возраст аккаунта", value=f"{age} дн.", inline=True)
        embed.add_field(name="Заходов", value=str(joins), inline=True)
        embed.add_field(name="Первый вход", value=db_user["first_joined_at"] if db_user else "—", inline=True)
        embed.add_field(name="Статус", value=db_user["verify_status"] if db_user else "—", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Запросил: {interaction.user}")

        await interaction.response.send_message(embed=embed, view=VerifyView(self.bot, user))


class VerifyView(discord.ui.View):
    def __init__(self, bot, target: discord.Member):
        super().__init__(timeout=None)
        self.bot = bot
        self.target = target

    async def _ok(self, interaction):
        return is_branch_staff(interaction.user, "support")

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ok(interaction):
            await interaction.response.send_message("❌ Только Support.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(self.target.id)
        if not member:
            await interaction.response.send_message("❌ Ушёл с сервера.", ephemeral=True)
            return
        try:
            unv = int(await self.bot.db.get_setting("role_unverified") or 0)
            den = int(await self.bot.db.get_setting("role_denied") or 0)
            ver = int(await self.bot.db.get_setting("role_verified") or 0)
            if unv:
                await member.remove_roles(discord.Object(id=unv))
            if den:
                await member.remove_roles(discord.Object(id=den))
            if ver:
                await member.add_roles(discord.Object(id=ver), reason="Верификация")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await self.bot.db.set_verify_status(self.target.id, "approved", interaction.user.id)
        ch = self.bot.get_channel(get_log_channel_id("support"))
        if ch:
            await ch.send(f"✅ {self.target.mention} одобрен — {interaction.user.mention}")
        await interaction.response.edit_message(
            content=f"✅ {self.target.mention} одобрен", embed=None, view=None
        )
        self.stop()

    @discord.ui.button(label="❌ Не допуск", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ok(interaction):
            await interaction.response.send_message("❌ Только Support.", ephemeral=True)
            return
        await interaction.response.send_modal(DenyModal(self.bot, self.target, self))


class DenyModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Причина", style=discord.TextStyle.paragraph, required=True, max_length=500
    )

    def __init__(self, bot, target, view):
        super().__init__()
        self.bot = bot
        self.target = target
        self.parent = view

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = guild.get_member(self.target.id)
        if not member:
            await interaction.response.send_message("❌ Ушёл.", ephemeral=True)
            return
        try:
            unv = int(await self.bot.db.get_setting("role_unverified") or 0)
            den = int(await self.bot.db.get_setting("role_denied") or 0)
            if unv:
                await member.remove_roles(discord.Object(id=unv))
            if den:
                await member.add_roles(discord.Object(id=den), reason=self.reason.value)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await self.bot.db.set_verify_status(self.target.id, "denied", interaction.user.id)
        ch = self.bot.get_channel(get_log_channel_id("support"))
        if ch:
            await ch.send(
                f"❌ {self.target.mention} не допущен — {interaction.user.mention}\nПричина: {self.reason.value}"
            )
        await interaction.response.edit_message(
            content=f"❌ {self.target.mention} не допущен. Причина: {self.reason.value}",
            embed=None,
            view=None,
        )
        self.parent.stop()


async def setup(bot):
    await bot.add_cog(Verification(bot))
