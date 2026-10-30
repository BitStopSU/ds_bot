import discord
from discord import app_commands
from discord.ext import commands

from utils import is_owner, is_branch_admin, is_branch_master_plus


class Branch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="branch", description="Структура ветки")
    @app_commands.choices(branch=[
        app_commands.Choice(name="Support", value="support"),
        app_commands.Choice(name="Moderator", value="mod"),
        app_commands.Choice(name="Eventer", value="event"),
    ])
    async def branch(self, interaction: discord.Interaction, branch: str):
        if not is_owner(interaction.user):
            if not is_branch_admin(interaction.user, branch) and not is_branch_master_plus(interaction.user, branch):
                await interaction.response.send_message("❌ Только master+ этой ветки.", ephemeral=True)
                return
        guild = interaction.guild
        labels = {"support": "Support", "mod": "Moderator", "event": "Eventer"}
        embed = discord.Embed(title=f"🏛️ Ветка {labels[branch]}", color=discord.Color.blurple())
        for rkey, rlabel in (("admin", "👑 Админ"), ("curator", "🎩 Куратор"),
                             ("master", "⭐ Мастер"), ("staff", "👤 Сотрудник")):
            role = discord.utils.get(guild.roles, name=f"{labels[branch]} | {rkey.capitalize()}")
            if role:
                members = [m.mention for m in role.members if not m.bot]
                embed.add_field(name=f"{rlabel} ({len(members)})", value="\n".join(members) if members else "— пусто —", inline=False)
        embed.set_footer(text=f"Запросил: {interaction.user}")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Branch(bot))
