import discord
from discord import app_commands
from discord.ext import commands
from database import execute_query, fetch_one
from voice.views import VoiceControlPanelView, generate_panel_embed

class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="vc-setup", description="Designate primary dynamic target connection channels for creation mappings.")
    @app_commands.describe(create_channel="Voice channel that acts as the 'Join to Create' anchor.")
    @app_commands.checks.has_permissions(administrator=True)
    async def vc_setup(self, interaction: discord.Interaction, create_channel: discord.VoiceChannel) -> None:
        guild_id = interaction.guild_id
        cfg = fetch_one("SELECT guild_id FROM voice_config WHERE guild_id = ?", (guild_id,))
        
        if not cfg:
            execute_query("INSERT INTO voice_config (guild_id, create_channel_id) VALUES (?, ?)", (guild_id, create_channel.id))
        else:
            execute_query("UPDATE voice_config SET create_channel_id = ? WHERE guild_id = ?", (create_channel.id, guild_id))
            
        await interaction.response.send_message(f"⚙ Setup channel initialization maps assigned across destination node identifier: {create_channel.mention}", ephemeral=False)

    @app_commands.command(name="vc-category", description="Specify default target functional layout location constraints for runtime creation components.")
    @app_commands.describe(category="The category under which temporary VCs will be created.")
    @app_commands.checks.has_permissions(administrator=True)
    async def vc_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        guild_id = interaction.guild_id
        cfg = fetch_one("SELECT guild_id FROM voice_config WHERE guild_id = ?", (guild_id,))
        
        if not cfg:
            execute_query("INSERT INTO voice_config (guild_id, category_id) VALUES (?, ?)", (guild_id, category.id))
        else:
            execute_query("UPDATE voice_config SET category_id = ? WHERE guild_id = ?", (category.id, guild_id))
            
        await interaction.response.send_message(f"📂 Execution parent node constraints set to folder structures map: `{category.name}`", ephemeral=False)

    @app_commands.command(name="vc-interface", description="Deploy permanent panel control views tracking automation parameters.")
    @app_commands.describe(channel="Text channel where the control panel will be deployed.")
    @app_commands.checks.has_permissions(administrator=True)
    async def vc_interface(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        
        cfg = fetch_one("SELECT interface_channel_id, interface_message_id FROM voice_config WHERE guild_id = ?", (guild_id,))
        
        if cfg and cfg[0] and cfg[1]:
            try:
                old_chan = interaction.guild.get_channel(cfg[0]) # type: ignore
                if isinstance(old_chan, discord.TextChannel):
                    old_msg = await old_chan.fetch_message(cfg[1])
                    await old_msg.delete()
            except Exception:
                pass 

        embed = generate_panel_embed()
        view = VoiceControlPanelView()
        
        panel_msg = await channel.send(embed=embed, view=view)
        
        execute_query(
            "UPDATE voice_config SET interface_channel_id = ?, interface_message_id = ? WHERE guild_id = ?",
            (channel.id, panel_msg.id, guild_id)
        )
        
        await interaction.followup.send(f"📟 Management control interfaces deployed to channel {channel.mention}.", ephemeral=True)

    @app_commands.command(name="vc-status", description="Inspect configurations infrastructure setups across the localized domain layer.")
    @app_commands.checks.has_permissions(administrator=True)
    async def vc_status(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        cfg = fetch_one("SELECT create_channel_id, category_id, interface_channel_id FROM voice_config WHERE guild_id = ?", (guild_id,))
        
        if not cfg:
            await interaction.response.send_message("❌ Operational system data profiles are completely unconfigured for this guild structure layout.", ephemeral=True)
            return
            
        cc = interaction.guild.get_channel(cfg[0]) if cfg[0] else "Not Defined"
        cat = interaction.guild.get_channel(cfg[1]) if cfg[1] else "Not Defined"
        ic = interaction.guild.get_channel(cfg[2]) if cfg[2] else "Not Defined"
        
        embed = discord.Embed(title="⚙ Voice System Core Diagnostics", color=discord.Color.blue())
        embed.add_field(name="Generator Target Root", value=getattr(cc, 'mention', f"`{cc}`"), inline=False)
        embed.add_field(name="Target Generation Folder Layer", value=f"`{getattr(cat, 'name', str(cat))}`", inline=False)
        embed.add_field(name="Panel Location Interface Tracking", value=getattr(ic, 'mention', f"`{ic}`"), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
  
