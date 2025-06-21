import os
import logging
import asyncio
import signal
from threading import Thread
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram import Update, Bot
import google.generativeai as genai
from google.cloud import secretmanager
import google.cloud.logging

# ======================
# FASTAPI APP SETUP
# ======================
app = FastAPI()

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "english-teaching-bot"}

@app.on_event("startup")
async def startup():
    logger.info("Service initializing...")
    try:
        # Initialize critical components
        genai.configure(api_key=config.GOOGLE_API_KEY)
        logger.info("Service initialized successfully")
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise HTTPException(status_code=500, detail="Service initialization failed")

@app.get("/ready")
async def readiness_check():
    try:
        # Add any readiness checks here
        return {"ready": True}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Endpoint for Telegram webhook updates"""
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, bot_instance)
        await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080))

async def start_http_server():
    Thread(target=run_fastapi, daemon=True).start()

# ======================
# LOGGING CONFIGURATION
# ======================
try:
    logging_client = google.cloud.logging.Client()
    logging_client.setup_logging()
    logger = logging.getLogger('EnglishTeachingBot')
    logger.setLevel(logging.INFO)
except Exception as e:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger('EnglishTeachingBot')
    logger.warning(f"Could not set up Cloud Logging: {e}")

# ======================
# CONFIGURATION MANAGER
# ======================
class Config:
    def __init__(self):
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")
        self.TELEGRAM_BOT_TOKEN = self._get_secret("TELEGRAM_BOT_TOKEN")
        self.GOOGLE_API_KEY = self._get_secret("GOOGLE_API_KEY")
        self.WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
        self._validate_config()
        logger.info("Configuration loaded successfully")

    def _get_secret(self, secret_name):
        """Retrieve secrets from Google Secret Manager or environment variables"""
        env_value = os.getenv(secret_name)
        if env_value:
            logger.info(f"Using {secret_name} from environment variables")
            return env_value
        
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.PROJECT_ID}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(name=name)
            logger.info(f"Retrieved {secret_name} from Secret Manager")
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

try:
    config = Config()
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
# Role: Kritika - The Perfect English Teacher for Hindi Speakers

## Core Identity:
You are Kritika, an AI English teacher specializing in teaching Hindi speakers through Hinglish. Your personality is:
- Warm and encouraging like a favorite teacher
- Patient and clear in explanations
- Culturally aware of Indian contexts
- Strict about proper English but gentle in corrections

## Teaching Methodology:
1. Concept Explanation:
   - Give Hindi explanation (Roman script)
   - Show English structure/formula
   - Provide 5 simple examples
   - Contrast with Hindi sentence structure

2. Error Correction:
   - Never say "Wrong!" - instead: "Good try! More accurately we say..."
   - Highlight mistakes gently: "Yahan 'has' ki jagah 'have' aayega because..."
   - Always provide corrected version

3. Practical Help:
   - Real-life Indian context examples
   - Pronunciation guides with Hindi phonetics
   - Short practice exercises when requested

## Communication Style:
- Language Preference:
  - If question in Hindi: Reply in Hinglish (90% Hindi + 10% English)
  - If question in English: Reply in English
  - Example: "Present perfect tense mein hum 'has/have' ke saath verb ka third form use karte hai"

- Tone:
  - Encouraging: "Bahut accha attempt! Thoda sa correction..."
  - Supportive: "Chinta mat karo, practice se perfect hoga!"
  - Respectful: "Aapka sawal bahut relevant hai"

## Special Features:
1. Instant Help:
   - When user says "help" or "samjhao":
     1. Simplify concept
     2. Give 3 basic examples
     3. Offer alternative explanation

2. Cultural Adaptation:
   - Use Indian examples: "Jaise hum 'I am going to mandir' ke jagah 'I am going to the temple' kahenge"
   - Explain Western concepts in Indian context

## Prohibitions:
- No word-for-word translations
- No romantic/political/religious examples
- Don't overwhelm with information
- Never use complex English to explain basics

## Response Format:
1. Start with greeting if new conversation
2. Explain concept in simple steps
3. Provide examples
4. End with:
   - "Aur koi doubt hai?"
   - "Mai aur madad kar sakti hoon?"

## Example Interactions:
User: "Present perfect tense samjhao"
Response:
Namaste! Present perfect tense ke baare mein samjha deti hoon:

1. Concept: Ye tense batata hai ki koi action past mein shuru hua aur uska effect present tak hai.

2. Structure:
   Subject + has/have + verb ka 3rd form

3. Examples:
   - Mai Delhi gaya hoon (I have gone to Delhi)
   - Usne khana kha liya hai (She has eaten food)
   - Humne movie dekh li hai (We have watched the movie)

4. Hindi Comparison:
    Hindi mein hum "cha hai", "liya hai" ka use karte hai
    English mein "have/has" + verb ka 3rd form

Koi aur doubt hai?
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
                logger.info(f"New chat session started for {chat_id}")
            return self.conversations[chat_id]

    async def cleanup(self):
        async with self.lock:
            self.conversations.clear()
            logger.info("All conversation sessions cleared")

conversation_manager = ConversationManager()

# ======================
# TELEGRAM HANDLERS
# ======================
async def start(update: Update, context: CallbackContext):
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        await conversation_manager.get_chat(chat_id)
        
        welcome_msg = (
            f"Namaste {user.first_name}!\n\n"
            "Main Kritika hoon - aapki personal English teacher.\n\n"
            "Mujhse aap poochh sakte hain:\n"
            "• Grammar concepts\n• Sentence corrections\n• Translations\n"
            "• Vocabulary doubts\n• Pronunciation help\n\n"
            "Koi bhi English-related problem ho, bas message kijiye!\n\n"
            "Chaliye shuru karte hain... Aaj aap kya seekhna chahenge?"
        )
        await update.message.reply_text(welcome_msg)
        logger.info(f"Sent welcome message to {chat_id}")
    except Exception as e:
        logger.error(f"Error in start handler: {e}", exc_info=True)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "Kuch technical problem aa gayi hai. Kripya thodi der baad try karein."
            )

async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    if not user_message:
        logger.warning(f"Empty message from {chat_id}")
        return

    try:
        logger.info(f"Processing message from {chat_id}: {user_message[:100]}...")
        chat = await conversation_manager.get_chat(chat_id)
        response = await chat.send_message(user_message)
        
        if response.text:
            await update.message.reply_text(response.text)
            logger.info(f"Response sent to {chat_id}")
        else:
            logger.error(f"Empty response from Gemini for {chat_id}")
            await update.message.reply_text(
                "Maaf karna, main samjha nahi. Kya aap phir se try kar sakte hain?\n\n"
                "Ya phir aap 'help' likh kar mujhe bata sakte hain ki aapko kis cheez mein difficulty aa rahi hai."
            )
    except Exception as e:
        logger.error(f"Error handling message for {chat_id}: {e}", exc_info=True)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "Kuch technical problem aa raha hai. Hum team ko inform kar diya hai.\n\n"
                "Kripya kuch samay baad phir try karein. Dhanyavaad!"
            )

async def error_handler(update: Update, context: CallbackContext):
    error = context.error
    logger.error(f"Telegram error: {error}", exc_info=True)
    
    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "Kuch technical problem aa gayi hai. Hum ise fix kar rahe hain.\n\n"
                "Kripya thodi der baad phir try karein. Dhanyavaad!"
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

# ======================
# APPLICATION MANAGEMENT
# ======================
class BotApplication:
    def __init__(self):
        self.application = None
        self.bot = None
        self.running = False
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        try:
            self.application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self.bot = self.application.bot
            
            self.application.add_handler(CommandHandler('start', start))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            self.application.add_error_handler(error_handler)
            
            await self.application.initialize()
            await self.application.start()
            
            if config.WEBHOOK_URL:
                await self.setup_webhook(config.WEBHOOK_URL)
            else:
                await self.application.updater.start_polling()
                logger.info("Bot started in polling mode")
                
            self.running = True
            logger.info("Bot application initialized and running")
        except Exception as e:
            logger.critical(f"Failed to initialize application: {e}")
            raise

    async def setup_webhook(self, url):
        webhook_url = f"{url}/webhook"
        await self.bot.set_webhook(webhook_url)
        logger.info(f"Webhook configured at {webhook_url}")

    async def shutdown(self):
        if self.running:
            try:
                logger.info("Starting graceful shutdown...")
                await conversation_manager.cleanup()
                
                if config.WEBHOOK_URL:
                    await self.bot.delete_webhook()
                    logger.info("Webhook removed")
                
                if self.application:
                    if hasattr(self.application, 'updater') and self.application.updater:
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

# Global references for webhook handling
application = None
bot_instance = None

# ======================
# MAIN EXECUTION
# ======================
async def main():
    global application, bot_instance
    
    try:
        await start_http_server()
        logger.info("HTTP health check server started")
        
        bot = BotApplication()
        await bot.initialize()
        application = bot.application
        bot_instance = bot.bot
        
        logger.info("Bot is now running")
        await bot.run_forever()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        if 'bot' in locals() and bot.running:
            await bot.shutdown()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical failure: {e}", exc_info=True)
        raise
