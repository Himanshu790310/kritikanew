import os
import logging
import asyncio
import signal
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update
import google.generativeai as genai
from google.cloud import secretmanager
import google.cloud.logging

# ======================
# LOGGING CONFIGURATION
# ======================
try:
    # Set up Google Cloud Logging
    logging_client = google.cloud.logging.Client()
    logging_client.setup_logging()
except Exception as e:
    print(f"Could not set up Cloud Logging: {e}")

# Configure basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('EnglishTeachingBot')

# ======================
# CONFIGURATION MANAGER
# ======================
class Config:
    def __init__(self):
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.PROJECT_ID:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set")
        
        self.TELEGRAM_BOT_TOKEN = self._get_secret("TELEGRAM_BOT_TOKEN")
        self.GOOGLE_API_KEY = self._get_secret("GOOGLE_API_KEY")
        self._validate_config()

    def _get_secret(self, secret_name):
        """Retrieve secrets from Google Secret Manager or environment variables"""
        # Try environment variables first
        env_value = os.getenv(secret_name)
        if env_value:
            logger.info(f"Using {secret_name} from environment variables")
            return env_value
            
        # Fall back to Secret Manager
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.PROJECT_ID}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(name=name)
            logger.info(f"Successfully retrieved {secret_name} from Secret Manager")
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
        logger.info("Configuration validation successful")

# Initialize configuration
try:
    config = Config()
    logger.info("Configuration initialized successfully")
except Exception as e:
    logger.critical(f"Configuration failed: {e}")
    raise

# ======================
# GEMINI AI SETUP
# ======================
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

## Core Identity:
You are Kritika, Himanshu's teaching assistant specializing in helping Hindi speakers with English. Your personality:
- Warm and encouraging like a favorite elder sister
- Patient and clear in explanations
- Culturally aware of Indian contexts
- Focused on practical language help

## Primary Functions:
1. *Doubt Solving*:
   - Explain grammar concepts in simple Hinglish
   - Help with translations (Hindi ↔ English)
   - Clarify vocabulary and phrases
   - Provide examples from daily Indian life

2. *Teaching Support*:
   - Assist Himanshu's students with their questions
   - Break down complex concepts into easy steps
   - Create quick practice exercises when requested

## Communication Style:
- *Language Preference*: 
   - 90% Hindi (Roman script) + 10% English
   - Examples: "Present perfect tense ko samjhiye...", "Is sentence mein error kya hai?"
- *Tone*: 
   - Friendly and supportive: "Chinta mat karo, main hoon na!"
   - Encouraging: "Aapne bahut accha try kiya!"
   - Respectful: "Aapka sawal accha hai..."

## Teaching Methodology:
1. *Concept Explanation*:
   - Hindi explanation first (Roman script)
   - English structure/formula
   - 2-3 simple examples
   - Contrast with Hindi structure

2. *Error Correction*:
   - Gently point out mistakes: "Yahan thoda sa correction chahiye..."
   - Show correct version: "Shayad aap ye kehna chahte the..."
   - Always provide reasoning: "Kyuki plural subject ke saath 'are' aata hai"

3. *Practical Help*:
   - Real-life usage examples
   - Short practice exercises (only when asked)
   - Pronunciation tips with Hindi phonetics

## Special Features:
- *Instant Help*: 
   - When user says "help" or "samjhao":
     1. Simplify concept
     2. Give 2 relatable examples
     3. Offer alternative explanations
     
- *Cultural Connection*:
   - Use Indian examples: "Jaise ki 'I'm going to market' ki jagah 'I'm going to the market' bolna sahi hai"
   - Explain Western concepts in Indian context

## Prohibitions:
- No fixed curriculum or daily tasks
- No word-for-word translations
- No romantic/political/religious examples
- Don't overwhelm with information

## Interaction Principles:
- Prioritize user's immediate needs
- Keep responses conversational and personal
- Use emojis sparingly (👍✨💡)
- Always end with: "Aur koi doubt hai?" or "Mai aur madad kar sakti hoon?"
"""

try:
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        generation_config=GENERATION_CONFIG,
        safety_settings=SAFETY_SETTINGS,
        system_instruction=SYSTEM_INSTRUCTION
    )
    logger.info("Gemini model initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize Gemini model: {e}")
    raise

# ======================
# CONVERSATION MANAGER
# ======================
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

    async def cleanup(self):
        async with self.lock:
            self.conversations.clear()
            logger.info("Cleared all conversation sessions")

conversation_manager = ConversationManager()

# ======================
# TELEGRAM HANDLERS
# ======================
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

# ======================
# APPLICATION MANAGEMENT
# ======================
class BotApplication:
    def __init__(self):
        self.application = None
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        try:
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
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}")
            raise

    async def shutdown(self):
        if self.running:
            try:
                logger.info("Starting shutdown sequence...")
                await conversation_manager.cleanup()
                
                if self.application:
                    await self.application.updater.stop()
                    await self.application.stop()
                    await self.application.shutdown()
                
                self.running = False
                self.shutdown_event.set()
                logger.info("Bot application shut down successfully")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
                raise

    async def run_forever(self):
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.shutdown())
            )
        
        try:
            while self.running and not self.shutdown_event.is_set():
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Received shutdown signal")
            await self.shutdown()
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            await self.shutdown()
            raise

# ======================
# MAIN EXECUTION
# ======================
async def main():
    bot = BotApplication()
    try:
        await bot.initialize()
        await bot.run_forever()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        if bot.running:
            await bot.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical failure: {e}", exc_info=True)
        raise
