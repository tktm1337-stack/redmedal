from redbot.core import commands, Config, checks
from discord.ext import tasks
import discord
import aiohttp

class Medal(commands.Cog):
    """Automatyczne klipy z Medal.tv"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "medal_user_id": None,
            "channel_id": None,
            "last_content_id": None
        }
        self.config.register_guild(**default_guild)
        
        # Tworzymy jedną sesję dla całego coga
        self.session = aiohttp.ClientSession()
        self.check_medal.start()

    def cog_unload(self):
        self.check_medal.cancel()
        # Zamykamy sesję przy wyłączaniu bota/coga
        self.bot.loop.create_task(self.session.close())

    async def fetch_latest_clip(self, api_key: str, user_id: int):
        url = "https://developers.medal.tv/v1/latest"
        params = {"userId": user_id, "limit": 1}
        headers = {
            "Authorization": f"Bearer {api_key}", # Zmienione na Bearer lub samo api_key zależnie od dok. Medal
            "Accept": "application/json"
        }

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                clips = data.get("contentObjects", [])
                return clips[0] if clips else None
        except Exception:
            return None

    @tasks.loop(minutes=5)
    async def check_medal(self):
        # Pobieramy klucz API z globalnego magazynu Reda
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
        """Konfiguracja Medal.tv"""
        if ctx.invoked_subcommand is None:
            # Instrukcja ustawiania API key
            prefix = ctx.clean_prefix
            msg = (
                "Aby bot działał, administrator bota musi ustawić klucz API komendą:\n"
                f"`{prefix}set api medal api_key,TWÓJ_KLUCZ`"
            )
            await ctx.send(msg)

    @medal.command()
    async def userid(self, ctx, user_id: int):
        """Ustaw ID użytkownika Medal"""
        await self.config.guild(ctx.guild).medal_user_id.set(user_id)
        await ctx.tick()

    @medal.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Ustaw kanał do wysyłania klipów"""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Klipy będą wysyłane na {channel.mention}")

    @medal.command()
        async def test(self, ctx):
            """Sprawdź czy konfiguracja działa i pobierz ostatni klip"""
            conf = self.config.guild(ctx.guild)
            user_id = await conf.medal_user_id()
        
            # Pobieramy klucz API z systemu Reda
            api_data = await self.bot.get_shared_api_tokens("medal")
            api_key = api_data.get("api_key")

            if not api_key:
                prefix = ctx.clean_prefix
                return await ctx.send(f"❌ Brak klucza API! Ustaw go wpisując:\n`{prefix}set api medal api_key,TWÓJ_KLUCZ`")

            if not user_id:
                return await ctx.send("❌ Najpierw ustaw ID użytkownika za pomocą `[p]medal userid`.")

            async with ctx.typing():
                clip = await self.fetch_latest_clip(api_key, user_id)
            
                if not clip:
                    return await ctx.send("❌ Nie udało się pobrać klipu. Sprawdź czy profil jest publiczny i czy ID jest poprawne.")

                clip_url = clip.get("directClipUrl") or clip.get("url")
                await ctx.send(f"✅ Test udany! Najnowszy klip:\n{clip_url}")
