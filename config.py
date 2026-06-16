import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("VoiceAIBot")

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

DEFAULT_MODEL: str = "llama3-8b-8192"
DATABASE_PATH: str = "data/database.db"

if not DISCORD_TOKEN or not GROQ_API_KEY:
    logger.warning("Environment variables DISCORD_TOKEN or GROQ_API_KEY are missing!")
