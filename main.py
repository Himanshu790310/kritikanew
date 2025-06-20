import os
import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update
import google.generativeai as genai
from google.cloud import secretmanager
import google.cloud.logging

# --- Cloud Logging Setup ---
client = google.cloud.logging.Client()
client.setup_logging()

# --- Logger Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('EnglishTeachingBot')

# --- Configuration Management ---
class Config:
    def __init__(self):
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.PROJECT_ID:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set")
        
        self.TELEGRAM_BOT_TOKEN = self._get_secret("TELEGRAM_BOT_TOKEN")
        self.GOOGLE_API_KEY = self._get_secret("GOOGLE_API_KEY")
        self._validate_config()

    def _get_secret(self, secret_name):
        """Retrieve secrets from Google Secret Manager with fallback to env vars"""
        # Try environment variables first
        env_value = os.getenv(secret_name)
        if env_value:
            return env_value
            
        # Fall back to Secret Manager
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.PROJECT_ID}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(name=name)
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logger.error(f"Failed to access secret {secret_name}: {e}")
            raise ValueError(f"Could not retrieve {secret_name}")

    def _validate_config(self):
        """Validate all required configurations"""
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not self.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required")

# Initialize configuration
try:
    config = Config()
except Exception as e:
    logger.critical(f"Configuration failed: {e}")
    raise

# --- Gemini AI Configuration ---
genai.configure(api_key=config.GOOGLE_API_KEY)

GENERATION_CONFIG = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2500,
}

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

SYSTEM_INSTRUCTION = """
# Role: Kritika - Friendly English Doubt Solver for Hindi Speakers

[Previous full system instruction here...]
"""

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest",
    generation_config=GENERATION_CONFIG,
    safety_settings=SAFETY_SETTINGS,
    system_instruction=SYSTEM_INSTRUCTION
)

# --- Conversation Management ---
class ConversationManager:
    def __init__(self):
        self.conversations = {}
        self.lock = asyncio.Lock()

    async def get_chat(self, chat_id):
        async with self.lock:
            if chat_id not in self.conversations:
                self.conversations[chat_id] = model.start_chat(history=[])
                logger.info(f"Started new chat session for {chat_id}")
            return self.conversations[chat_id]

conversation_manager = ConversationManager()

# --- Telegram Handlers ---
async def start(update: Update, context):
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        await conversation_manager.get_chat(chat_id)
        
        welcome_msg = (
            f"Namaste {user.first_name}! 🙏\n"
            "Main Kritika hoon - Himanshu sir ki teaching assistant.\n\n"
            "Aap mujhse poochh sakte hain:\n"
            "• English grammar ke sawal\n"
            "• Translation help (Hindi ↔ English)\n"
            "• Vocabulary doubts\n"
            "• Aur bhi koi bhi English-related problem!\n\n"
            "Bas apna doubt bhejiye... Main poori koshish karungi aapki madad karne ki! 💪"
        )
        await update.message.reply_text(welcome_msg)
        logger.info(f"Sent welcome message to {chat_id}")
    except Exception as e:
        logger.error(f"Error in start handler: {e}", exc_info=True)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "Kuch technical problem aa gayi hai. Hum team ko inform kar diya hai."
            )

async def handle_message(update: Update, context):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    if not user_message:
        logger.warning(f"Empty message from {chat_id}")
        return

    try:
        logger.info(f"Processing message from {chat_id}: {user_message[:50]}...")
        chat = await conversation_manager.get_chat(chat_id)
        response = chat.send_message(user_message)
        
        if response.text:
            await update.message.reply_text(response.text)
            logger.info(f"Sent response to {chat_id}")
        else:
            logger.error(f"Empty response from Gemini for {chat_id}")
            await update.message.reply_text("Maaf kijiye, main samjha nahi. Phir se try karein?")
            
    except Exception as e:
        logger.error(f"Error handling message for {chat_id}: {e}", exc_info=True)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "Kuch technical problem aa raha hai. Thodi der baad try karein."
            )

async def error_handler(update: Update, context):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=True)
    if update and update.effective_chat:
        await update.effective_chat.send_message(
            "Kuch technical problem aa gayi hai. Hum team ko inform kar diya hai."
        )

# --- Application Management ---
class BotApplication:
    def __init__(self):
        self.application = None
        self.running = False

    async def initialize(self):
        self.application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler('start', start))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        self.application.add_error_handler(error_handler)
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        self.running = True
        logger.info("Bot application initialized and running")

    async def shutdown(self):
        if self.application and self.running:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self.running = False
            logger.info("Bot application shut down")

    async def run_forever(self):
        while self.running:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Received shutdown signal")
                await self.shutdown()
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await self.shutdown()
                raise

# --- Main Execution ---
async def main():
    bot = BotApplication()
    try:
        await bot.initialize()
        await bot.run_forever()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        await bot.shutdown()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        await bot.shutdown()
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical failure: {e}", exc_info=True)
