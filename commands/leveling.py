import discord
from discord import app_commands
from discord.ext import commands, tasks
from database import execute_query, fetch_one, fetch_all
from config import logger
import time
import math
import random
import asyncio
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════════
#  XP CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
MSG_XP_MIN          = 15
MSG_XP_MAX          = 25
MSG_XP_COOLDOWN     = 60        # seconds cooldown between message XP grants
VOICE_XP_PER_TICK   = 10        # XP per voice tick
VOICE_TICK_INTERVAL = 60        # seconds per tick
VOICE_MIN_MEMBERS   = 1         # min non-bot members in VC to earn XP

# ═══════════════════════════════════════════════════════════════════════════════
#  XP MATH
# ═══════════════════════════════════════════════════════════════════════════════
def xp_for_level(level: int) -> int:
    """Total XP required to reach `level` from zero."""
    if level <= 0:
        return 0
    return math.floor(100 * (level ** 1.65))

def level_from_xp(xp: int) -> int:
    level = 0
    while xp >= xp_for_level(level + 1):
        level += 1
        if level >= 100:
            break
    return level

def xp_progress(xp: int) -> tuple[int, int, int]:
    """Returns (current_level, xp_into_level, xp_needed_for_next)."""
    level          = level_from_xp(xp)
    floor          = xp_for_level(level)
    next_floor     = xp_for_level(level + 1)
    return level, xp - floor, next_floor - floor

def progress_bar(filled: int, total: int, width: int = 20) -> str:
    if total <= 0:
        pct = 1.0
    else:
        pct = min(filled / total, 1.0)
    n = int(pct * width)
    return "█" * n + "░" * (width - n)

# ═══════════════════════════════════════════════════════════════════════════════
#  DB HELPERS — users
# ═══════════════════════════════════════════════════════════════════════════════
def ensure_user(guild_id: int, user_id: int) -> None:
    execute_query(
        """INSERT OR IGNORE INTO levels
           (guild_id, user_id, xp, total_xp, level, last_msg_xp,
            msg_xp, voice_xp, msg_count, voice_minutes)
           VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)""",
        (guild_id, user_id),
    )

def get_user_row(guild_id: int, user_id: int) -> dict:
    row = fetch_one(
        """SELECT xp, total_xp, level, msg_xp, voice_xp,
                  msg_count, voice_minutes
           FROM levels WHERE guild_id = ? AND user_id = ?""",
        (guild_id, user_id),
    )
    if not row:
        return dict(xp=0, total_xp=0, level=0, msg_xp=0,
                    voice_xp=0, msg_count=0, voice_minutes=0.0)
    return dict(xp=row[0], total_xp=row[1], level=row[2],
                msg_xp=row[3], voice_xp=row[4],
                msg_count=row[5], voice_minutes=float(row[6]))

def _add_xp_internal(
    guild_id: int, user_id: int, amount: int,
    source: str  # "msg" or "voice"
) -> tuple[int, int, bool]:
    """
    Adds XP from the given source. Returns (old_level, new_level, leveled_up).
    """
    ensure_user(guild_id, user_id)
    d = get_user_row(guild_id, user_id)
    old_level  = d["level"]
    new_xp     = d["xp"] + amount
    new_total  = d["total_xp"] + amount
    new_level  = level_from_xp(new_xp)
    leveled_up = new_level > old_level

    if source == "msg":
        execute_query(
            """UPDATE levels
               SET xp=?, total_xp=?, level=?,
                   msg_xp = msg_xp + ?,
                   msg_count = msg_count + 1
               WHERE guild_id=? AND user_id=?""",
            (new_xp, new_total, new_level, amount, guild_id, user_id),
        )
    else:
        execute_query(
            """UPDATE levels
               SET xp=?, total_xp=?, level=?,
                   voice_xp = voice_xp + ?
               WHERE guild_id=? AND user_id=?""",
            (new_xp, new_total, new_level, amount, guild_id, user_id),
        )
    return old_level, new_level, leveled_up

