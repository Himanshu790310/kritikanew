import os
import logging
import asyncio # Keep asyncio for async operations
from typing import Dict

# For FastAPI
from fastapi import FastAPI, Request, HTTPException

# For Google Secret Manager
from google.cloud import secretmanager # Correct import path

# For Google Gemini
import google.generativeai as genai

# For Python Telegram Bot
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# For running FastAPI with Uvicorn
import uvicorn

# ======================
# LOGGING CONFIGURATION
# ======================
# Initialize basic logging first, then try Cloud Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG # Set to DEBUG for verbose output during debugging
)
logger = logging.getLogger('EnglishTeachingBot')
logger.setLevel(logging.DEBUG) # Ensure logger level is also DEBUG

try:
    import google.cloud.logging
    logging_client = google.cloud.logging.Client()
    logging_client.setup_logging(log_level=logging.DEBUG) # Set Cloud Logging to DEBUG
    logger.info("Cloud Logging set up.")
except Exception as e:
    logger.warning(f"Could not set up Cloud Logging, falling back to basic logging: {e}")

# ======================
# CONFIGURATION MANAGER
# ======================
class Config:
    def __init__(self):
        # Default to your specific project ID here if not in env
        self.PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "kritika-463510") 
        logger.info(f"Using Google Cloud Project ID: {self.PROJECT_ID}")

        self.TELEGRAM_BOT_TOKEN = self._get_secret("TELEGRAM_BOT_TOKEN")
        self.GOOGLE_API_KEY = self._get_secret("GOOGLE_API_KEY")
        # WEBHOOK_URL will be set by Cloud Run and accessed as an env var
        self.WEBHOOK_URL = os.getenv("K_SERVICE_URL", "") # Standard Cloud Run URL env var
        
        self._validate_config()
        logger.info("Configuration loaded successfully")

    def _get_secret(self, secret_name):
        env_value = os.getenv(secret_name)
        if env_value:
            logger.debug(f"Retrieved {secret_name} from environment variable.")
            return env_value
        
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.PROJECT_ID}/secrets/{secret_name}/versions/latest"
            logger.debug(f"Attempting to retrieve secret from Secret Manager: {name}")
            response = client.access_secret_version(name=name)
            secret_value = response.payload.data.decode("UTF-8")
            logger.debug(f"Successfully retrieved {secret_name} from Secret Manager.")
            return secret_value
        except Exception as e:
            logger.error(f"Failed to retrieve secret '{secret_name}' from Secret Manager: {e}", exc_info=True)
            raise ValueError(f"Could not retrieve {secret_name}")

    def _validate_config(self):
        if not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required and not found.")
        if not self.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is required and not found.")
        if not self.WEBHOOK_URL:
            logger.warning("WEBHOOK_URL (K_SERVICE_URL) not found in environment. Webhook will not be set automatically during startup.")


# --- GLOBAL APPLICATION INSTANCES ---
# These will be initialized in the startup event
config: Config = None
application: Application = None
conversation_manager: 'ConversationManager' = None # Forward declaration

# ======================
# CONVERSATION MANAGER (for maintaining chat history with Gemini)
# ======================
class ConversationManager:
    def __init__(self, model_instance: genai.GenerativeModel):
        self.chats: Dict[int, genai.GenerativeModel.start_chat] = {}
        self.model = model_instance # Use the already initialized model
        self.lock = asyncio.Lock()
        logger.info("ConversationManager initialized.")

    async def get_chat(self, chat_id: int):
        async with self.lock:
            if chat_id not in self.chats:
                self.chats[chat_id] = self.model.start_chat(history=[])
                logger.info(f"New chat session started for chat_id: {chat_id}")
            return self.chats[chat_id]

    async def cleanup(self):
        async with self.lock:
            self.chats.clear()
            logger.info("All conversation sessions cleared")

# ======================
# TELEGRAM HANDLERS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        user = update.effective_user
        await conversation_manager.get_chat(chat_id) # Ensure chat session starts
        
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
        print(f"DEBUG: Sent welcome message to {chat_id}") # Debug print
    except Exception as e:
        logger.error(f"Error in start handler for {update.effective_chat.id}: {e}", exc_info=True)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "Kuch technical problem aa gayi hai. Kripya thodi der baad try karein."
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    logger.info(f"Processing message from {chat_id}: '{user_message[:100]}'")
    print(f"DEBUG: Processing message from {chat_id}: {user_message}") # Debug print

    if not user_message:
        logger.warning(f"Empty message received from {chat_id}")
        print(f"DEBUG: Empty message from {chat_id}") # Debug print
        return

    try:
        chat = await conversation_manager.get_chat(chat_id)
        # Assuming your Gemini model is already configured and global/accessible
        response = await chat.send_message(user_message)
        
        if response.text:
            await update.message.reply_text(response.text)
            logger.info(f"Bot replied to {chat_id}")
            print(f"DEBUG: Sent reply to {chat_id}: {response.text[:50]}...") # Debug print
        else:
            logger.warning(f"Empty text in Gemini response for {chat_id}")
            await update.message.reply_text("I'm sorry, I couldn't generate a response for that.")
            print(f"DEBUG: Sent error reply (empty Gemini response) to {chat_id}") # Debug print

    except Exception as e:
        logger.error(f"Error handling message from {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred while processing your request. Please try again later.")
        print(f"DEBUG: Error in handle_message for {chat_id}: {e}") # Debug print

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    logger.error(f"Telegram error: {error}", exc_info=True)
    
    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "Kuch technical problem aa gayi hai. Hum ise fix kar rahe hain.\n\n"
                "Kripya thodi der baad phir try karein. Dhanyavaad!"
            )
        except Exception as e:
            logger.error(f"Failed to send error message in error_handler: {e}")

