import discord
from discord.ext import commands
import asyncio
from config import DISCORD_TOKEN, logger
from database import init_db, fetch_one
from voice.manager import handle_vc_routing
from voice.views import VoiceControlPanelView
from ai.groq_client import generate_ai_response

# Initialization setup configurations
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

class VoiceAIBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        # Setup specific anti-spam mitigation mechanisms dictionary blocks tracking intervals
        self.ai_cooldowns: dict[int, float] = {}

    async def setup_hook(self) -> None:
        # Run database initialization steps profiles mapping tracking routines
        init_db()
        
        # Load extensions 
        await self.load_extension("commands.ai")
        await self.load_extension("commands.setup")
        await self.load_extension("commands.voice")
        
        # Register persistent control panel component views tracker to map callbacks dynamically across reboots
        self.add_view(VoiceControlPanelView())
        logger.info("Persistent View bindings successfully registered inside application hook profiles.")

    async def on_ready(self) -> None:
        logger.info(f"Successfully online and identified as user framework profile target: {self.user} (ID: {self.user.id if self.user else 0})")
        try:
            synced = await self.tree.sync()
            logger.info(f"Application synchronization complete. Root mapping tree references logged: {len(synced)} components.")
        except Exception as e:
            logger.error(f"Error executing global configuration parameters interface tree update tracks sync: {e}")

bot = VoiceAIBot()

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    # Route voice infrastructure layout events directly to state machine tracker processing channels
    await handle_vc_routing(member, before, after)

@bot.event
async def on_message(message: discord.Message) -> None:
    # 1. Verification filter passes
    if message.author.bot:
        return
        
    # Ignore slash commands interactions matching content patterns directly
    if message.content.startswith("/") or message.content.startswith("!"):
        return

    # Check if text location window tracks active automatic configuration items
    cfg = fetch_one("SELECT model FROM ai_channels WHERE channel_id = ?", (message.channel.id,))
    if cfg:
        model_name = cfg[0]
        current_time = asyncio.get_event_loop().time()
        last_triggered = bot.ai_cooldowns.get(message.channel.id, 0.0)
        
        # Anti-spam interval threshold barrier (2.0-second delay throttle)
        if current_time - last_triggered < 2.0:
            return
            
        bot.ai_cooldowns[message.channel.id] = current_time
        
        try:
            async with message.channel.typing():
                chunks = await generate_ai_response(
                    channel_id=message.channel.id,
                    user_id=message.author.id,
                    user_name=message.author.display_name,
                    prompt=message.content,
                    model_name=model_name
                )
                for chunk in chunks:
                    if chunk.strip():
                        await message.reply(chunk, mention_author=False)
        except Exception as e:
            logger.error(f"Failed to cleanly deliver AI inference reply payload: {e}")

async def main() -> None:
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot application shutdown initialized manually by operator framework signals.")
      
