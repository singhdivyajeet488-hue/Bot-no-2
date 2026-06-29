import discord
from discord import app_commands
from discord.ext import commands
from database import fetch_one
from voice.controls import check_vc_ownership, apply_lock, apply_visibility

class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="vc-lock", description="Secure connection gates manually via prompt processing executions.")
    async def vc_lock(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if isinstance(member, discord.Member) and member.voice and member.voice.channel:
            channel = member.voice.channel
            status, msg = check_vc_ownership(member.id, channel) # type: ignore
            if status:
                await apply_lock(channel, True) # type: ignore
                await interaction.response.send_message("🔒 Session access parameters locked securely via manual parameter prompt overrides.", ephemeral=True)
                return
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ensure active tracking connectivity to targeted session configurations instances before processing.", ephemeral=True)

    @app_commands.command(name="vc-unlock", description="Release connection constraints across the workspace nodes manually.")
    async def vc_unlock(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if isinstance(member, discord.Member) and member.voice and member.voice.channel:
            channel = member.voice.channel
            status, msg = check_vc_ownership(member.id, channel) # type: ignore
            if status:
                await apply_lock(channel, False) # type: ignore
                await interaction.response.send_message("🔓 Session parameters opened up safely for connection routing tracks.", ephemeral=True)
                return
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Ensure active tracking connectivity to targeted session configurations instances before processing.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
