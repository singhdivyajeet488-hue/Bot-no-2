import discord
from typing import Optional, Tuple
from database import fetch_one, execute_query, fetch_all

def check_vc_ownership(user_id: int, channel: Optional[discord.VoiceChannel]) -> Tuple[bool, str]:
    if not channel:
        return False, "You are not connected to any voice session channel."
    
    res = fetch_one("SELECT owner_id FROM active_vcs WHERE channel_id = ?", (channel.id,))
    if not res:
        return False, "This channel is not an active managed temporary voice instance."
    
    if res[0] != user_id:
        return False, "Only the designated Voice Channel owner can adjust these configurations."
    
    return True, ""

async def apply_lock(channel: discord.VoiceChannel, lock: bool) -> None:
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.connect = False if lock else True
    await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)

async def apply_visibility(channel: discord.VoiceChannel, hide: bool) -> None:
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.view_channel = False if hide else True
    await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)

async def apply_user_override(channel: discord.VoiceChannel, target: discord.Member, override_type: str) -> None:
    overwrite = channel.overwrites_for(target)
    if override_type == "BAN":
        overwrite.connect = False
        overwrite.view_channel = False
        await channel.set_permissions(target, overwrite=overwrite)
        execute_query("INSERT OR REPLACE INTO vc_overrides (channel_id, user_id, type) VALUES (?, ?, 'BAN')", (channel.id, target.id))
        if target in channel.members:
            await target.move_to(None)
    elif override_type == "PERMIT":
        overwrite.connect = True
        overwrite.view_channel = True
        await channel.set_permissions(target, overwrite=overwrite)
        execute_query("INSERT OR REPLACE INTO vc_overrides (channel_id, user_id, type) VALUES (?, ?, 'PERMIT')", (channel.id, target.id))
    elif override_type == "RESET":
        await channel.set_permissions(target, overwrite=None)
        execute_query("DELETE FROM vc_overrides WHERE channel_id = ? AND user_id = ?", (channel.id, target.id))
      
