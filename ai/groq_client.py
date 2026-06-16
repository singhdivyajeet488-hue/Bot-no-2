import discord
from groq import AsyncGroq
from config import GROQ_API_KEY, DEFAULT_MODEL, logger
from ai.memory import memory_manager
from typing import List, Dict

try:
    groq_client = AsyncGroq(api_key=GROQ_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Groq Client: {e}")
    groq_client = None

async def generate_ai_response(channel_id: int, user_id: int, user_name: str, prompt: str, model_name: str = DEFAULT_MODEL) -> List[str]:
    if not groq_client:
        return ["Groq API Client is currently uninitialized or misconfigured."]
    
    # Retrieve structural thread memory
    history = memory_manager.get_context(channel_id, user_id)
    
    system_prompt = {
        "role": "system",
        "content": f"You are an advanced AI companion in a Discord server. You are talking to {user_name}. Keep your answers direct, natural, conversational, and avoid long-winded system notes."
    }
    
    messages: List[Dict[str, str]] = [system_prompt] + history + [{"role": "user", "content": prompt}]
    
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=messages,
            model=model_name,
            max_tokens=1200,
            temperature=0.7
        )
        
        # Save validated interaction back to chat log
        response_text = chat_completion.choices[0].message.content or ""
        memory_manager.add_message(channel_id, user_id, "user", prompt)
        memory_manager.add_message(channel_id, user_id, "assistant", response_text)
        
        # Slice up to chunk lengths safely fitting within Discord boundaries
        return chunk_text(response_text, 1950)
        
    except Exception as e:
        logger.error(f"Error executing Chat Completion on Groq: {e}")
        return [f"⚠️ An error occurred during inference initialization: `{str(e)}`"]

def chunk_text(text: str, limit: int = 1950) -> List[str]:
    if len(text) <= limit:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Split nicely at a newline space or space boundaries where possible
        split_idx = text.rfind("\n", 0, limit)
        if split_idx == -1:
            split_idx = text.rfind(" ", 0, limit)
        if split_idx == -1:
            split_idx = limit
            
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    return chunks
  
