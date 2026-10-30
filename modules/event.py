import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils import is_owner, is_branch_master_plus


class Event(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="event-mode", description="Включить/выключить режим ивента")
    @app_commands.choices(action=[
        app_commands.Choice(name="Включить", value="on"),
        app_commands.Choice(name="Выключить", value="off"),
        app_commands.Choice(name="Статус", value="status"),
    ])
    async def event_mode(self, interaction: discord.Interaction, action: str):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "event"):
            await interaction.response.send_message("❌ Только Eventer master+ / владелец.", ephemeral=True)
            return
        if action == "status":
            value = await self.bot.db.get_setting("event_mode_active")
            started = await self.bot.db.get_setting("event_mode_started_by")
            if value == "1":
                await interaction.response.send_message(f"🎉 Event Mode **активен**\nЗапустил: <@{started}>", ephemeral=True)
            else:
                await interaction.response.send_message("💤 Event Mode **выключен**.", ephemeral=True)
            return
        if action == "on":
            await self.bot.db.set_setting("event_mode_active", "1")
            await self.bot.db.set_setting("event_mode_started_by", str(interaction.user.id))
            await self.bot.db.set_setting("event_mode_started_at", datetime.utcnow().isoformat())
            await interaction.response.send_message("🎉 **Event Mode включён.**\nНа время ивента бот может ограничивать владельца в ивент-каналах.", ephemeral=True)
        else:
            await self.bot.db.set_setting("event_mode_active", "0")
            await interaction.response.send_message("💤 Event Mode **выключен**.", ephemeral=True)
        ch_id = int(await self.bot.db.get_setting("channel_event_log") or 0)
        ch = interaction.guild.get_channel(ch_id)
        if ch:
            await ch.send(f"{'🎉' if action == 'on' else '💤'} Event Mode **{'включён' if action == 'on' else 'выключен'}** — {interaction.user.mention}")


async def setup(bot):
    await bot.add_cog(Event(bot))
