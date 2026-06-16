import discord
from discord import app_commands
from discord.ext import commands
from database import execute_query, fetch_one
from ai.memory import memory_manager
from config import DEFAULT_MODEL

class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ai-chat", description="Enable autonomous conversation loop in a designated text channel.")
    @app_commands.describe(channel="Target channel for automatic AI responses.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_chat(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        execute_query("INSERT OR REPLACE INTO ai_channels (guild_id, channel_id, model) VALUES (?, ?, ?)", 
                      (interaction.guild_id, channel.id, DEFAULT_MODEL))
        await interaction.response.send_message(f"✅ AI Response Matrix fully routed to target {channel.mention}. Responses will trigger without prefixes.", ephemeral=False)

    @app_commands.command(name="ai-disable", description="Disable autonomous conversation processing inside this text window.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_disable(self, interaction: discord.Interaction) -> None:
        cfg = fetch_one("SELECT channel_id FROM ai_channels WHERE channel_id = ?", (interaction.channel_id,))
        if not cfg:
            await interaction.response.send_message("❌ This text channel does not possess active automation pipelines.", ephemeral=True)
            return
            
        execute_query("DELETE FROM ai_channels WHERE channel_id = ?", (interaction.channel_id,))
        memory_manager.clear_channel_context(interaction.channel_id) # type: ignore
        await interaction.response.send_message("🗑 Auto-response model mappings dropped. Content tracking cleared for this channel context block.", ephemeral=False)

    @app_commands.command(name="ai-status", description="Query current structural configurations status mapping values.")
    async def ai_status(self, interaction: discord.Interaction) -> None:
        cfg = fetch_one("SELECT model FROM ai_channels WHERE channel_id = ?", (interaction.channel_id,))
        if cfg:
            await interaction.response.send_message(f"🤖 **Status Monitoring Frame**: Autonomous conversation loops are tracking active in this pipeline via LLM infrastructure model target `{cfg[0]}`.", ephemeral=True)
        else:
            await interaction.response.send_message("⏸ **Status Monitoring Frame**: Automated message processors are currently resting for this runtime environment.", ephemeral=True)

    @app_commands.command(name="ai-reset-memory", description="Clear memory logs across conversation threads manually.")
    async def ai_reset_memory(self, interaction: discord.Interaction) -> None:
        memory_manager.clear_context(interaction.channel_id, interaction.user.id) # type: ignore
        await interaction.response.send_message("🧹 Local conversational history profiles associated with your structural trace tracking arrays have been purged.", ephemeral=True)

    @app_commands.command(name="ai-model", description="Update active LLM structural framework models.")
    @app_commands.describe(model_name="Target engine format variant designation model string value identifier.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_model(self, interaction: discord.Interaction, model_name: str) -> None:
        cfg = fetch_one("SELECT channel_id FROM ai_channels WHERE channel_id = ?", (interaction.channel_id,))
        if not cfg:
            await interaction.response.send_message("❌ Configure AI execution routing workflows inside this channel target layer prior to toggling platform configurations.", ephemeral=True)
            return
            
        execute_query("UPDATE ai_channels SET model = ? WHERE channel_id = ?", (model_name, interaction.channel_id))
        await interaction.response.send_message(f"🔄 Operational execution target model shifted successfully to value framework representation string identifier context: `{model_name}`", ephemeral=False)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
