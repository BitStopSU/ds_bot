import discord
from discord import app_commands
from discord.ext import commands

from utils import role_names


class SwitchBranch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="switch-branch", description="Выбрать активную ветку (если ты в нескольких)")
    async def switch(self, interaction: discord.Interaction):
        names = role_names(interaction.user)
        available = []
        if "Support | Admin" in names:
            available.append(("support", "Support"))
        if "Moderator | Admin" in names:
            available.append(("mod", "Moderator"))
        if "Eventer | Admin" in names:
            available.append(("event", "Eventer"))
        if not available:
            await interaction.response.send_message("❌ У тебя нет админ-ролей веток.", ephemeral=True)
            return
        current = await self.bot.db.get_active_branch(interaction.user.id)
        await interaction.response.send_message(
            f"Текущая активная ветка: **{current or 'не выбрана'}**",
            view=BranchSelectView(self.bot, available, current), ephemeral=True
        )


class BranchSelectView(discord.ui.View):
    def __init__(self, bot, available, current):
        super().__init__(timeout=60)
        self.bot = bot
        for key, label in available:
            button = discord.ui.Button(label=label,
                                       style=discord.ButtonStyle.success if current == key else discord.ButtonStyle.primary,
                                       custom_id=f"sw_{key}")
            button.callback = self._make(key, label)
            self.add_item(button)

    def _make(self, key, label):
        async def callback(interaction: discord.Interaction):
            await self.bot.db.set_active_branch(interaction.user.id, key)
            await interaction.response.send_message(f"✅ Активная ветка: **{label}**", ephemeral=True)
        return callback


async def setup(bot):
    await bot.add_cog(SwitchBranch(bot))
