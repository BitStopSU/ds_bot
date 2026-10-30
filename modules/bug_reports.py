import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime


class BugReports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bug", description="Сообщить об ошибке бота")
    async def bug(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BugModal(self.bot))


class BugModal(discord.ui.Modal, title="Баг-репорт"):
    title_ = discord.ui.TextInput(label="Кратко", required=True, max_length=100)
    description = discord.ui.TextInput(label="Что произошло", style=discord.TextStyle.paragraph, required=True, max_length=1500)
    command = discord.ui.TextInput(label="Команда / шаги", required=False, max_length=200)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        rid = await self.bot.db.add_report(
            interaction.user.id, "bug", None,
            f"{self.title_.value}\n\n{self.description.value}\n\nШаги: {self.command.value or '—'}", None
        )
        ch = interaction.guild.get_channel(int(await self.bot.db.get_setting("channel_coder_log") or 0))
        if not ch:
            await interaction.response.send_message("❌ Канал coder-log не настроен.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🐛 Баг #{rid}", color=discord.Color.orange(), timestamp=datetime.utcnow())
        embed.add_field(name="Автор", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=False)
        embed.add_field(name="Кратко", value=self.title_.value, inline=False)
        embed.add_field(name="Описание", value=self.description.value, inline=False)
        embed.add_field(name="Шаги", value=self.command.value or "—", inline=False)
        await ch.send(embed=embed)
        await interaction.response.send_message(f"✅ Баг #{rid} отправлен код-каналу.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(BugReports(bot))
