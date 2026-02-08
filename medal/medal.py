import discord
import aiohttp
import logging
import asyncio
import re
from redbot.core import commands, Config, checks
from discord.ext import tasks

log = logging.getLogger("red.medal")

class Medal(commands.Cog):
    """Automatyczne powiadomienia o nowych klipach z Medal.tv"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8472910482, force_registration=True)
        
        default_guild = {
            "users": {},  # Format: {"user_id": "last_content_id"}
            "channel_id": None
        }
        self.config.register_guild(**default_guild)
        
        self.session = aiohttp.ClientSession()
        self.check_medal.start()

    def cog_unload(self):
        self.check_medal.cancel()
        self.bot.loop.create_task(self.session.close())

    async def fetch_latest_clip(self, api_key: str, user_id: int):
        url = "https://developers.medal.tv/v1/latest"
        params = {"userId": user_id, "limit": 1}
        headers = {"Authorization": api_key, "Accept": "application/json"}

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                clips = data.get("contentObjects", [])
                return clips[0] if clips else None
        except Exception as e:
            log.error(f"Wyjątek Medal API: {e}")
            return None

    def extract_author(self, clip: dict, user_id: int):
        """Wyciąga nazwę autora z pola credits lub innych dostępnych pól"""
        credits = clip.get("credits", "")
        # Format credits to zazwyczaj: "Credits to NICK (url)"
        if credits.startswith("Credits to "):
            # Wyciąga tekst między "Credits to " a pierwszą spacją/nawiasem
            name = credits.replace("Credits to ", "").split(" (")[0]
            return name
        
        return clip.get("creatorDisplayName") or clip.get("userName") or f"Gracz {user_id}"

    async def add_reactions_to_msg(self, message: discord.Message):
        reactions = ["❤️", "👍", "👎"]
        for emoji in reactions:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                break

    @tasks.loop(minutes=5)
    async def check_medal(self):
        api_data = await self.bot.get_shared_api_tokens("medal")
        api_key = api_data.get("api_key")
        if not api_key:
            return

        all_guilds = await self.config.all_guilds()
        for guild_id, settings in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if not guild or not settings["channel_id"] or not settings["users"]:
                continue

            channel = guild.get_channel(settings["channel_id"])
            if not channel:
                continue

            updated_users = settings["users"].copy()
            should_update = False

            for user_id, last_id in settings["users"].items():
                clip = await self.fetch_latest_clip(api_key, int(user_id))
                if not clip:
                    continue

                content_id = clip.get("contentId")
                if content_id == last_id:
                    continue

                # WYCIĄGANIE NICKU
                author_name = self.extract_author(clip, user_id)
                clip_url = clip.get("directClipUrl") or clip.get("url")
                
                msg = await channel.send(f"🎬 **{author_name}** wrzucił nowego super medala!\n{clip_url}")
                await self.add_reactions_to_msg(msg)
                
                updated_users[str(user_id)] = content_id
                should_update = True

            if should_update:
                await self.config.guild(guild).users.set(updated_users)

    @check_medal.before_loop
    async def before_check_medal(self):
        await self.bot.wait_until_ready()

    # =========================
    # KOMENDY
    # =========================

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def medal(self, ctx):
        """Zarządzanie powiadomieniami Medal.tv"""
        pass

    @medal.command(name="add")
    async def add_user(self, ctx, user_id: int):
        """Dodaj ID użytkownika do śledzenia"""
        async with self.config.guild(ctx.guild).users() as users:
            if str(user_id) in users:
                return await ctx.send("❌ Ten użytkownik jest już na liście.")
            users[str(user_id)] = None
        await ctx.send(f"✅ Dodano użytkownika `{user_id}` do listy śledzonych.")

    @medal.command(name="remove")
    async def remove_user(self, ctx, user_id: int):
        """Usuń ID użytkownika z listy"""
        async with self.config.guild(ctx.guild).users() as users:
            if str(user_id) in users:
                del users[str(user_id)]
                await ctx.send(f"✅ Usunięto użytkownika `{user_id}`.")
            else:
                await ctx.send("❌ Nie ma takiego użytkownika na liście.")

    @medal.command(name="list")
    async def list_users(self, ctx):
        """Pokaż listę śledzonych ID"""
        users = await self.config.guild(ctx.guild).users()
        if not users:
            return await ctx.send("Lista jest pusta.")
        
        lista = "\n".join([f"• `{uid}`" for uid in users.keys()])
        await ctx.send(f"**Śledzeni użytkownicy Medal:**\n{lista}")

    @medal.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Ustaw kanał dla powiadomień"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Kanał ustawiony na {channel.mention}")

    @medal.command()
    async def test(self, ctx):
        """Testuje połączenie i wyciąganie nicku"""
        conf = await self.config.guild(ctx.guild).all()
        api_data = await self.bot.get_shared_api_tokens("medal")
        api_key = api_data.get("api_key")

        if not api_key or not conf["users"]:
            return await ctx.send("❌ Brakuje klucza API lub lista osób jest pusta.")

        await ctx.send(f"⏳ Testowanie wyciągania nicku...")
        
        async with ctx.typing():
            first_uid = list(conf["users"].keys())[0]
            clip = await self.fetch_latest_clip(api_key, int(first_uid))
            
            if clip:
                author = self.extract_author(clip, first_uid)
                url = clip.get("directClipUrl") or clip.get("url")
                msg = await ctx.send(f"✅ **Test udany!**\nAutor: `{author}`\nKlip: {url}")
                await self.add_reactions_to_msg(msg)
            else:
                await ctx.send(f"❌ Nie udało się pobrać danych dla `{first_uid}`.")

async def setup(bot):
    await bot.add_cog(Medal(bot))