# ======================
# FASTAPI APP SETUP
# ======================
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "English Teaching Bot is running!"}

# --- HEALTH AND READINESS CHECKS ---
@app.get("/healthz")
async def health_check():
    """Kubernetes-style health check endpoint"""
    return {
        "status": "healthy",
        "details": {
            "telegram_app_ready": application is not None and application.running,
            "gemini_model_ready": hasattr(genai, 'default_generative_model') and genai.default_generative_model is not None,
            "config_loaded": config is not None,
            "service": "english-teaching-bot"
        }
    }

@app.get("/ready")
async def readiness_check():
    try:
        # Check if core components are initialized and ready to serve
        if application and application.running and \
           hasattr(genai, 'default_generative_model') and genai.default_generative_model:
            return {"ready": True}
        else:
            logger.warning("Readiness check failed: Application or Gemini not ready.")
            raise HTTPException(status_code=503, detail="Service not ready")
    except Exception as e:
        logger.error(f"Readiness check failed unexpectedly: {e}")
        raise HTTPException(status_code=503, detail="Service not ready (internal error)")


# --- FASTAPI STARTUP EVENT ---
@app.on_event("startup")
async def startup_event():
    global config, application, conversation_manager
    logger.info("--- Application startup event initiated ---")
    print("DEBUG: --- Application startup event initiated ---") # Debug print

    try:
        # 1. Load Configuration
        config = Config()
        logger.info("Config loaded.")
        print("DEBUG: Config loaded.") # Debug print

        # 2. Configure Gemini (as it needs API key from config)
        genai.configure(api_key=config.GOOGLE_API_KEY)
        gemini_model_instance = genai.GenerativeModel(
            model_name="gemini-1.5-flash-latest",
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            system_instruction=SYSTEM_INSTRUCTION
        )
        logger.info("Gemini model configured and initialized.")
        print("DEBUG: Gemini model configured.") # Debug print

        # 3. Initialize Telegram Application
        application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        logger.info("Telegram Application builder created.")
        print("DEBUG: Telegram Application builder created.") # Debug print

        # Add Handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        logger.info("Telegram handlers added.")
        print("DEBUG: Telegram handlers added.") # Debug print

        # Initialize and start the Telegram application (for webhook mode, this just sets up internal state)
        await application.initialize()
        await application.start() # Necessary for internal PTB state management, even with webhooks
        logger.info("Telegram Application initialized and started internally.")
        print("DEBUG: Telegram Application initialized and started internally.") # Debug print

        # 4. Set Telegram Webhook (if WEBHOOK_URL is available)
        if config.WEBHOOK_URL:
            webhook_url_full = f"{config.WEBHOOK_URL}/webhook"
            await application.bot.set_webhook(url=webhook_url_full)
            logger.info(f"Webhook set to: {webhook_url_full}")
            print(f"DEBUG: Webhook set to: {webhook_url_full}") # Debug print
        else:
            logger.warning("WEBHOOK_URL not found in environment (K_SERVICE_URL). Webhook not set automatically.")
            print("DEBUG: WEBHOOK_URL missing, webhook not set automatically.") # Debug print

        # 5. Initialize Conversation Manager (after Gemini model is ready)
        conversation_manager = ConversationManager(model_instance=gemini_model_instance)
        logger.info("ConversationManager initialized.")
        print("DEBUG: ConversationManager initialized.") # Debug print

        logger.info("--- Application startup complete ---")
        print("DEBUG: --- Application startup complete ---") # Debug print

    except Exception as e:
        logger.critical(f"FATAL ERROR during application startup: {e}", exc_info=True)
        print(f"DEBUG: FATAL ERROR during startup: {e}") # Debug print
        # Re-raise to prevent the server from starting improperly
        raise

# --- TELEGRAM WEBHOOK ENDPOINT ---
@app.post("/webhook")
async def telegram_webhook(request: Request):
    print("----- Webhook request received! -----") # Debug print to check if request reaches
    try:
        if application is None or not application.running:
            logger.error("Webhook received but Telegram Application is not initialized/running.")
            print("DEBUG: Application not ready for webhook.") # Debug print
            raise HTTPException(status_code=503, detail="Telegram Application not ready")

        json_data = await request.json()
        print(f"Received JSON data: {json_data}") # Debug print of received data

        # Use application.bot directly as it's correctly initialized in startup_event
        update = Update.de_json(json_data, application.bot) 
        print(f"Update object created for chat: {update.effective_chat.id}") # Debug print

        await application.process_update(update)
        print("----- Webhook request processed. -----") # Debug print
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        print(f"----- Webhook ERROR: {e} -----") # Debug print for immediate error visibility
        # Return 500 status code for internal errors
        return {"status": "error", "message": str(e)}, 500

# ======================
# MAIN EXECUTION
# ======================
# This is the standard entry point for Cloud Run
if __name__ == "__main__":
    logger.info("Starting FastAPI application with Uvicorn.")
    # Uvicorn will automatically call app.on_event("startup")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