def add_voice_minutes(guild_id: int, user_id: int, minutes: float) -> None:
    ensure_user(guild_id, user_id)
    execute_query(
        "UPDATE levels SET voice_minutes = voice_minutes + ? WHERE guild_id=? AND user_id=?",
        (minutes, guild_id, user_id),
    )

def set_user_xp_raw(guild_id: int, user_id: int, xp: int) -> None:
    ensure_user(guild_id, user_id)
    level = level_from_xp(xp)
    execute_query(
        """UPDATE levels SET xp=?, total_xp=?, level=?
           WHERE guild_id=? AND user_id=?""",
        (xp, xp, level, guild_id, user_id),
    )

def wipe_user(guild_id: int, user_id: int) -> None:
    execute_query(
        """UPDATE levels
           SET xp=0, total_xp=0, level=0, last_msg_xp=0,
               msg_xp=0, voice_xp=0, msg_count=0, voice_minutes=0
           WHERE guild_id=? AND user_id=?""",
        (guild_id, user_id),
    )

def rank_in_guild(guild_id: int, user_id: int, by: str = "xp") -> int:
    col = {"xp": "xp", "msg": "msg_xp", "voice": "voice_xp"}.get(by, "xp")
    rows = fetch_all(
        f"SELECT user_id FROM levels WHERE guild_id=? ORDER BY {col} DESC",
        (guild_id,),
    )
    return next((i + 1 for i, r in enumerate(rows) if r[0] == user_id), 0)

# ═══════════════════════════════════════════════════════════════════════════════
#  DB HELPERS — guild config
# ═══════════════════════════════════════════════════════════════════════════════
def ensure_level_config(guild_id: int) -> None:
    execute_query(
        "INSERT OR IGNORE INTO level_config (guild_id) VALUES (?)",
        (guild_id,),
    )

def get_levelup_channel(guild_id: int) -> Optional[int]:
    row = fetch_one("SELECT levelup_channel_id FROM level_config WHERE guild_id=?", (guild_id,))
    return row[0] if row and row[0] else None

def get_leaderboard_info(guild_id: int) -> tuple[Optional[int], Optional[int]]:
    row = fetch_one(
        "SELECT leaderboard_channel_id, leaderboard_message_id FROM level_config WHERE guild_id=?",
        (guild_id,),
    )
    return (row[0], row[1]) if row else (None, None)

# ═══════════════════════════════════════════════════════════════════════════════
#  DB HELPERS — role rewards
# ═══════════════════════════════════════════════════════════════════════════════
def get_role_rewards(guild_id: int) -> list[tuple[int, int]]:
    """Returns list of (level, role_id) sorted ascending."""
    return fetch_all(
        "SELECT level, role_id FROM level_roles WHERE guild_id=? ORDER BY level ASC",
        (guild_id,),
    )

def set_role_reward(guild_id: int, level: int, role_id: int) -> None:
    execute_query(
        "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
        (guild_id, level, role_id),
    )

def remove_role_reward(guild_id: int, level: int) -> bool:
    row = fetch_one(
        "SELECT role_id FROM level_roles WHERE guild_id=? AND level=?",
        (guild_id, level),
    )
    if not row:
        return False
    execute_query(
        "DELETE FROM level_roles WHERE guild_id=? AND level=?",
        (guild_id, level),
    )
    return True

