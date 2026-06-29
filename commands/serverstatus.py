import asyncio
import time
import re
import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────
MC_STATUS_API    = "https://api.mcsrvstat.us/3/{host}"
EMBED_COLOR_ON   = 0x57F287
EMBED_COLOR_OFF  = 0xED4245
EMBED_COLOR_ERR  = 0x99AAB5
REQUEST_TIMEOUT  = 8
REFRESH_INTERVAL = 30  # seconds

MC_FORMAT_RE = re.compile(r"§[0-9a-fk-or]", re.IGNORECASE)


def strip_mc_formatting(text: str) -> str:
    return MC_FORMAT_RE.sub("", text).strip()


def parse_motd(motd_data) -> str:
    if motd_data is None:
        return "No MOTD"
    if isinstance(motd_data, str):
        return strip_mc_formatting(motd_data) or "No MOTD"
    lines = motd_data.get("clean") or motd_data.get("raw") or []
    joined = "\n".join(lines) if isinstance(lines, list) else str(lines)
    return strip_mc_formatting(joined) or "No MOTD"


async def fetch_server_data(ip: str):
    """Returns (data_dict, error_str). One of them will be None."""
    url = MC_STATUS_API.format(host=ip)
    try:
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("`aiohttp` is not installed.")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": "FrostWarden-Discord-Bot/1.0"}
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"API returned HTTP {resp.status}")
                data = await resp.json(content_type=None)
        return data, None
    except Exception as exc:
        return None, str(exc)


def build_cooldown_bar(seconds_left: int, total: int = REFRESH_INTERVAL) -> str:
    """Returns a visual progress bar + countdown label."""
    filled = total - seconds_left
    bar_len = 20
    filled_blocks = round((filled / total) * bar_len)
    bar = "█" * filled_blocks + "░" * (bar_len - filled_blocks)
    return f"`[{bar}]` — Next refresh in **{seconds_left}s**"


def build_online_embed(ip: str, data: dict, seconds_left: int) -> tuple:
    players_online = data.get("players", {}).get("online", 0)
    players_max    = data.get("players", {}).get("max", 0)
    version        = data.get("version", "Unknown")
    motd           = parse_motd(data.get("motd"))

    favicon_data_uri = data.get("icon")
    favicon_file = None
    if favicon_data_uri and favicon_data_uri.startswith("data:image/png;base64,"):
        try:
            import base64, io
            img_bytes = base64.b64decode(favicon_data_uri.split(",", 1)[1])
            favicon_file = discord.File(io.BytesIO(img_bytes), filename="favicon.png")
        except Exception:
            favicon_file = None

    embed = discord.Embed(title="🟢  Server Online", color=EMBED_COLOR_ON)
    embed.add_field(name="🖥  Server IP", value=f"`{ip}`",                           inline=False)
    embed.add_field(name="👥  Players",   value=f"`{players_online}/{players_max}`",  inline=True)
    embed.add_field(name="📡  Ping",      value="`N/A`",                              inline=True)
    embed.add_field(name="🎮  Version",   value=f"`{version}`",                       inline=True)
    embed.add_field(name="📝  MOTD",      value=f"```{motd}```",                      inline=False)
    embed.add_field(name="🟢  Status",    value="`Online`",                           inline=True)
    embed.add_field(
        name="🔄  Auto-Refresh",
        value=build_cooldown_bar(seconds_left),
        inline=False
    )

    if favicon_file:
        embed.set_thumbnail(url="attachment://favicon.png")

    return embed, favicon_file


def build_offline_embed(ip: str, seconds_left: int) -> discord.Embed:
    embed = discord.Embed(
        title="🔴  Server Offline",
        description=(
            f"**`{ip}`** is currently **offline** or unreachable.\n"
            "Double-check the address or try again later."
        ),
        color=EMBED_COLOR_OFF
    )
    embed.add_field(
        name="🔄  Auto-Refresh",
        value=build_cooldown_bar(seconds_left),
        inline=False
    )
    return embed


