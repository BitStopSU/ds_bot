import asyncio
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

import discord
from discord.ext import commands, tasks

import config
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot")

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True
intents.guilds = True


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(config.DB_PATH)

    async def setup_hook(self):
        await self.db.connect()
        log.info("БД подключена")

        for ext in [
            "modules.verification", "modules.moderation", "modules.hours", "modules.antinuke",
            "modules.snapshot", "modules.profiles", "modules.branch", "modules.event",
            "modules.economy", "modules.reports", "modules.applications", "modules.ai_analysis",
            "modules.bug_reports", "modules.switch_branch",
        ]:
            try:
                await self.load_extension(ext)
                log.info("Загружен модуль: %s", ext)
            except Exception as e:
                log.error("Ошибка загрузки %s: %s", ext, e)

        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Слеш-команды синхронизированы")

    async def on_ready(self):
        log.info("Бот запущен как %s (ID: %s)", self.user, self.user.id)
        guild = self.get_guild(config.GUILD_ID)
        if guild:
            await self.setup_server_structure(guild)
        if not self.auto_snapshot.is_running():
            self.auto_snapshot.start()

    @tasks.loop(hours=24)
    async def auto_snapshot(self):
        guild = self.get_guild(config.GUILD_ID)
        if guild:
            cog = self.get_cog("Snapshot")
            if cog:
                await cog.create_snapshot(guild, self.user.id)

    @auto_snapshot.before_loop
    async def before_snapshot(self):
        await self.wait_until_ready()

    async def setup_server_structure(self, guild: discord.Guild):
        log.info("Проверка структуры сервера...")

        base_roles = {
            "owner": {"name": "Owner", "color": discord.Color.gold()},
            "unverified": {"name": "unverified", "color": discord.Color.greyple()},
            "verified": {"name": "verified", "color": discord.Color.green()},
            "denied": {"name": "Не допуск", "color": discord.Color.red()},
            "muted_text": {"name": "Muted-Text", "color": discord.Color.dark_gray()},
            "muted_voice": {"name": "Muted-Voice", "color": discord.Color.dark_gray()},
            "quarantine": {"name": "Quarantine", "color": discord.Color.dark_red()},
        }
        for key, data in base_roles.items():
            role = discord.utils.get(guild.roles, name=data["name"])
            if not role:
                role = await guild.create_role(name=data["name"], color=data["color"], reason="Автосоздание")
                log.info("Создана роль: %s", data["name"])
            await self.db.set_setting(f"role_{key}", str(role.id))

        branches = {"support": "Support", "mod": "Moderator", "event": "Eventer"}
        ranks = {"admin": "Admin", "curator": "Curator", "master": "Master", "staff": "Staff"}
        branch_colors = {"support": discord.Color.blue(), "mod": discord.Color.orange(), "event": discord.Color.purple()}
        for bkey, bname in branches.items():
            for rkey, rname in ranks.items():
                full = f"{bname} | {rname}"
                role = discord.utils.get(guild.roles, name=full)
                if not role:
                    role = await guild.create_role(name=full, color=branch_colors[bkey], reason="Автосоздание ветки")
                    log.info("Создана роль: %s", full)
                await self.db.set_setting(f"role_{bkey}_{rkey}", str(role.id))

        categories = {"support_cat": "Support", "mod_cat": "Moderator", "event_cat": "Eventer"}
        for key, name in categories.items():
            cat = discord.utils.get(guild.categories, name=name)
            if not cat:
                cat = await guild.create_category(name=name, reason="Автосоздание")
                log.info("Создана категория: %s", name)
            await self.db.set_setting(f"cat_{key}", str(cat.id))

        text_channels = {
            "channel_support_log": ("support-log", "support_cat"),
            "channel_mod_log": ("mod-log", "mod_cat"),
            "channel_event_log": ("event-log", "event_cat"),
            "channel_verify": ("верификация", "support_cat"),
            "channel_support_apps": ("support-apps", "support_cat"),
            "channel_mod_apps": ("mod-apps", "mod_cat"),
            "channel_event_apps": ("event-apps", "event_cat"),
            "channel_coder_log": ("coder-log", "support_cat"),
        }
        for key, (name, cat_key) in text_channels.items():
            ch = discord.utils.get(guild.text_channels, name=name)
            if not ch:
                cat_id = int(await self.db.get_setting(f"cat_{cat_key}") or 0)
                ch = await guild.create_text_channel(name=name, category=guild.get_channel(cat_id), reason="Автосоздание")
                log.info("Создан канал: %s", name)
            await self.db.set_setting(key, str(ch.id))

        voice_cats = {
            "vcat_voice_support": "Проходка Support", "vcat_voice_mod": "Мод-румы",
            "vcat_voice_event": "Ивент-румы",
        }
        for key, name in voice_cats.items():
            cat = discord.utils.get(guild.categories, name=name)
            if not cat:
                cat = await guild.create_category(name=name, reason="Автосоздание")
                log.info("Создана голосовая категория: %s", name)
            await self.db.set_setting(key, str(cat.id))

        await self.apply_permissions(guild)
        log.info("Структура сервера готова")

    async def apply_permissions(self, guild: discord.Guild):
        async def rid(key):
            return int(await self.db.get_setting(key) or 0)

        muted_text = guild.get_role(await rid("role_muted_text"))
        muted_voice = guild.get_role(await rid("role_muted_voice"))
        unverified = guild.get_role(await rid("role_unverified"))
        verify_ch = guild.get_channel(await rid("channel_verify"))
        quarantine = guild.get_role(await rid("role_quarantine"))
        if muted_text:
            for ch in guild.text_channels:
                await ch.set_permissions(muted_text, send_messages=False)
        if muted_voice:
            vcat = guild.get_channel(await rid("vcat_voice_mod"))
            if vcat:
                await vcat.set_permissions(muted_voice, connect=False)
        if quarantine:
            for ch in guild.channels:
                await ch.set_permissions(quarantine, send_messages=False, connect=False)
        if unverified and verify_ch:
            for ch in guild.text_channels:
                if ch.id != verify_ch.id:
                    await ch.set_permissions(unverified, view_channel=False)
            await verify_ch.set_permissions(unverified, view_channel=True, send_messages=True)

        branches = {"support": "channel_support_apps", "mod": "channel_mod_apps", "event": "channel_event_apps"}
        for bkey, ch_key in branches.items():
            ch = guild.get_channel(await rid(ch_key))
            if not ch:
                continue
            await ch.set_permissions(guild.default_role, view_channel=False)
            for rank in ("admin", "curator", "master"):
                role = guild.get_role(await rid(f"role_{bkey}_{rank}"))
                if role:
                    await ch.set_permissions(role, view_channel=True)
        log.info("Права каналов настроены")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        now = datetime.utcnow().isoformat()
        await self.db.upsert_user(member.id, str(member), member.global_name or "", now)
        await self.db.log_join_event(member.id, "join")
        unverified_id = int(await self.db.get_setting("role_unverified") or 0)
        if unverified_id:
            try:
                await member.add_roles(discord.Object(id=unverified_id), reason="Новый участник")
            except Exception as e:
                log.warning("Не смог выдать unverified %s: %s", member.id, e)
        log_ch_id = int(await self.db.get_setting("channel_support_log") or 0)
        if log_ch_id:
            ch = self.get_channel(log_ch_id)
            if ch:
                await ch.send(f"📥 Зашёл {member.mention} (`{member.id}`)")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await self.db.set_user_left(member.id)
        await self.db.log_join_event(member.id, "leave")
        rows = await self.db.get_history(member.id)
        for row in rows:
            if row["type"] == "warn" and row["active"]:
                await self.db.deactivate_punishment(row["id"], self.user.id)


async def main():
    load_dotenv()
    bot = Bot()
    async with bot:
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    asyncio.run(main())
