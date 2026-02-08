from redbot.core import commands, Config
from discord.ext import tasks
import discord
import aiohttp


class Medal(commands.Cog):
    """Automatyczne klipy z Medal.tv"""

    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(
            api_key=None,
            medal_user_id=None,
            channel_id=None,
            last_content_id=None
        )

        self.check_medal.start()

    def cog_unload(self):
        self.check_medal.cancel()

    # =========================
    # BACKGROUND TASK
    # =========================
    @tasks.loop(minutes=5)
    async def check_medal(self):
        for guild in self.bot.guilds:
            conf = self.config.guild(guild)

            api_key = await conf.api_key()
            user_id = await conf.medal_user_id()
            channel_id = await conf.channel_id()
            last_id = await conf.last_content_id()

            if not all([api_key, user_id, channel_id]):
                continue

            clip = await self.fetch_latest_clip(api_key, user_id)
            if not clip:
                continue

            content_id = clip.get("contentId")
            clip_url = clip.get("directClipUrl")

            if not content_id or not clip_url:
                continue

            if content_id == last_id:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            await channel.send(f"🎬 **Nowy klip na Medal!**\n{clip_url}")
            await conf.last_content_id.set(content_id)

    @check_medal.before_loop
    async def before_check_medal(self):
        await self.bot.wait_until_ready()

    # =========================
    # MEDAL API
    # =========================
    async def fetch_latest_clip(self, api_key: str, user_id: int):
        url = "https://developers.medal.tv/v1/latest"
        params = {
            "userId": user_id,
            "limit": 1
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                print("=== MEDAL DEBUG ===")
                print("STATUS:", resp.status)
                text = await resp.text()
                print("RAW RESPONSE:", text)
                print("===================")

                if resp.status != 200:
                    return None

                data = await resp.json()
                clips = data.get("contentObjects", [])
                return clips[0] if clips else None

    # =========================
    # COMMANDS
    # =========================
    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def medal(self, ctx):
        """Konfiguracja Medal.tv"""
        pass

    @medal.command()
    async def apikey(self, ctx, key: str):
        await self.config.guild(ctx.guild).api_key.set(key)
        await ctx.send("✅ API key zapisany")

    @medal.command()
    async def userid(self, ctx, user_id: int):
        await self.config.guild(ctx.guild).medal_user_id.set(user_id)
        await ctx.send(f"✅ Medal userId ustawione na `{user_id}`")

    @medal.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"✅ Klipy będą wysyłane na {channel.mention}")

    @medal.command()
    async def test(self, ctx):
        conf = self.config.guild(ctx.guild)

        api_key = await conf.api_key()
        user_id = await conf.medal_user_id()

        if not api_key or not user_id:
            await ctx.send("❌ Najpierw ustaw `apikey` i `userid`")
            return

        clip = await self.fetch_latest_clip(api_key, user_id)
        if not clip:
            await ctx.send("❌ Nie udało się pobrać klipu (brak publicznych klipów lub błąd API)")
            return

        await ctx.send(clip.get("directClipUrl"))
