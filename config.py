import os
import logging
from dotenv import load_dotenv

# Load local environment variables if testing locally
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

# Core authorization tokens pulled securely from environment variables
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# FIXED: Hardcoded to use the supported 3.1 model right out of the box
DEFAULT_MODEL: str = "llama-3.1-8b-instant"
DATABASE_PATH: str = "data/database.db"

# Safety sanity check warning for server deployment
if not DISCORD_TOKEN or not GROQ_API_KEY:
    logger.warning("Environment variables DISCORD_TOKEN or GROQ_API_KEY are missing!")
