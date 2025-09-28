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
import uvicorn
from fastapi import FastAPI, Request, Response

# --- 1. Basic Setup & Configuration ---

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

try:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
except (TypeError, ValueError):
    logger.error("FATAL: GEMINI_API_KEY and TELEGRAM_BOT_TOKEN must be set as environment variables.")
    exit()

# --- 2. AI Model Initialization ---
try:
    text_model = genai.GenerativeModel('gemini-pro')
    vision_model = genai.GenerativeModel('gemini-pro-vision')
except Exception as e:
    logger.error(f"FATAL: Could not initialize Gemini models: {e}")
    exit()

# --- 3. Conversation Handler States ---
WAITING_FOR_IMAGE = 1

# --- 4. Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    about_text = (
        "**ℹ️ About This Bot**\n\n"
        "This bot uses Google's powerful Gemini API to bring advanced AI features to your Telegram chat.\n\n"
        "**Developer:** @AADI_IO\n"
        "**Technology:** Python, `python-telegram-bot`, Google Gemini"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'chat_session' in context.user_data:
        del context.user_data['chat_session']
    await update.message.reply_text("✅ Conversation history cleared. Let's start a fresh chat!")

# --- 5. Feature Logic Handlers ---

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        response = await asyncio.to_thread(chat.send_message, user_message)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Error in chat_handler: {e}")
        await update.message.reply_text("Sorry, an error occurred while processing your request. Please try starting a `/newchat`.")

async def ocr_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please send the image you want me to scan for text. To cancel, send /cancel.")
    return WAITING_FOR_IMAGE

async def ocr_image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"Received image for OCR from {update.effective_user.first_name}")
    await update.message.reply_text("⏳ Processing your image, this may take a moment...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        photo_file: File = await update.message.photo[-1].get_file()
        file_bytes = await photo_file.download_as_bytearray()
        img = Image.open(io.BytesIO(file_bytes))
        prompt = "Extract all text from this image. Present it clearly and accurately."
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
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

# --- 6. Telegram Application Setup ---

ptb_application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# --- 7. Web Server (FastAPI) Setup ---

app = FastAPI()

async def initialize_bot():
    """Initializes the bot, sets commands, and sets the webhook."""
    logger.info("Initializing bot...")

    # Define bot commands
    commands = [
        BotCommand("start", "▶️ Welcome & Intro"),
        BotCommand("help", "❓ How to use the bot"),
        BotCommand("chat", "🤖 Chat with the AI"),
        BotCommand("ocr", "📄 Extract text from image"),
        BotCommand("newchat", "🔄 Start a new conversation"),
    ]
    await ptb_application.bot.set_my_commands(commands)
    
    # Retry logic to get the WEBHOOK_URL from Render's environment
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    retries = 10
    while not WEBHOOK_URL and retries > 0:
        logger.warning(f"WEBHOOK_URL not found. Retrying in 5 seconds... ({retries} left)")
        await asyncio.sleep(5)
        WEBHOOK_URL = os.getenv("WEBHOOK_URL")
        retries -= 1

    if WEBHOOK_URL:
        webhook_path = f"/{TELEGRAM_BOT_TOKEN}"
        await ptb_application.bot.set_webhook(url=f"{WEBHOOK_URL}{webhook_path}")
        logger.info(f"Webhook set successfully to {WEBHOOK_URL}{webhook_path}")
    else:
        logger.error("FATAL: WEBHOOK_URL not found after multiple retries. Webhook not set.")

@app.on_event("startup")
async def startup_event():
    """On startup, create a background task to initialize the bot."""
    asyncio.create_task(initialize_bot())

@app.get("/")
def health_check():
    """This endpoint is called by Render to check if the service is live."""
    return {"status": "ok"}

@app.post("/{token}")
async def process_telegram_update(token: str, request: Request):
    """This endpoint receives the updates from Telegram."""
    if token != TELEGRAM_BOT_TOKEN:
        return Response(status_code=403)
    
    try:
        update_data = await request.json()
        update = Update.de_json(data=update_data, bot=ptb_application.bot)
        await ptb_application.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status_code=500)

# --- 8. Main Execution ---

if __name__ == '__main__':
    # Add all handlers to the application
    ocr_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ocr", ocr_start_handler)],
        states={WAITING_FOR_IMAGE: [MessageHandler(filters.PHOTO, ocr_image_handler)]},
        fallbacks=[CommandHandler("cancel", ocr_cancel_handler)],
    )
    ptb_application.add_handler(CommandHandler("start", start_command))
    ptb_application.add_handler(CommandHandler("help", help_command))
    ptb_application.add_handler(CommandHandler("about", about_command))
    ptb_application.add_handler(CommandHandler("newchat", newchat_command))
    ptb_application.add_handler(CommandHandler("chat", chat_handler))
    ptb_application.add_handler(ocr_conv_handler)
    
    async def guide_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Please use a command to interact with me. Click the 'Menu' button or type /help to see what I can do!")
    ptb_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guide_user_handler))

    # Run the web server
    PORT = int(os.environ.get('PORT', '8080'))
    uvicorn.run(app, host="0.0.0.0", port=PORT)