# ─────────────────────────────────────────────
#  Refresh loop — one per active status message
# ─────────────────────────────────────────────
class StatusRefresher:
    """
    Runs a background loop that:
      - Edits the embed with a live countdown every second
      - Fetches fresh server data and rebuilds the embed every 30 s
    """

    def __init__(self, ip: str, channel: discord.TextChannel, message_id: int,
                 initial_data: dict | None):
        self.ip = ip
        self.channel = channel
        self.message_id = message_id
        # Cache the last known server data so we can update the bar without re-fetching
        self._last_data: dict | None = initial_data
        self._last_online: bool = initial_data is not None and initial_data.get("online", False)
        self._task = asyncio.create_task(self._loop())

    async def _edit_message(self, msg: discord.Message, seconds_left: int):
        """Rebuild embed with updated countdown and edit the Discord message."""
        if self._last_online and self._last_data:
            embed, favicon_file = build_online_embed(self.ip, self._last_data, seconds_left)
            if favicon_file:
                await msg.edit(embed=embed, attachments=[favicon_file])
            else:
                await msg.edit(embed=embed, attachments=[])
        else:
            embed = build_offline_embed(self.ip, seconds_left)
            await msg.edit(embed=embed, attachments=[])

    async def _loop(self):
        try:
            while True:
                # ── One full 30-second cycle ──────────────────────────────
                for seconds_left in range(REFRESH_INTERVAL, 0, -1):
                    await asyncio.sleep(1)

                    try:
                        msg = await self.channel.fetch_message(self.message_id)
                    except (discord.NotFound, discord.Forbidden):
                        return  # message deleted — stop the loop

                    await self._edit_message(msg, seconds_left)

                # ── Time to refresh server data ───────────────────────────
                try:
                    msg = await self.channel.fetch_message(self.message_id)
                except (discord.NotFound, discord.Forbidden):
                    return

                data, error = await fetch_server_data(self.ip)

                if error or data is None or not data.get("online", False):
                    self._last_online = False
                    self._last_data = None
                else:
                    self._last_online = True
                    self._last_data = data

                # Show full bar right after the fetch (30 s to next refresh)
                await self._edit_message(msg, REFRESH_INTERVAL)

        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def cancel(self):
        self._task.cancel()


# ─────────────────────────────────────────────
#  Cog
# ─────────────────────────────────────────────
class ServerStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._refreshers: list[StatusRefresher] = []

    @app_commands.command(
        name="serverstatus",
        description="Fetch the live status of a Minecraft Java Edition server."
    )
    @app_commands.describe(ip="Server IP address (e.g. play.hypixel.net)")
    async def serverstatus(self, interaction: discord.Interaction, ip: str) -> None:
        await interaction.response.defer()

        ip = ip.strip()
        if not ip:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Please provide a valid server IP.", color=EMBED_COLOR_ERR)
            )
            return

        data, error = await fetch_server_data(ip)

        if error:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️  Error fetching server status",
                description=f"**Server:** `{ip}`\n**Reason:** {error}",
                color=EMBED_COLOR_ERR
            ))
            return

        online: bool = data.get("online", False) if data else False

        if not online:
            embed = build_offline_embed(ip, REFRESH_INTERVAL)
            webhook_msg = await interaction.followup.send(embed=embed, wait=True)
        else:
            embed, favicon_file = build_online_embed(ip, data, REFRESH_INTERVAL)
            if favicon_file:
                webhook_msg = await interaction.followup.send(embed=embed, file=favicon_file, wait=True)
            else:
                webhook_msg = await interaction.followup.send(embed=embed, wait=True)

        # Fetch the real Message object so we can edit it later
        real_msg = await interaction.channel.fetch_message(webhook_msg.id)

        # Start background refresh with initial data cached
        refresher = StatusRefresher(
            ip=ip,
            channel=interaction.channel,
            message_id=real_msg.id,
            initial_data=data if online else None,
        )
        self._refreshers.append(refresher)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStatusCog(bot))
