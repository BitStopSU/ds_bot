import discord
from discord import app_commands
from discord.ext import commands

from utils import is_branch_master_plus, is_owner


class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Мой профиль")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        if target.bot:
            await interaction.response.send_message("❌ Бот.", ephemeral=True)
            return
        db = await self.bot.db.get_user(target.id)
        hours = await self.bot.db.get_week_hours(target.id)
        embed = discord.Embed(title=f"👤 {target}", color=discord.Color.blurple())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Часов за неделю", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Первый вход", value=db["first_joined_at"] if db else "—", inline=True)
        embed.add_field(name="Статус", value=db["verify_status"] if db else "—", inline=True)
        await interaction.response.send_message(embed=embed, view=ProfileView(self.bot, target))

    @app_commands.command(name="staff-profile", description="Профиль стаффа")
    async def staff_profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        if target.id != interaction.user.id and not is_owner(interaction.user):
            if not any(is_branch_master_plus(interaction.user, b) for b in ("support", "mod", "event")):
                await interaction.response.send_message("❌ Только master+ смотрит чужие.", ephemeral=True)
                return
        branches = await self.bot.db.get_staff_branches(target.id)
        if not branches:
            await interaction.response.send_message("❌ Не стафф.", ephemeral=True)
            return
        hours = await self.bot.db.get_week_hours(target.id)
        warns = await self.bot.db.count_active_warns(target.id)
        embed = discord.Embed(title=f"🛡️ Стафф-профиль: {target}", color=discord.Color.gold())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Часов за неделю", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Активных варнов", value=str(warns), inline=True)
        for branch in branches:
            embed.add_field(name=f"Ветка {branch['branch']}", value=f"Ранг: {branch['rank']}\nС {branch['joined_branch_at']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="event-profile", description="Ивент-профиль (игры)")
    async def event_profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        embed = discord.Embed(title=f"🎮 Ивент-профиль: {target}", color=discord.Color.purple())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.description = "Пока пусто. Скоро здесь будут игры и скрины (Dota2, CS2, Valorant)."
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ProfileView(discord.ui.View):
    def __init__(self, bot, target):
        super().__init__(timeout=300)
        self.bot, self.target = bot, target

    @discord.ui.button(label="Профиль", style=discord.ButtonStyle.primary, custom_id="p_main")
    async def main_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        hours = await self.bot.db.get_week_hours(self.target.id)
        db = await self.bot.db.get_user(self.target.id)
        embed = discord.Embed(title=f"👤 {self.target}", color=discord.Color.blurple())
        embed.set_thumbnail(url=self.target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{self.target.id}`", inline=True)
        embed.add_field(name="Часов за неделю", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Первый вход", value=db["first_joined_at"] if db else "—", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Стафф", style=discord.ButtonStyle.success, custom_id="p_staff")
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        branches = await self.bot.db.get_staff_branches(self.target.id)
        if not branches:
            await interaction.response.send_message("❌ Не стафф.", ephemeral=True)
            return
        if interaction.user.id != self.target.id and not is_owner(interaction.user):
            if not any(is_branch_master_plus(interaction.user, b) for b in ("support", "mod", "event")):
                await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
                return
        hours = await self.bot.db.get_week_hours(self.target.id)
        warns = await self.bot.db.count_active_warns(self.target.id)
        embed = discord.Embed(title=f"🛡️ Стафф: {self.target}", color=discord.Color.gold())
        embed.add_field(name="Часов за неделю", value=f"{hours:.1f}", inline=True)
        embed.add_field(name="Варнов", value=str(warns), inline=True)
        for branch in branches:
            embed.add_field(name=branch["branch"], value=f"Ранг: {branch['rank']}", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Ивент", style=discord.ButtonStyle.secondary, custom_id="p_event")
    async def event_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title=f"🎮 Ивент: {self.target}", color=discord.Color.purple())
        embed.description = "Пока пусто."
        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot):
    await bot.add_cog(Profiles(bot))
