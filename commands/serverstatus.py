import time
import re
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

# Minecraft §-code stripper (§0–§9, §a–§f, §k–§r, §x + hex colour sequences)
_MC_CODE_RE = re.compile(r"§(?:x(?:§[0-9a-fA-F]){6}|[0-9a-fA-Fk-orK-OR])")

def strip_mc_codes(text: str) -> str:
    """Remove Minecraft formatting / colour codes from a string."""
    return _MC_CODE_RE.sub("", text).strip()


def parse_motd(motd_raw) -> str:
    """
    Accept the MOTD field returned by mcsrvstat.us (string or dict with 'raw' list).
    Returns a clean, human-readable string.
    """
    if isinstance(motd_raw, dict):
        # mcsrvstat returns {"raw": ["line1", "line2"], "clean": ["…"], "html": "…"}
        lines = motd_raw.get("clean") or motd_raw.get("raw") or []
        text = "\n".join(lines)
    elif isinstance(motd_raw, str):
        text = motd_raw
    else:
        return "N/A"
    return strip_mc_codes(text) or "N/A"


# ─────────────────────────────────────────────
#  API fetch
# ─────────────────────────────────────────────

API_BASE = "https://api.mcsrvstat.us/3/{address}"
TIMEOUT  = aiohttp.ClientTimeout(total=8)   # 8-second hard cap


async def fetch_server_status(address: str) -> dict:
    """
    Query mcsrvstat.us for a Java edition server.
    Returns the parsed JSON dict plus a synthetic 'response_ms' key.
    Raises aiohttp.ClientError or asyncio.TimeoutError on failure.
    """
    url = API_BASE.format(address=address)

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        t0 = time.monotonic()
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        elapsed_ms = round((time.monotonic() - t0) * 1000)

    data["response_ms"] = elapsed_ms
    return data


# ─────────────────────────────────────────────
#  Embed builders
# ─────────────────────────────────────────────

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"

def build_online_embed(address: str, data: dict) -> discord.Embed:
    """Construct the 'server online' embed from the API payload."""
    players_online = data.get("players", {}).get("online", 0)
    players_max    = data.get("players", {}).get("max", 0)
    version        = data.get("version", "Unknown")
    motd           = parse_motd(data.get("motd", ""))
    ping_ms        = data.get("response_ms", "N/A")
    favicon        = data.get("icon")          # base-64 PNG data-URI or None
    tps_raw        = data.get("info", {}).get("tps") if data.get("info") else None

    # TPS: some servers expose it via the info block; fall back gracefully
    if tps_raw is not None:
        tps_display = f"{tps_raw:.1f}" if isinstance(tps_raw, float) else str(tps_raw)
    else:
        tps_display = "Unavailable"

    embed = discord.Embed(
        title="🟢  Server Online",
        color=discord.Color.green(),
    )

    # Field order matches the specification exactly
    embed.add_field(name="🖥  Server IP",  value=f"`{address}`",               inline=False)
    embed.add_field(name="👥  Players",    value=f"`{players_online}/{players_max}`", inline=True)
    embed.add_field(name="⚡  TPS",        value=f"`{tps_display}`",           inline=True)
    embed.add_field(name="📡  Ping",       value=f"`{ping_ms} ms`",            inline=True)
    embed.add_field(name="🎮  Version",    value=f"`{version}`",               inline=False)
    embed.add_field(name="📝  MOTD",       value=f"```{motd}```",              inline=False)
    embed.add_field(name="\u200b",         value=DIVIDER,                      inline=False)

    # Attach the server's favicon as the embed thumbnail when available
    if favicon:
        embed.set_thumbnail(url=favicon)

    embed.set_footer(text="Powered by mcsrvstat.us  •  FrostWarden")
    return embed


def build_offline_embed(address: str) -> discord.Embed:
    """Construct the 'server offline / unreachable' embed."""
    embed = discord.Embed(
        title="🔴  Server Offline",
        description=(
            f"**`{address}`** could not be reached.\n"
            "The server may be offline, the IP may be invalid, or it is blocking status pings."
        ),
        color=discord.Color.red(),
    )
    embed.add_field(name="\u200b", value=DIVIDER, inline=False)
    embed.set_footer(text="Powered by mcsrvstat.us  •  FrostWarden")
    return embed


# ─────────────────────────────────────────────
#  Cog
# ─────────────────────────────────────────────

class ServerStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="serverstatus",
        description="Fetch the live status of a Minecraft Java server.",
    )
    @app_commands.describe(ip="Server address, e.g. play.hypixel.net or play.example.com:25565")
    async def serverstatus(self, interaction: discord.Interaction, ip: str) -> None:
        # Acknowledge immediately so Discord doesn't time out while we call the API
        await interaction.response.defer(thinking=True)

        # ── Basic input sanitisation ──────────────────────────────────────
        address = ip.strip().lower()
        if not address:
            await interaction.followup.send("❌ Please provide a valid server IP address.", ephemeral=True)
            return

        # ── API call ──────────────────────────────────────────────────────
        try:
            data = await fetch_server_status(address)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # Network-level failure → treat as offline
            await interaction.followup.send(embed=build_offline_embed(address))
            return
        except Exception as exc:
            await interaction.followup.send(
                f"❌ An unexpected error occurred while contacting the status API: `{exc}`",
                ephemeral=True,
            )
            return

        # ── Build and send the appropriate embed ──────────────────────────
        if data.get("online"):
            embed = build_online_embed(address, data)
        else:
            embed = build_offline_embed(address)

        await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────────
#  Extension entry-point
# ─────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStatusCog(bot))
