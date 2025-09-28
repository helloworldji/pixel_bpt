import os
import logging
import asyncio
import google.generativeai as genai
from telegram import Update, File, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from PIL import Image
import io

# --- 1. Basic Setup & Configuration ---

# Configure logging to see events and errors
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get API keys from environment variables. The script will exit if they are not found.
try:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    # Configure the Gemini API client
    genai.configure(api_key=GEMINI_API_KEY)
except (TypeError, ValueError):
    logger.error("FATAL: GEMINI_API_KEY and TELEGRAM_BOT_TOKEN must be set in environment variables.")
    exit()

# --- 2. AI Model Initialization ---
try:
    text_model = genai.GenerativeModel('gemini-pro')
    vision_model = genai.GenerativeModel('gemini-pro-vision')
except Exception as e:
    logger.error(f"FATAL: Could not initialize Gemini models: {e}")
    exit()

# --- 3. Conversation Handler States ---
# Define a state for the OCR conversation flow to know when we are waiting for an image
WAITING_FOR_IMAGE = 1

# --- 4. Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the user and explains the bot's purpose."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 **Hello {user_name}!**\n\n"
        "I am an AI assistant powered by Google Gemini.\n\n"
        "I have several features, each triggered by a specific command. "
        "This makes it easy for you to get exactly what you need.\n\n"
        "👉 Click the **Menu** button below (or type `/`) to see all available commands and get started!\n\n"
        "**Credits:** @AADI_IO"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides a detailed guide on how to use the bot's commands."""
    help_text = (
        "**📖 How to Use This Bot**\n\n"
        "Here is a list of all my commands:\n\n"
        "🤖 **/chat [your question]**\n"
        "Engage in a conversation. Just type your question after the command.\n"
        "  *Example:* `/chat What are the best places to visit in India?`\n\n"
        "📄 **/ocr**\n"
        "Extract text from an image. After sending this command, I will prompt you to send the photo.\n\n"
        "🔄 **/newchat**\n"
        "Clears our previous conversation history, allowing us to start fresh.\n\n"
        "ℹ️ **/about**\n"
        "Displays information about me, my developer, and the technology I use."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows information about the bot."""
    about_text = (
        "**ℹ️ About This Bot**\n\n"
        "This bot uses Google's powerful Gemini API to bring advanced AI features to your Telegram chat.\n\n"
        "**Developer:** @AADI_IO\n"
        "**Technology:** Python, `python-telegram-bot`, Google Gemini"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the user's conversation history for the chat model."""
    if 'chat_session' in context.user_data:
        del context.user_data['chat_session']
    await update.message.reply_text("✅ Conversation history cleared. Let's start a fresh chat!")

# --- 5. Feature Logic Handlers ---

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /chat command and generates a text response."""
    user_message = " ".join(context.args)
    if not user_message:
        await update.message.reply_text("Please provide a question after the `/chat` command.\n*Example:* `/chat Who are you?`", parse_mode='Markdown')
        return

    logger.info(f"Chat query from {update.effective_user.first_name}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        if 'chat_session' not in context.user_data:
            context.user_data['chat_session'] = text_model.start_chat(history=[])
        
        chat = context.user_data['chat_session']
        # Run the synchronous Gemini SDK call in a separate thread to avoid blocking
        response = await asyncio.to_thread(chat.send_message, user_message)
        
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Error in chat_handler: {e}")
        await update.message.reply_text("Sorry, an error occurred while processing your request. Please try starting a `/newchat`.")

async def ocr_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the OCR process by asking for an image."""
    await update.message.reply_text("Please send the image you want me to scan for text. To cancel, send /cancel.")
    return WAITING_FOR_IMAGE

async def ocr_image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the image sent for OCR."""
    logger.info(f"Received image for OCR from {update.effective_user.first_name}")
    await update.message.reply_text("⏳ Processing your image, this may take a moment...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        photo_file: File = await update.message.photo[-1].get_file()
        file_bytes = await photo_file.download_as_bytearray()
        img = Image.open(io.BytesIO(file_bytes))

        prompt = "Extract all text from this image. Present it clearly and accurately."
        # Run the synchronous Gemini SDK call in a separate thread
        response = await asyncio.to_thread(vision_model.generate_content, [prompt, img])

        final_response = (
            f"✅ **Text Extracted:**\n\n---\n\n{response.text}\n\n---\n\n"
            "**Credits:** @AADI_IO"
        )
        await update.message.reply_text(final_response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in ocr_image_handler: {e}")
        await update.message.reply_text("Sorry, I couldn't process that image. Please try the `/ocr` command again.")
    
    return ConversationHandler.END

async def ocr_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the OCR operation if the user sends /cancel."""
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

# --- 6. Error Handling & General Messages ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs any errors that the bot encounters."""
    logger.error('Update "%s" caused error "%s"', update, context.error)

async def guide_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles any text message that isn't a command, guiding the user on how to interact."""
    await update.message.reply_text("Please use a command to interact with me. Click the 'Menu' button or type /help to see what I can do!")

# --- 7. Main Application Setup & Execution ---

async def post_init(application: Application) -> None:
    """This function is called after the bot is initialized to set the command menu."""
    logger.info("Setting up bot commands...")
    commands = [
        BotCommand("start", "▶️ Welcome & Intro"),
        BotCommand("help", "❓ How to use the bot"),
        BotCommand("chat", "🤖 Chat with the AI"),
        BotCommand("ocr", "📄 Extract text from image"),
        BotCommand("newchat", "🔄 Start a new conversation"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set successfully.")

async def main() -> None:
    """The main function to set up and run the bot."""
    PORT = int(os.environ.get('PORT', '8080'))

    # This is the crucial part for Render deployment. We need the public URL
    # from the WEBHOOK_URL env var, which isn't available immediately.
    # We will retry asynchronously while the health check server runs.
    logger.info("Attempting to find WEBHOOK_URL from environment...")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    retries = 10
    while not WEBHOOK_URL and retries > 0:
        logger.warning(f"WEBHOOK_URL not found. Retrying in 5 seconds... ({retries} left)")
        await asyncio.sleep(5) # Non-blocking sleep allows health checks to pass
        WEBHOOK_URL = os.getenv("WEBHOOK_URL")
        retries -= 1

    if not WEBHOOK_URL:
        logger.error("FATAL: WEBHOOK_URL not found after multiple retries. Cannot start in webhook mode.")
        return

    logger.info(f"Successfully found WEBHOOK_URL: {WEBHOOK_URL}")

    # Build the application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .health_check_endpoint("/") # Responds to Render's health checks
        .build()
    )

    # Define the conversation handler for the multi-step OCR process
    ocr_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ocr", ocr_start_handler)],
        states={ WAITING_FOR_IMAGE: [MessageHandler(filters.PHOTO, ocr_image_handler)] },
        fallbacks=[CommandHandler("cancel", ocr_cancel_handler)],
    )

    # Register all handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("newchat", newchat_command))
    application.add_handler(CommandHandler("chat", chat_handler))
    application.add_handler(ocr_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guide_user_handler))
    application.add_error_handler(error_handler)

    # Start the bot in webhook mode
    logger.info(f"Starting webhook server on port {PORT}...")
    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")

