import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone

import config
from utils import is_owner, is_branch_staff, is_branch_master_plus


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mute_check.start()

    def cog_unload(self):
        self.mute_check.cancel()

    @app_commands.command(name="action", description="Выдать наказание")
    @app_commands.choices(type=[
        app_commands.Choice(name="Варн", value="warn"),
        app_commands.Choice(name="Мут текстовый", value="mute_text"),
        app_commands.Choice(name="Мут голосовой", value="mute_voice"),
        app_commands.Choice(name="Бан", value="ban"),
        app_commands.Choice(name="Кик", value="kick"),
        app_commands.Choice(name="Переместить", value="move"),
    ])
    async def action(self, interaction: discord.Interaction, user: discord.Member,
                     type: app_commands.Choice[str], reason: str, duration: int = 0,
                     channel: discord.VoiceChannel = None):
        if not is_branch_staff(interaction.user, "mod") and not is_owner(interaction.user):
            await interaction.response.send_message("❌ Только Moderator.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("❌ Ботов нельзя.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ Себя нельзя.", ephemeral=True)
            return
        if is_owner(user) and await self.bot.db.get_setting("event_mode_active") != "1":
            await interaction.response.send_message("❌ Владельца/Owner нельзя.", ephemeral=True)
            return
        if type.value in ("warn", "mute_text", "mute_voice", "ban"):
            if await self.bot.db.has_active_punishment(user.id, type.value):
                await interaction.response.send_message(f"❌ Уже есть активное `{type.value}`.", ephemeral=True)
                return
        await interaction.response.defer(ephemeral=True)
        result = await self._apply(interaction.guild, user, type.value, reason, interaction.user, duration, channel)
        await interaction.followup.send(result["msg"], ephemeral=True)

    async def _apply(self, guild, user, type_, reason, author, duration, channel):
        now = datetime.now(timezone.utc)
        if type_ == "warn":
            await self.bot.db.add_punishment(user.id, "warn", reason, author.id)
            warns = await self.bot.db.count_active_warns(user.id)
            if warns >= config.WARN_TO_BAN:
                exp = now + timedelta(days=config.BAN_DURATION_DAYS)
                await self.bot.db.add_punishment(user.id, "ban", f"Авто-бан: {config.WARN_TO_BAN} варна",
                                                 self.bot.user.id, expires_at=exp.isoformat())
                try:
                    await user.ban(reason=f"Авто-бан: {config.WARN_TO_BAN} варна")
                except Exception as e:
                    return {"ok": False, "msg": f"Варн выдан, бан не удался: {e}"}
                await self._log(guild, f"🔨 {user.mention} — авто-бан {config.BAN_DURATION_DAYS}д ({config.WARN_TO_BAN} варна)")
                return {"ok": True, "msg": f"⚠️ Варн. Лимит {config.WARN_TO_BAN} — бан на {config.BAN_DURATION_DAYS} дней."}
            await self._dm(user, f"⚠️ Варн: {reason}")
            await self._log(guild, f"⚠️ {user.mention} — варн ({warns}/{config.WARN_TO_BAN}). {reason}")
            return {"ok": True, "msg": f"⚠️ Варн выдан ({warns}/{config.WARN_TO_BAN})."}
        if type_ in ("mute_text", "mute_voice"):
            if duration <= 0 or duration > config.MUTE_MAX_HOURS:
                return {"ok": False, "msg": f"Длительность 1–{config.MUTE_MAX_HOURS} ч."}
            role_name = "Muted-Text" if type_ == "mute_text" else "Muted-Voice"
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                return {"ok": False, "msg": f"Роль {role_name} не найдена."}
            try:
                await user.add_roles(role, reason=reason)
            except Exception as e:
                return {"ok": False, "msg": f"Ошибка роли: {e}"}
            exp = now + timedelta(hours=duration)
            await self.bot.db.add_punishment(user.id, type_, reason, author.id, expires_at=exp.isoformat())
            await self._dm(user, f"🔇 Мут на {duration}ч: {reason}")
            await self._log(guild, f"🔇 {user.mention} — {type_} {duration}ч. {reason}")
            return {"ok": True, "msg": f"🔇 Мут {duration}ч выдан."}
        if type_ == "ban":
            exp = now + timedelta(days=config.BAN_DURATION_DAYS)
            try:
                await user.ban(reason=reason)
            except Exception as e:
                return {"ok": False, "msg": f"Ошибка бана: {e}"}
            await self.bot.db.add_punishment(user.id, "ban", reason, author.id, expires_at=exp.isoformat())
            await self._log(guild, f"🔨 {user.mention} — бан {config.BAN_DURATION_DAYS}д. {reason}")
            return {"ok": True, "msg": f"🔨 Забанен на {config.BAN_DURATION_DAYS} дней."}
        if type_ == "kick":
            try:
                await user.kick(reason=reason)
            except Exception as e:
                return {"ok": False, "msg": f"Ошибка кика: {e}"}
            await self.bot.db.add_punishment(user.id, "kick", reason, author.id)
            await self._log(guild, f"👢 {user.mention} — кик. {reason}")
            return {"ok": True, "msg": "👢 Кикнут."}
        if type_ == "move":
            if not channel:
                return {"ok": False, "msg": "Укажи канал."}
            if not user.voice or not user.voice.channel:
                return {"ok": False, "msg": "Не в войсе."}
            try:
                await user.move_to(channel)
            except Exception as e:
                return {"ok": False, "msg": f"Ошибка: {e}"}
            await self._log(guild, f"↔️ {user.mention} → {channel.mention}")
            return {"ok": True, "msg": "↔️ Перемещён."}
        return {"ok": False, "msg": "Неизвестный тип."}

    @app_commands.command(name="history", description="История наказаний")
    async def history(self, interaction: discord.Interaction, user: discord.Member):
        if not is_branch_master_plus(interaction.user, "mod") and not is_owner(interaction.user):
            await interaction.response.send_message("❌ Moderator master+.", ephemeral=True)
            return
        rows = await self.bot.db.get_history(user.id)
        if not rows:
            await interaction.response.send_message("📭 Нет наказаний.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📋 {user}", color=discord.Color.orange())
        for r in rows[:20]:
            value = f"`{r['type']}` — {r['reason'] or '—'} {'🟢' if r['active'] else '⚪'}"
            if r["expires_at"]:
                value += f"\n⏳ до {r['expires_at']}"
            embed.add_field(name=f"#{r['id']}", value=value, inline=False)
        embed.set_footer(text=f"Всего: {len(rows)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unpunish", description="Снять наказание")
    async def unpunish(self, interaction: discord.Interaction, punishment_id: int, reason: str):
        if not is_branch_master_plus(interaction.user, "mod") and not is_owner(interaction.user):
            await interaction.response.send_message("❌ Moderator master+.", ephemeral=True)
            return
        row = await self.bot.db.get_punishment(punishment_id)
        if not row or not row["active"]:
            await interaction.response.send_message("❌ Не найдено или снято.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(row["discord_id"])
        if row["type"] == "mute_text" and member:
            role = discord.utils.get(guild.roles, name="Muted-Text")
            if role:
                await member.remove_roles(role, reason=reason)
        elif row["type"] == "mute_voice" and member:
            role = discord.utils.get(guild.roles, name="Muted-Voice")
            if role:
                await member.remove_roles(role, reason=reason)
        elif row["type"] == "ban":
            try:
                await guild.unban(discord.Object(id=row["discord_id"]), reason=reason)
            except Exception:
                pass
        await self.bot.db.deactivate_punishment(punishment_id, interaction.user.id)
        await self._log(guild, f"✅ Снято #{punishment_id} с <@{row['discord_id']}>. {reason}")
        await interaction.response.send_message(f"✅ Снято #{punishment_id}.", ephemeral=True)

    @app_commands.command(name="punished-left", description="Ушедшие с наказаниями")
    async def punished_left(self, interaction: discord.Interaction):
        if not is_branch_master_plus(interaction.user, "mod") and not is_owner(interaction.user):
            await interaction.response.send_message("❌ Moderator master+.", ephemeral=True)
            return
        rows = await self.bot.db.get_punished_left()
        if not rows:
            await interaction.response.send_message("📭 Пусто.", ephemeral=True)
            return
        embed = discord.Embed(title="👻 Ушедшие с наказаниями", color=discord.Color.dark_gray())
        for r in rows[:25]:
            embed.add_field(name=f"`{r['discord_id']}`", value=f"{r['type']} — {r['reason'] or '—'}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(minutes=5)
    async def mute_check(self):
        try:
            rows = await self.bot.db.get_expired_punishments()
        except Exception:
            return
        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return
        for r in rows:
            member = guild.get_member(r["discord_id"])
            if member and r["type"] in ("mute_text", "mute_voice"):
                role = discord.utils.get(guild.roles, name="Muted-Text" if r["type"] == "mute_text" else "Muted-Voice")
                if role:
                    try:
                        await member.remove_roles(role, reason="Истёк мут")
                    except Exception:
                        pass
            await self.bot.db.deactivate_punishment(r["id"], self.bot.user.id)

    @mute_check.before_loop
    async def before_mute(self):
        await self.bot.wait_until_ready()

    async def _dm(self, user, text):
        try:
            await user.send(text)
        except Exception:
            pass

    async def _log(self, guild, text):
        ch_id = int(await self.bot.db.get_setting("channel_mod_log") or 0)
        ch = guild.get_channel(ch_id)
        if ch:
            await ch.send(text)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
