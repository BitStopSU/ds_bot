import discord
import json
import os
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils import is_owner, is_branch_master_plus

SNAPSHOT_DIR = "snapshots"


class Snapshot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    async def create_snapshot(self, guild: discord.Guild, author_id: int) -> str:
        data = {"created_at": datetime.utcnow().isoformat(), "author_id": author_id,
                "categories": [], "channels": [], "roles": []}
        for cat in guild.categories:
            data["categories"].append({"id": cat.id, "name": cat.name, "position": cat.position,
                                        "overwrites": self._ser_ow(cat)})
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            data["channels"].append({"id": ch.id, "name": ch.name, "type": str(ch.type),
                                     "category_id": ch.category_id, "position": ch.position,
                                     "topic": getattr(ch, "topic", None), "overwrites": self._ser_ow(ch)})
        for role in guild.roles:
            if role.is_default() or role.managed:
                continue
            data["roles"].append({"id": role.id, "name": role.name, "color": role.color.value,
                                  "position": role.position, "permissions": role.permissions.value,
                                  "hoist": role.hoist, "mentionable": role.mentionable})
        filename = f"{SNAPSHOT_DIR}/snap_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        files = sorted(os.listdir(SNAPSHOT_DIR))
        for old in files[:-10]:
            try:
                os.remove(os.path.join(SNAPSHOT_DIR, old))
            except Exception:
                pass
        return filename

    def _ser_ow(self, channel):
        result = []
        for target, overwrite in channel.overwrites.items():
            allow, deny = overwrite.pair()
            result.append({"target_id": target.id,
                           "target_type": "role" if isinstance(target, discord.Role) else "member",
                           "allow": allow.value, "deny": deny.value})
        return result

    async def restore_snapshot(self, guild, filename) -> dict:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
        existing_cat = {c.name for c in guild.categories}
        existing_ch = {c.name for c in guild.channels}
        existing_roles = {r.name for r in guild.roles}
        restored = {"categories": 0, "channels": 0, "roles": 0}
        for role_data in data["roles"]:
            if role_data["name"] in existing_roles:
                continue
            try:
                await guild.create_role(name=role_data["name"], color=discord.Color(role_data["color"]),
                                        permissions=discord.Permissions(role_data["permissions"]),
                                        hoist=role_data["hoist"], mentionable=role_data["mentionable"],
                                        reason="Snapshot restore")
                restored["roles"] += 1
            except Exception as e:
                print(f"role {role_data['name']}: {e}")
        cat_map = {}
        for category_data in data["categories"]:
            if category_data["name"] in existing_cat:
                category = discord.utils.get(guild.categories, name=category_data["name"])
            else:
                try:
                    category = await guild.create_category(name=category_data["name"],
                                                           position=category_data["position"], reason="Snapshot restore")
                    restored["categories"] += 1
                except Exception as e:
                    print(f"cat {category_data['name']}: {e}")
                    continue
            cat_map[category_data["id"]] = category
        for channel_data in data["channels"]:
            if channel_data["name"] in existing_ch:
                continue
            category = cat_map.get(channel_data["category_id"])
            try:
                if channel_data["type"] == "text":
                    await guild.create_text_channel(name=channel_data["name"], category=category,
                                                    topic=channel_data.get("topic"), position=channel_data["position"],
                                                    reason="Snapshot restore")
                elif channel_data["type"] == "voice":
                    await guild.create_voice_channel(name=channel_data["name"], category=category,
                                                     position=channel_data["position"], reason="Snapshot restore")
                restored["channels"] += 1
            except Exception as e:
                print(f"channel {channel_data['name']}: {e}")
        return restored

    @app_commands.command(name="snapshot", description="Управление снапшотами")
    @app_commands.choices(action=[app_commands.Choice(name="Создать", value="create"),
                                  app_commands.Choice(name="Список", value="list"),
                                  app_commands.Choice(name="Восстановить", value="restore")])
    async def snapshot(self, interaction: discord.Interaction, action: str, file: str = None):
        if not is_owner(interaction.user) and not is_branch_master_plus(interaction.user, "mod"):
            await interaction.response.send_message("❌ Только master+ / владелец.", ephemeral=True)
            return
        if action == "create":
            await interaction.response.defer(ephemeral=True)
            path = await self.create_snapshot(interaction.guild, interaction.user.id)
            await interaction.followup.send(f"✅ Снапшот: `{path}`", ephemeral=True)
        elif action == "list":
            files = sorted(os.listdir(SNAPSHOT_DIR))
            if not files:
                await interaction.response.send_message("📭 Нет снапшотов.", ephemeral=True)
                return
            await interaction.response.send_message("📋 " + "\n".join(f"`{f}`" for f in files[-10:]), ephemeral=True)
        elif action == "restore":
            if not file:
                await interaction.response.send_message("❌ Укажи файл.", ephemeral=True)
                return
            path = os.path.join(SNAPSHOT_DIR, file)
            if not os.path.exists(path):
                await interaction.response.send_message("❌ Не найден.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            result = await self.restore_snapshot(interaction.guild, path)
            await interaction.followup.send(
                f"✅ Восстановлено: категорий {result['categories']}, каналов {result['channels']}, ролей {result['roles']}",
                ephemeral=True)


async def setup(bot):
    await bot.add_cog(Snapshot(bot))
