import discord
from discord import app_commands
from discord.ext import commands

from utils import is_owner, is_branch_master_plus


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="money", description="Мой баланс")
    async def money(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        cur = await self.bot.db.conn.execute("SELECT balance FROM currency WHERE discord_id=?", (target.id,))
        row = await cur.fetchone()
        balance = row["balance"] if row else 0
        await interaction.response.send_message(f"💰 {target.mention}: **{balance}** монет", ephemeral=True)

    @app_commands.command(name="shop", description="Магазин сервера")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛒 Магазин", description="Скоро здесь появятся роли и картинки на профиль.", color=discord.Color.gold())
        embed.add_field(name="В разработке", value="Экономика запустится позже.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add-money", description="Начислить монеты (admin)")
    async def add_money(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "mod"):
            await interaction.response.send_message("❌ Только master+ / владелец.", ephemeral=True)
            return
        if amount == 0:
            await interaction.response.send_message("❌ 0 нельзя.", ephemeral=True)
            return
        await self.bot.db.conn.execute(
            """INSERT INTO currency(discord_id, balance, total_earned) VALUES (?, ?, ?)
               ON CONFLICT(discord_id) DO UPDATE SET balance=balance+excluded.balance,
               total_earned=total_earned+excluded.total_earned""", (user.id, max(0, amount), max(0, amount))
        )
        await self.bot.db.conn.commit()
        await interaction.response.send_message(
            f"💰 {user.mention}: {'+' if amount > 0 else ''}{amount} монет. Причина: {reason}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Economy(bot))
