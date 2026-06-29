import discord
import time
import sqlite3
from typing import Optional, Tuple, Dict
from database import execute_query, fetch_one, fetch_all
from config import logger

async def handle_vc_routing(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    # 1. Processing Join events
    if after.channel is not None:
        guild_id = member.guild.id
        cfg = fetch_one(
            "SELECT create_channel_id, category_id FROM voice_config WHERE guild_id = ?", 
            (guild_id,)
        )
        
        if cfg and cfg[0] == after.channel.id:
            category_id = cfg[1]
            category = member.guild.get_channel(category_id) if category_id else None
            
            # Default dynamic target criteria parameters
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(manage_channels=True, move_members=True, mute_members=True, deafen_members=True)
            }
            
            try:
                vc_name = f"{member.display_name}'s VC"
                new_channel = await member.guild.create_voice_channel(
                    name=vc_name,
                    category=category,  # type: ignore
                    overwrites=overwrites
                )
                
                # Track ownership configurations
                execute_query(
                    "INSERT INTO active_vcs (channel_id, guild_id, owner_id, creation_time) VALUES (?, ?, ?, ?)",
                    (new_channel.id, guild_id, member.id, int(time.time()))
                )
                
                # Instantly port user over to their space
                await member.move_to(new_channel)
                logger.info(f"Created temporary voice channel '{vc_name}' for {member}")
            except Exception as e:
                logger.error(f"Error parsing temporary voice generation runtime: {e}")

    # 2. Processing Leave events/Cleanup cycles
    if before.channel is not None:
        vc_id = before.channel.id
        track = fetch_one("SELECT channel_id FROM active_vcs WHERE channel_id = ?", (vc_id,))
        if track:
            # Check remaining functional user payloads inside target
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temporary Voice Channel Empty")
                    execute_query("DELETE FROM active_vcs WHERE channel_id = ?", (vc_id,))
                    execute_query("DELETE FROM vc_overrides WHERE channel_id = ?", (vc_id,))
                    logger.info(f"Cleaned up empty temporary voice channel: {vc_id}")
                except Exception as e:
                    logger.error(f"Error cleaning up old operational VCs: {e}")
                  
