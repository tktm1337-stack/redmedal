import discord
import aiohttp
import logging
from redbot.core import commands, Config, checks
from discord.ext import tasks

# Ustawienie loggera, żeby błędy były widoczne w logach Reda
log = logging.getLogger("red.medal")

class Medal(commands.Cog):
    """Automatyczne powiadomienia o nowych klipach z Medal.tv"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8472910482, force_registration=True)
        
        default_guild = {
            "medal_user_id": None,
            "channel_id": None,
            "last_content_id": None
        }
        self.config.register_guild(**default_guild)
        
        self.session = aiohttp.ClientSession()
        self.check_medal.start()

    def cog_unload(self):
        self.check_medal.cancel()
        self.bot.loop.create_task(self.session.close())

    async def fetch_latest_clip(self, api_key: str, user_id: int):
        """Pobiera najnowszy klip i loguje szczegóły w razie błędu"""
        url = "https://developers.medal.tv/v1/latest"
        params = {"userId": user_id, "limit": 1}
        
        # Próbujemy bez 'Bearer' na początku, bo Medal często tego nie wymaga
        headers = {
            "Authorization": api_key, 
            "Accept": "application/json"
        }

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=15) as resp:
                # --- DEBUG W KONSOLI ---
                print(f"\n--- MEDAL API DEBUG ---")
                print(f"Status: {resp.status}")
                raw_data = await resp.text()
                print(f"Response: {raw_data}")
                print(f"-----------------------\n")
                # -----------------------

                if resp.status != 200:
                    log.error(f"Błąd API Medal: {resp.status}")
                    return None
                
                data = await resp.json()
                clips = data.get("contentObjects", [])
                return clips[0] if clips else None
        except Exception as e:
            log.error(f"Wyjątek podczas zapytania do Medal: {e}")
            return None

    @tasks.loop(minutes=5)
    async def check_medal(self):
        api_data = await self.bot.get_shared_api_tokens("medal")
        api_key = api_data.get("api_key")
        
        if not api_key:
            return

        all_guilds = await self.config.all_guilds()
        for guild_id, settings in all_guilds.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            user_id = settings["medal_user_id"]
            channel_id = settings["channel_id"]
            last_id = settings["last_content_id"]

            if not user_id or not channel_id:
                continue

            clip = await self.fetch_latest_clip(api_key, user_id)
            if not clip:
                continue

            content_id = clip.get("contentId")
            if content_id == last_id:
                continue

            channel = guild.get_channel(channel_id)
            if channel:
                clip_url = clip.get("directClipUrl") or clip.get("url")
                await channel.send(f"🎬 **Nowy klip na Medal!**\n{clip_url}")
                await self.config.guild(guild).last_content_id.set(content_id)

    @check_medal.before_loop
    async def before_check_medal(self):
        await self.bot.wait_until_ready()

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def medal(self, ctx):
        """Zarządzanie modułem Medal.tv"""
        if ctx.invoked_subcommand is None:
            api_data = await self.bot.get_shared_api_tokens("medal")
            if not api_data.get("api_key"):
                prefix = ctx.clean_prefix
                await ctx.send(f"⚠️ Brak klucza API! Użyj: `{prefix}set api medal api_key,KLUCZ`")

    @medal.command()
    async def userid(self, ctx, user_id: int):
        """Ustaw ID użytkownika z Medal.tv"""
        await self.config.guild(ctx.guild).medal_user_id.set(user_id)
        await ctx.send(f"✅ Ustawiono Medal User ID na: `{user_id}`")

    @medal.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Ustaw kanał dla klipów"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Kanał ustawiony na {channel.mention}")

    @medal.command()
    async def test(self, ctx):
        """Testuj połączenie i wyświetl debug w konsoli"""
        conf = self.config.guild(ctx.guild)
        user_id = await conf.medal_user_id()
        api_data = await self.bot.get_shared_api_tokens("medal")
        api_key = api_data.get("api_key")

        if not api_key or not user_id:
            return await ctx.send("❌ Brakuje API key lub User ID. Sprawdź konsolę bota po teście.")

        await ctx.send("⏳ Łączę z API Medal... sprawdź konsolę bota.")
        
        async with ctx.typing():
            clip = await self.fetch_latest_clip(api_key, user_id)
            
            if clip:
                url = clip.get("directClipUrl") or clip.get("url")
                await ctx.send(f"✅ Sukces! Najnowszy klip: {url}")
            else:
                await ctx.send("❌ Nie udało się pobrać klipu. Szczegóły błędu znajdziesz w konsoli (terminalu) bota.")

async def setup(bot):
    await bot.add_cog(Medal(bot))