# ═══════════════════════════════════════════════════════════════════════════════
#  ROLE REWARD APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
async def apply_level_roles(member: discord.Member, new_level: int) -> Optional[discord.Role]:
    """
    Awards the highest earned role, removes lower ones.
    Returns the newly awarded role if any, else None.
    """
    guild   = member.guild
    rewards = get_role_rewards(guild.id)
    if not rewards:
        return None

    earned_role_id: Optional[int] = None
    for lvl, role_id in rewards:
        if new_level >= lvl:
            earned_role_id = role_id

    all_reward_ids = {r[1] for r in rewards}

    to_remove = [r for r in member.roles if r.id in all_reward_ids and r.id != earned_role_id]
    if to_remove:
        try:
            await member.remove_roles(*to_remove, reason="Level role update")
        except discord.Forbidden:
            logger.warning(f"No perms to remove level roles from {member.id}")

    newly_added: Optional[discord.Role] = None
    if earned_role_id:
        target = guild.get_role(earned_role_id)
        if target and target not in member.roles:
            try:
                await member.add_roles(target, reason=f"Reached level {new_level}")
                newly_added = target
            except discord.Forbidden:
                logger.warning(f"No perms to assign role {earned_role_id} to {member.id}")
    return newly_added

# ═══════════════════════════════════════════════════════════════════════════════
#  EMBEDS
# ═══════════════════════════════════════════════════════════════════════════════
def build_levelup_embed(
    member: discord.Member,
    new_level: int,
    new_xp: int,
    role_reward: Optional[discord.Role],
) -> discord.Embed:
    level, xp_in, xp_needed = xp_progress(new_xp)
    bar = progress_bar(xp_in, xp_needed)

    embed = discord.Embed(
        title="⬆️  Level Up!",
        description=f"{member.mention} just reached **Level {new_level}**! 🎉",
        color=0x5865F2,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="XP Progress",
        value=f"`{bar}` {xp_in:,} / {xp_needed:,}",
        inline=False,
    )
    if role_reward:
        embed.add_field(name="🎁 Role Unlocked", value=role_reward.mention, inline=False)

    # show next role
    rewards = get_role_rewards(member.guild.id)
    next_entry = next(((lvl, rid) for lvl, rid in rewards if lvl > new_level), None)
    if next_entry:
        next_role = member.guild.get_role(next_entry[1])
        if next_role:
            embed.add_field(
                name="🔜 Next Role",
                value=f"{next_role.mention} at Level **{next_entry[0]}**",
                inline=False,
            )
    embed.set_footer(text=f"Total XP: {new_xp:,}")
    return embed


