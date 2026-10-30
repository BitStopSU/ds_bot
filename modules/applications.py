import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils import is_owner, is_branch_master_plus

BRANCH_LABELS = {"support": "Support", "mod": "Moderator", "event": "Eventer"}
APPS_CHANNEL_KEY = {"support": "channel_support_apps", "mod": "channel_mod_apps", "event": "channel_event_apps"}
VOICE_CAT_KEY = {"support": "vcat_voice_support", "mod": "vcat_voice_mod", "event": "vcat_voice_event"}


class Applications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.interview_channels = {}

    @app_commands.command(name="apply", description="Подать заявку в стафф")
    async def apply(self, interaction: discord.Interaction):
        existing = await self.bot.db.get_active_application(interaction.user.id)
        if existing:
            await interaction.response.send_message(f"❌ У тебя уже есть активная заявка #{existing['id']}.", ephemeral=True)
            return
        await interaction.response.send_modal(ApplyModal(self.bot))


class ApplyModal(discord.ui.Modal, title="Заявка в стафф"):
    branch = discord.ui.TextInput(label="Ветка (Support / Moderator / Eventer)", required=True, max_length=20)
    hours = discord.ui.TextInput(label="Свободные часы в неделю", required=True, max_length=3)
    past = discord.ui.TextInput(label="Где стояли на стаффе", style=discord.TextStyle.paragraph, required=False, max_length=500)
    motivation = discord.ui.TextInput(label="Почему хотите в стафф", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    discord_exp = discord.ui.TextInput(label="Опыт в Discord (лет)", required=True, max_length=2)
    timezone = discord.ui.TextInput(label="Часовой пояс", required=True, max_length=20)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        branch = self.branch.value.strip().lower()
        if branch not in BRANCH_LABELS:
            await interaction.response.send_message("❌ Ветка: Support / Moderator / Eventer.", ephemeral=True)
            return
        try:
            hours_int = int(self.hours.value)
        except ValueError:
            await interaction.response.send_message("❌ Часы — число.", ephemeral=True)
            return
        app_id = await self.bot.db.add_application(interaction.user.id, branch, hours_int,
                                                   self.past.value, self.motivation.value,
                                                   self.discord_exp.value, self.timezone.value)
        ch = interaction.guild.get_channel(int(await self.bot.db.get_setting(APPS_CHANNEL_KEY[branch]) or 0))
        if not ch:
            await interaction.response.send_message("❌ Канал набора не настроен.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📝 Заявка #{app_id} — {BRANCH_LABELS[branch]}",
                              color=discord.Color.blurple(), timestamp=datetime.utcnow())
        embed.add_field(name="Кандидат", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=False)
        embed.add_field(name="Часы/нед", value=self.hours.value, inline=True)
        embed.add_field(name="Опыт", value=self.discord_exp.value, inline=True)
        embed.add_field(name="Часовой пояс", value=self.timezone.value, inline=True)
        embed.add_field(name="Прошлый опыт", value=self.past.value or "—", inline=False)
        embed.add_field(name="Мотивация", value=self.motivation.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await ch.send(embed=embed, view=AppView(self.bot, app_id, interaction.user, branch))
        label = BRANCH_LABELS[branch]
        for rank in ("Admin", "Curator"):
            role = discord.utils.get(interaction.guild.roles, name=f"{label} | {rank}")
            if role:
                for member in role.members:
                    if not member.bot:
                        try:
                            await member.send(f"📝 Новая заявка #{app_id} в {label}: {ch.mention}")
                        except Exception:
                            pass
        await interaction.response.send_message(f"✅ Заявка #{app_id} подана.", ephemeral=True)


class AppView(discord.ui.View):
    def __init__(self, bot, app_id, applicant, branch):
        super().__init__(timeout=None)
        self.bot, self.app_id, self.applicant, self.branch = bot, app_id, applicant, branch

    def _ok(self, member):
        return is_owner(member) or is_branch_master_plus(member, self.branch)

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="ap_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._ok(interaction.user):
            await interaction.response.send_message("❌ Только master+ ветки.", ephemeral=True)
            return
        await self.bot.db.set_application_status(self.app_id, "accepted", interaction.user.id)
        role = discord.utils.get(interaction.guild.roles, name=f"{BRANCH_LABELS[self.branch]} | Staff")
        if role:
            try:
                await self.applicant.add_roles(role, reason=f"Заявка #{self.app_id}")
            except Exception as e:
                await interaction.response.send_message(f"⚠️ Роль не выдана: {e}", ephemeral=True)
                return
        try:
            await self.applicant.send(f"🎉 Заявка #{self.app_id} в {BRANCH_LABELS[self.branch]} принята!")
        except Exception:
            pass
        await self.bot.db.add_staff(self.applicant.id, self.branch, "staff")
        await interaction.response.edit_message(content=f"✅ Заявка #{self.app_id} принята ({interaction.user.mention}). Роль выдана.", embed=None, view=None)

    @discord.ui.button(label="💬 Собеседование", style=discord.ButtonStyle.primary, custom_id="ap_int")
    async def interview(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._ok(interaction.user):
            await interaction.response.send_message("❌ Только master+ ветки.", ephemeral=True)
            return
        guild = interaction.guild
        category = guild.get_channel(int(await self.bot.db.get_setting(VOICE_CAT_KEY[self.branch]) or 0))
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            self.applicant: discord.PermissionOverwrite(connect=True, speak=True),
            interaction.user: discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True),
        }
        admin_role = discord.utils.get(guild.roles, name=f"{BRANCH_LABELS[self.branch]} | Admin")
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True)
        try:
            voice = await guild.create_voice_channel(name=f"Собеседование | {self.applicant.display_name}",
                                                     category=category, overwrites=overwrites,
                                                     reason=f"Заявка #{self.app_id}")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        self.bot.get_cog("Applications").interview_channels[voice.id] = True
        ping = f"{self.applicant.mention} {interaction.user.mention}"
        if admin_role:
            ping += f" <@&{admin_role.id}>"
        await voice.send(f"💬 Собеседование по заявке #{self.app_id}\n{ping}")
        await interaction.response.send_message(f"✅ Войс: {voice.mention}", ephemeral=True)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="ap_rej")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._ok(interaction.user):
            await interaction.response.send_message("❌ Только master+ ветки.", ephemeral=True)
            return
        await interaction.response.send_modal(RejectAppModal(self.bot, self.app_id, self.applicant, self.branch))


class RejectAppModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(label="Причина", style=discord.TextStyle.paragraph, required=True, max_length=500)

    def __init__(self, bot, app_id, applicant, branch):
        super().__init__()
        self.bot, self.app_id, self.applicant, self.branch = bot, app_id, applicant, branch

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.set_application_status(self.app_id, "rejected", interaction.user.id)
        try:
            await self.applicant.send(f"❌ Заявка #{self.app_id} отклонена.\nПричина: {self.reason.value}")
        except Exception:
            pass
        await interaction.response.edit_message(content=f"❌ Заявка #{self.app_id} отклонена. {self.reason.value}", embed=None, view=None)


class AppVoiceListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        apps = self.bot.get_cog("Applications")
        if not apps:
            return
        if before.channel and before.channel.id in apps.interview_channels and len(before.channel.members) == 0:
            try:
                await before.channel.delete(reason="Собеседование завершено")
            except Exception:
                pass
            apps.interview_channels.pop(before.channel.id, None)


async def setup(bot):
    await bot.add_cog(Applications(bot))
    await bot.add_cog(AppVoiceListener(bot))
