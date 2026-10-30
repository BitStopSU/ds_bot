import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from collections import defaultdict

from utils import is_owner, is_branch_master_plus


class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.actions = defaultdict(lambda: defaultdict(list))
        self.WINDOW = 60
        self.THRESHOLDS = {"channel_delete": 3, "role_delete": 3, "channel_create": 5,
                           "role_create": 5, "ban": 5, "kick": 5}

    def _check(self, user_id, action) -> bool:
        now = datetime.utcnow()
        start = now - timedelta(seconds=self.WINDOW)
        self.actions[user_id][action] = [t for t in self.actions[user_id][action] if t > start]
        self.actions[user_id][action].append(now)
        return len(self.actions[user_id][action]) >= self.THRESHOLDS.get(action, 999)

    @app_commands.command(name="whitelist", description="Добавить/убрать из whitelist Anti-Nuke")
    @app_commands.choices(action=[app_commands.Choice(name="Добавить", value="add"),
                                  app_commands.Choice(name="Убрать", value="remove")])
    async def whitelist(self, interaction: discord.Interaction, action: str, user: discord.Member):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ Только владелец/Owner.", ephemeral=True)
            return
        if action == "add":
            await self.bot.db.add_whitelist(user.id, interaction.user.id)
            await interaction.response.send_message(f"✅ {user.mention} в whitelist.", ephemeral=True)
        else:
            await self.bot.db.remove_whitelist(user.id)
            await interaction.response.send_message(f"✅ {user.mention} убран из whitelist.", ephemeral=True)

    @app_commands.command(name="protect", description="Защитить канал/категорию от удаления")
    async def protect(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "mod"):
            await interaction.response.send_message("❌ Только master+ / владелец.", ephemeral=True)
            return
        await self.bot.db.protect_channel(channel.id, interaction.user.id)
        await interaction.response.send_message(f"🛡️ {channel.mention} защищён.", ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if not entry.user or entry.user.bot or is_owner(entry.user) or await self.bot.db.is_whitelisted(entry.user.id):
                return
            if await self.bot.db.is_protected(channel.id):
                await self._ask_confirm(guild, entry.user, channel.name, "удаление канала")
                return
            if self._check(entry.user.id, "channel_delete"):
                await self._trigger(guild, entry.user, "channel_delete", 3)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            if not entry.user or entry.user.bot or is_owner(entry.user) or await self.bot.db.is_whitelisted(entry.user.id):
                return
            if self._check(entry.user.id, "role_delete"):
                await self._trigger(role.guild, entry.user, "role_delete", 3)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if not entry.user or entry.user.bot or is_owner(entry.user) or await self.bot.db.is_whitelisted(entry.user.id):
                return
            if self._check(entry.user.id, "ban"):
                await self._trigger(guild, entry.user, "ban", 5)

    async def _trigger(self, guild, user, action, count):
        for role in user.roles:
            perms = role.permissions
            if perms.administrator or perms.manage_channels or perms.manage_roles or perms.ban_members or perms.kick_members:
                try:
                    await user.remove_roles(role, reason="Anti-Nuke")
                except Exception:
                    pass
        quarantine = discord.utils.get(guild.roles, name="Quarantine")
        if quarantine:
            try:
                await user.add_roles(quarantine, reason="Anti-Nuke карантин")
            except Exception:
                pass
        await self.bot.db.add_antinuke_event(user.id, action, count)
        await self._log(guild, user, action, count)

    async def _ask_confirm(self, guild, user, channel_name, action_text):
        ch_id = int(await self.bot.db.get_setting("channel_mod_log") or 0)
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        embed = discord.Embed(title="⚠️ Запрос подтверждения",
                              description=f"{user.mention} пытается выполнить **{action_text}**: `{channel_name}`",
                              color=discord.Color.orange())
        await ch.send(embed=embed, view=ConfirmView(self.bot, user, channel_name, action_text))

    async def _log(self, guild, user, action, count):
        ch = guild.get_channel(int(await self.bot.db.get_setting("channel_mod_log") or 0))
        if ch:
            embed = discord.Embed(title="🚨 АНТИКРАШ", color=discord.Color.dark_red(), timestamp=datetime.utcnow())
            embed.add_field(name="Нарушитель", value=f"{user.mention}\n`{user.id}`", inline=False)
            embed.add_field(name="Действие", value=action, inline=True)
            embed.add_field(name="Кол-во", value=f"{count} за {self.WINDOW}с", inline=True)
            await ch.send(embed=embed, view=AntiNukeView(self.bot, user))


class ConfirmView(discord.ui.View):
    def __init__(self, bot, user, channel_name, action_text):
        super().__init__(timeout=300)
        self.bot, self.user = bot, user
        self.channel_name, self.action_text = channel_name, action_text

    @discord.ui.button(label="✅ Разрешить", style=discord.ButtonStyle.success)
    async def allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "mod"):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await interaction.response.edit_message(content="✅ Разрешено. Действие не блокируется.", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "mod"):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Отклонено. Уведомление создателю.", embed=None, view=None)
        try:
            await self.user.send(f"⚠️ Твоё действие `{self.action_text}` над `{self.channel_name}` отклонено.")
        except Exception:
            pass
        self.stop()


class AntiNukeView(discord.ui.View):
    def __init__(self, bot, user):
        super().__init__(timeout=None)
        self.bot, self.user = bot, user

    async def _sec(self, interaction):
        return is_owner(interaction.user) or is_branch_master_plus(interaction.user, "mod")

    @discord.ui.button(label="✅ Снять ограничение", style=discord.ButtonStyle.success, custom_id="an_release")
    async def release(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._sec(interaction):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        q = discord.utils.get(interaction.guild.roles, name="Quarantine")
        if q and q in self.user.roles:
            await self.user.remove_roles(q, reason="Anti-Nuke: ложное срабатывание")
        await interaction.response.send_message(f"✅ Ограничения сняты с {self.user.mention}.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="🔨 Забанить", style=discord.ButtonStyle.danger, custom_id="an_ban")
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._sec(interaction):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await interaction.guild.ban(self.user, reason=f"Anti-Nuke подтверждён {interaction.user}")
        await interaction.response.send_message(f"🔨 {self.user} забанен.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="👢 Кикнуть", style=discord.ButtonStyle.secondary, custom_id="an_kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._sec(interaction):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
            return
        await interaction.guild.kick(self.user, reason=f"Anti-Nuke подтверждён {interaction.user}")
        await interaction.response.send_message(f"👢 {self.user} кикнут.", ephemeral=True)
        await interaction.message.edit(view=None)


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