def build_stats_embed(member: discord.Member, d: dict, guild: discord.Guild) -> discord.Embed:
    """Statbot-style /stats card."""
    level, xp_in, xp_needed = xp_progress(d["xp"])
    bar = progress_bar(xp_in, xp_needed)
    pct = (xp_in / xp_needed * 100) if xp_needed else 100.0

    msg_rank   = rank_in_guild(guild.id, member.id, "msg")
    voice_rank = rank_in_guild(guild.id, member.id, "voice")
    xp_rank    = rank_in_guild(guild.id, member.id, "xp")

    voice_hrs  = d["voice_minutes"] / 60.0
    voice_str  = f"{voice_hrs:.2f} hrs" if voice_hrs >= 1 else f"{d['voice_minutes']:.0f} min"

    embed = discord.Embed(
        title=f"📊  {member.display_name}",
        color=0x2B2D31,
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Top stat row
    embed.add_field(name="Level", value=f"`{level}`", inline=True)
    embed.add_field(name="XP Rank", value=f"`#{xp_rank}`", inline=True)
    embed.add_field(name="Total XP", value=f"`{d['xp']:,}`", inline=True)

    # Progress bar
    embed.add_field(
        name=f"Progress to Level {level + 1}",
        value=f"`{bar}` {xp_in:,} / {xp_needed:,} ({pct:.1f}%)",
        inline=False,
    )

    # Messages section
    embed.add_field(
        name="💬  Messages",
        value=f"Rank: `#{msg_rank}`\nMessages: `{d['msg_count']:,}`\nXP: `{d['msg_xp']:,}`",
        inline=True,
    )

    # Voice section
    embed.add_field(
        name="🔊  Voice Activity",
        value=f"Rank: `#{voice_rank}`\nTime: `{voice_str}`\nXP: `{d['voice_xp']:,}`",
        inline=True,
    )

    # Role rewards info
    rewards = get_role_rewards(guild.id)
    next_entry = next(((lvl, rid) for lvl, rid in rewards if lvl > level), None)
    if next_entry:
        next_role = guild.get_role(next_entry[1])
        if next_role:
            embed.add_field(
                name="🎯  Next Role",
                value=f"{next_role.mention} at Level **{next_entry[0]}**",
                inline=False,
            )

    embed.set_footer(text=f"Server: {guild.name}  •  Joined: {member.joined_at.strftime('%b %d, %Y') if member.joined_at else 'Unknown'}")
    return embed


def build_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    """
    Split leaderboard: Voice (left) | Messages (right).
    """
    voice_rows = fetch_all(
        """SELECT user_id, voice_xp, voice_minutes FROM levels
           WHERE guild_id=? ORDER BY voice_xp DESC LIMIT 10""",
        (guild.id,),
    )
    msg_rows = fetch_all(
        """SELECT user_id, msg_xp, msg_count FROM levels
           WHERE guild_id=? ORDER BY msg_xp DESC LIMIT 10""",
        (guild.id,),
    )

    medals = ["🥇", "🥈", "🥉"]

    def voice_line(i: int, row: tuple) -> str:
        uid, vxp, vmin = row
        m     = guild.get_member(uid)
        name  = (m.display_name if m else f"User {uid}")[:16]
        hrs   = vmin / 60.0
        time_ = f"{hrs:.1f}h" if hrs >= 1 else f"{vmin:.0f}m"
        pre   = medals[i] if i < 3 else f"`#{i+1}`"
        return f"{pre} **{name}**\n└ `{time_}` · `{vxp:,} XP`"

    def msg_line(i: int, row: tuple) -> str:
        uid, mxp, mc = row
        m    = guild.get_member(uid)
        name = (m.display_name if m else f"User {uid}")[:16]
        pre  = medals[i] if i < 3 else f"`#{i+1}`"
        return f"{pre} **{name}**\n└ `{mc:,} msgs` · `{mxp:,} XP`"

    voice_text = "\n".join(voice_line(i, r) for i, r in enumerate(voice_rows)) or "_No data yet._"
    msg_text   = "\n".join(msg_line(i, r)   for i, r in enumerate(msg_rows))   or "_No data yet._"

    embed = discord.Embed(title=f"🏆  {guild.name} — Leaderboard", color=0xFFD700)
    embed.add_field(name="🔊  Top Voice Members", value=voice_text, inline=True)
    embed.add_field(name="💬  Top Message Members", value=msg_text,  inline=True)
    embed.set_footer(text="Refreshes every 30 seconds")
    return embed


def build_levelroles_embed(guild: discord.Guild) -> discord.Embed:
    rewards = get_role_rewards(guild.id)
    embed   = discord.Embed(title="🎖️  Level Role Rewards", color=0x5865F2)
    if not rewards:
        embed.description = "_No role rewards configured._\nUse `/levelrole add <level> <role>`."
        return embed
    lines = []
    for lvl, rid in rewards:
        role = guild.get_role(rid)
        lines.append(f"Level **{lvl}** → {role.mention if role else f'`[deleted role {rid}]`'}")
    embed.description = "\n".join(lines)
    return embed

# ═══════════════════════════════════════════════════════════════════════════════
#  COG
# ═══════════════════════════════════════════════════════════════════════════════
class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._msg_cooldowns:   dict[tuple[int, int], float] = {}
        self._voice_sessions:  dict[tuple[int, int], float] = {}
        self._voice_xp_loop.start()
        self._leaderboard_refresh.start()

    def cog_unload(self) -> None:
        self._voice_xp_loop.cancel()
        self._leaderboard_refresh.cancel()

    # ── Level-up pipeline ───────────────────────────────────────────────
    async def _handle_levelup(
        self,
        guild: discord.Guild,
        member: discord.Member,
        new_level: int,
        new_xp: int,
        fallback_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        role_reward = await apply_level_roles(member, new_level)
        ch_id       = get_levelup_channel(guild.id)
        ch          = guild.get_channel(ch_id) if ch_id else fallback_channel
        if ch and isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=build_levelup_embed(member, new_level, new_xp, role_reward))
            except discord.Forbidden:
                pass

    # ── Message XP ──────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if message.content.startswith(("/", "!")):
            return

        guild_id = message.guild.id
        user_id  = message.author.id
        key      = (guild_id, user_id)
        now      = time.time()

        if now - self._msg_cooldowns.get(key, 0.0) < MSG_XP_COOLDOWN:
            return
        self._msg_cooldowns[key] = now

        grant = random.randint(MSG_XP_MIN, MSG_XP_MAX)
        old_lvl, new_lvl, leveled_up = _add_xp_internal(guild_id, user_id, grant, "msg")
        execute_query(
            "UPDATE levels SET last_msg_xp=? WHERE guild_id=? AND user_id=?",
            (now, guild_id, user_id),
        )

        if leveled_up:
            d      = get_user_row(guild_id, user_id)
            new_xp = d["xp"]
            fb     = message.channel if isinstance(message.channel, discord.TextChannel) else None
            await self._handle_levelup(message.guild, message.author, new_lvl, new_xp, fb)  # type: ignore

    # ── Voice XP ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        key = (member.guild.id, member.id)

        if after.channel and not before.channel:
            self._voice_sessions[key] = time.time()

        elif before.channel and not after.channel:
            join_time = self._voice_sessions.pop(key, None)
            if join_time:
                elapsed   = time.time() - join_time
                ticks     = int(elapsed / VOICE_TICK_INTERVAL)
                minutes   = elapsed / 60.0
                if ticks > 0:
                    grant = ticks * VOICE_XP_PER_TICK
                    add_voice_minutes(member.guild.id, member.id, minutes)
                    old_lvl, new_lvl, leveled_up = _add_xp_internal(
                        member.guild.id, member.id, grant, "voice"
                    )
                    if leveled_up:
                        d      = get_user_row(member.guild.id, member.id)
                        new_xp = d["xp"]
                        fb     = next(
                            (c for c in member.guild.text_channels
                             if c.permissions_for(member.guild.me).send_messages),
                            None,
                        )
                        await self._handle_levelup(member.guild, member, new_lvl, new_xp, fb)

    @tasks.loop(seconds=VOICE_TICK_INTERVAL)
    async def _voice_xp_loop(self) -> None:
        now = time.time()
        for (guild_id, user_id) in list(self._voice_sessions):
            guild  = self.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(user_id)
            if not member or not member.voice or not member.voice.channel:
                self._voice_sessions.pop((guild_id, user_id), None)
                continue
            vc = member.voice.channel
            if sum(1 for m in vc.members if not m.bot) < VOICE_MIN_MEMBERS:
                continue

            add_voice_minutes(guild_id, user_id, VOICE_TICK_INTERVAL / 60.0)
            old_lvl, new_lvl, leveled_up = _add_xp_internal(
                guild_id, user_id, VOICE_XP_PER_TICK, "voice"
            )
            self._voice_sessions[(guild_id, user_id)] = now

            if leveled_up:
                d      = get_user_row(guild_id, user_id)
                new_xp = d["xp"]
                fb     = next(
                    (c for c in guild.text_channels
                     if c.permissions_for(guild.me).send_messages),
                    None,
                )
                await self._handle_levelup(guild, member, new_lvl, new_xp, fb)

    @_voice_xp_loop.before_loop
    async def _before_voice_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── Live leaderboard refresh ─────────────────────────────────────────
    @tasks.loop(seconds=30)
    async def _leaderboard_refresh(self) -> None:
        for guild in self.bot.guilds:
            ch_id, msg_id = get_leaderboard_info(guild.id)
            if not ch_id or not msg_id:
                continue
            ch = guild.get_channel(ch_id)
            if not isinstance(ch, discord.TextChannel):
                continue
            try:
                msg = await ch.fetch_message(msg_id)
                await msg.edit(embed=build_leaderboard_embed(guild))
            except (discord.NotFound, discord.Forbidden):
                pass

    @_leaderboard_refresh.before_loop
    async def _before_lb_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════════════════════════════════
    #  SLASH COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    # ── /stats ──────────────────────────────────────────────────────────
    @app_commands.command(name="stats", description="View your stats card — level, XP, messages, and voice time.")
    @app_commands.describe(member="Member to look up (defaults to you).")
    async def stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        target = member or interaction.user
        ensure_user(interaction.guild_id, target.id)  # type: ignore
        d = get_user_row(interaction.guild_id, target.id)  # type: ignore
        await interaction.response.send_message(
            embed=build_stats_embed(target, d, interaction.guild),  # type: ignore
            ephemeral=False,
        )

    # ── /rank ────────────────────────────────────────────────────────────
    @app_commands.command(name="rank", description="Check your current level, XP rank, and progress bar.")
    @app_commands.describe(member="User to look up (defaults to you).")
    async def rank(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        target = member or interaction.user
        ensure_user(interaction.guild_id, target.id)  # type: ignore
        d       = get_user_row(interaction.guild_id, target.id)  # type: ignore
        xp_rank = rank_in_guild(interaction.guild_id, target.id, "xp")  # type: ignore

        level, xp_in, xp_needed = xp_progress(d["xp"])
        bar = progress_bar(xp_in, xp_needed)
        pct = (xp_in / xp_needed * 100) if xp_needed else 100.0

        embed = discord.Embed(
            title=f"📊  Rank Card — {target.display_name}",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level",   value=f"`{level}`",    inline=True)
        embed.add_field(name="Rank",    value=f"`#{xp_rank}`", inline=True)
        embed.add_field(name="XP",      value=f"`{d['xp']:,}`", inline=True)
        embed.add_field(
            name="Progress to Next Level",
            value=f"`{bar}` {xp_in:,} / {xp_needed:,} ({pct:.1f}%)",
            inline=False,
        )
        rewards = get_role_rewards(interaction.guild_id)  # type: ignore
        next_e  = next(((lvl, rid) for lvl, rid in rewards if lvl > level), None)
        if next_e:
            nr = interaction.guild.get_role(next_e[1])  # type: ignore
            if nr:
                embed.add_field(
                    name="Next Role At",
                    value=f"{nr.mention} at Level **{next_e[0]}**",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ─────────────────────────────────────────────────────
    @app_commands.command(name="leaderboard", description="View the server leaderboard (voice left, messages right).")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=build_leaderboard_embed(interaction.guild),  # type: ignore
        )

    # ── /setlevelchannel ─────────────────────────────────────────────────
    @app_commands.command(name="setlevelchannel", description="[Admin] Set the channel where level-up messages are posted.")
    @app_commands.describe(channel="The text channel for level-up announcements.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevelchannel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        ensure_level_config(interaction.guild_id)  # type: ignore
        execute_query(
            "UPDATE level_config SET levelup_channel_id=? WHERE guild_id=?",
            (channel.id, interaction.guild_id),
        )
        await interaction.response.send_message(
            f"✅ Level-up messages will now be sent to {channel.mention}.", ephemeral=True
        )

    # ── /setleaderboard ──────────────────────────────────────────────────
    @app_commands.command(name="setleaderboard", description="[Admin] Post a live leaderboard in a channel (auto-refreshes every 30s).")
    @app_commands.describe(channel="The text channel to post the live leaderboard in.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setleaderboard(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id

        # Delete old leaderboard message if exists
        ch_id, msg_id = get_leaderboard_info(guild_id)  # type: ignore
        if ch_id and msg_id:
            old_ch = interaction.guild.get_channel(ch_id)  # type: ignore
            if isinstance(old_ch, discord.TextChannel):
                try:
                    old_msg = await old_ch.fetch_message(msg_id)
                    await old_msg.delete()
                except Exception:
                    pass

        msg = await channel.send(embed=build_leaderboard_embed(interaction.guild))  # type: ignore

        ensure_level_config(guild_id)  # type: ignore
        execute_query(
            """UPDATE level_config
               SET leaderboard_channel_id=?, leaderboard_message_id=?
               WHERE guild_id=?""",
            (channel.id, msg.id, guild_id),
        )
        await interaction.followup.send(
            f"✅ Live leaderboard posted in {channel.mention} — refreshes every 30 seconds.",
            ephemeral=True,
        )

    # ── /levelrole group ─────────────────────────────────────────────────
    levelrole = app_commands.Group(
        name="levelrole",
        description="Manage role rewards for reaching certain levels.",
    )

    @levelrole.command(name="add", description="Assign a role reward to a level (1–100).")
    @app_commands.describe(level="Level that triggers this role (1–100).", role="Role to award.")
    @app_commands.checks.has_permissions(administrator=True)
    async def levelrole_add(self, interaction: discord.Interaction, level: int, role: discord.Role) -> None:
        if not 1 <= level <= 100:
            await interaction.response.send_message("❌ Level must be between 1 and 100.", ephemeral=True)
            return
        set_role_reward(interaction.guild_id, level, role.id)  # type: ignore
        await interaction.response.send_message(
            f"✅ {role.mention} will be awarded at Level **{level}**.", ephemeral=True
        )

    @levelrole.command(name="remove", description="Remove a role reward from a level.")
    @app_commands.describe(level="Level to remove the role reward from.")
    @app_commands.checks.has_permissions(administrator=True)
    async def levelrole_remove(self, interaction: discord.Interaction, level: int) -> None:
        removed = remove_role_reward(interaction.guild_id, level)  # type: ignore
        if removed:
            await interaction.response.send_message(f"✅ Role reward removed from Level **{level}**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No role reward set for Level **{level}**.", ephemeral=True)

    @levelrole.command(name="list", description="List all configured level role rewards.")
    async def levelrole_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=build_levelroles_embed(interaction.guild),  # type: ignore
            ephemeral=True,
        )

    # ── /setxp ───────────────────────────────────────────────────────────
    @app_commands.command(name="setxp", description="[Admin] Manually set a member's XP.")
    @app_commands.describe(member="Target member.", amount="Raw XP value to set.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, amount: int) -> None:
        if amount < 0:
            await interaction.response.send_message("❌ XP can't be negative.", ephemeral=True)
            return
        set_user_xp_raw(interaction.guild_id, member.id, amount)  # type: ignore
        level = level_from_xp(amount)
        await apply_level_roles(member, level)
        await interaction.response.send_message(
            f"✅ Set **{member.display_name}**'s XP to `{amount:,}` (Level `{level}`).",
            ephemeral=True,
        )

    # ── /resetxp ─────────────────────────────────────────────────────────
    @app_commands.command(name="resetxp", description="[Admin] Wipe a member's XP and level to zero.")
    @app_commands.describe(member="Target member.")
    @app_commands.checks.has_permissions(administrator=True)
    async def resetxp(self, interaction: discord.Interaction, member: discord.Member) -> None:
        wipe_user(interaction.guild_id, member.id)  # type: ignore
        await apply_level_roles(member, 0)
        await interaction.response.send_message(
            f"🗑️ Reset **{member.display_name}**'s XP and level to zero.",
            ephemeral=True,
        )

    # ── Error handler ────────────────────────────────────────────────────
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Administrator permission required.", ephemeral=True
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))
