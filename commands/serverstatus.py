import time
import re
import discord
from discord import app_commands
from discord.ext import commands

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────
MC_STATUS_API   = "https://api.mcsrvstat.us/3/{host}"  # mcsrvstat.us v3 — reliable, supports SRV
EMBED_COLOR_ON  = 0x57F287   # Discord green
EMBED_COLOR_OFF = 0xED4245   # Discord red
EMBED_COLOR_ERR = 0x99AAB5   # Grey for errors
REQUEST_TIMEOUT = 8           # seconds

# Regex strips Minecraft § colour / formatting codes from MOTDs
MC_FORMAT_RE = re.compile(r"§[0-9a-fk-or]", re.IGNORECASE)


def strip_mc_formatting(text: str) -> str:
    """Remove Minecraft legacy colour codes (§X) from a string."""
    return MC_FORMAT_RE.sub("", text).strip()


def parse_motd(motd_data: dict | str | None) -> str:
    """
    mcsrvstat v3 returns motd as:
      { "raw": ["line1", "line2"], "clean": ["line1", "line2"], "html": [...] }
    We prefer 'clean' (already stripped), fall back to 'raw'.
    """
    if motd_data is None:
        return "No MOTD"

    if isinstance(motd_data, str):
        return strip_mc_formatting(motd_data) or "No MOTD"

    # Prefer clean lines (no colour codes)
    lines = motd_data.get("clean") or motd_data.get("raw") or []
    if isinstance(lines, list):
        joined = "\n".join(lines)
    else:
        joined = str(lines)

    return strip_mc_formatting(joined) or "No MOTD"


# ─────────────────────────────────────────────
#  Cog
# ─────────────────────────────────────────────
class ServerStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="serverstatus",
        description="Fetch the live status of a Minecraft Java Edition server."
    )
    @app_commands.describe(ip="Server IP address (e.g. play.hypixel.net or play.example.com:25565)")
    async def serverstatus(self, interaction: discord.Interaction, ip: str) -> None:
        """
        /serverstatus ip:<server_ip>
        Returns a rich embed with player count, version, MOTD, ping, TPS,
        and server icon — or a red offline embed if the server is unreachable.
        """
        # Defer immediately — API call can take a moment
        await interaction.response.defer()

        # ── Validate / sanitise the IP string ──────────────────────────────
        ip = ip.strip()
        if not ip:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Please provide a valid server IP.",
                    color=EMBED_COLOR_ERR
                )
            )
            return

        # ── Query the status API ────────────────────────────────────────────
        url = MC_STATUS_API.format(host=ip)
        t_start = time.monotonic()

        try:
            if not AIOHTTP_AVAILABLE:
                raise RuntimeError(
                    "`aiohttp` is not installed. Run `pip install aiohttp` and restart the bot."
                )

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    headers={"User-Agent": "FrostWarden-Discord-Bot/1.0"}
                ) as resp:
                    if resp.status != 200:
                        raise ValueError(f"API returned HTTP {resp.status}")
                    data: dict = await resp.json(content_type=None)

        except aiohttp.ClientConnectorError:
            await interaction.followup.send(embed=self._error_embed(ip, "Could not reach the status API. Check your internet connection."))
            return
        except aiohttp.ServerTimeoutError:
            await interaction.followup.send(embed=self._error_embed(ip, "The status API timed out. Try again in a moment."))
            return
        except Exception as exc:
            await interaction.followup.send(embed=self._error_embed(ip, str(exc)))
            return

        api_latency_ms = round((time.monotonic() - t_start) * 1000)

        # ── Build the embed ─────────────────────────────────────────────────
        online: bool = data.get("online", False)

        if not online:
            embed = discord.Embed(
                title="🔴  Server Offline",
                description=(
                    f"**`{ip}`** is currently **offline** or unreachable.\n"
                    "Double-check the address or try again later."
                ),
                color=EMBED_COLOR_OFF
            )
            embed.set_footer(text=f"API response time: {api_latency_ms} ms  •  Powered by mcsrvstat.us")
            await interaction.followup.send(embed=embed)
            return

        # ── Parse fields ────────────────────────────────────────────────────
        players_online = data.get("players", {}).get("online", 0)
        players_max    = data.get("players", {}).get("max", 0)

        version        = data.get("version", "Unknown")

        motd_raw       = data.get("motd")
        motd           = parse_motd(motd_raw)

        # Ping: mcsrvstat doesn't expose raw TCP ping, so we use our API RTT
        ping_ms        = api_latency_ms

        # TPS: only available via plugins (e.g. Paper/Purpur) — not in the API
        tps            = "Unavailable"

        # Favicon: mcsrvstat returns a base64 data URI ("data:image/png;base64,...").
        # Discord embed thumbnail URLs do NOT accept data URIs, so we decode the
        # bytes and upload the image as a file attachment, then reference it via
        # the special "attachment://favicon.png" protocol.
        favicon_data_uri: str | None = data.get("icon")
        favicon_file: discord.File | None = None

        if favicon_data_uri and favicon_data_uri.startswith("data:image/png;base64,"):
            try:
                import base64, io
                raw_b64 = favicon_data_uri.split(",", 1)[1]
                img_bytes = base64.b64decode(raw_b64)
                favicon_file = discord.File(io.BytesIO(img_bytes), filename="favicon.png")
            except Exception:
                favicon_file = None  # silently skip on any decode error

        # ── Compose embed ────────────────────────────────────────────────────
        embed = discord.Embed(
            title="🟢  Server Online",
            color=EMBED_COLOR_ON
        )

        embed.add_field(name="🖥  Server IP",   value=f"`{ip}`",                          inline=False)
        embed.add_field(name="👥  Players",      value=f"`{players_online}/{players_max}`", inline=True)
        embed.add_field(name="⚡  TPS",          value=f"`{tps}`",                          inline=True)
        embed.add_field(name="📡  Ping",         value=f"`{ping_ms} ms`",                   inline=True)
        embed.add_field(name="🎮  Version",      value=f"`{version}`",                      inline=True)
        embed.add_field(name="📝  MOTD",         value=f"```{motd}```",                     inline=False)
        embed.add_field(name="🟢  Status",       value="`Online`",                          inline=True)
        embed.add_field(name="\u200b",           value="\u200b",                            inline=False)  # spacer
        embed.add_field(
            name="\u2501" * 22,  # ━━━━━━━━━━━━━━━━━━━━━━
            value=f"API response time: **{api_latency_ms} ms**",
            inline=False
        )

        embed.set_footer(text="Powered by mcsrvstat.us  •  Minecraft Java Edition")

        # Reference the attached file as thumbnail (attachment:// works for uploaded files)
        if favicon_file:
            embed.set_thumbnail(url="attachment://favicon.png")
            await interaction.followup.send(embed=embed, file=favicon_file)
        else:
            await interaction.followup.send(embed=embed)

    # ── Helper ──────────────────────────────────────────────────────────────
    @staticmethod
    def _error_embed(ip: str, reason: str) -> discord.Embed:
        """Return a generic error embed."""
        embed = discord.Embed(
            title="⚠️  Error fetching server status",
            description=f"**Server:** `{ip}`\n**Reason:** {reason}",
            color=EMBED_COLOR_ERR
        )
        embed.set_footer(text="Powered by mcsrvstat.us")
        return embed


# ─────────────────────────────────────────────
#  Extension entry-point
# ─────────────────────────────────────────────
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStatusCog(bot))
