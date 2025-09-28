import os
import logging
import google.generativeai as genai
from telegram import Update, File, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from PIL import Image
import io

# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API Configuration ---
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    # We will get WEBHOOK_URL later inside the main function to avoid startup race conditions.
    genai.configure(api_key=GEMINI_API_KEY)
except TypeError:
    logger.error("API keys not found. Please set GEMINI_API_KEY and TELEGRAM_BOT_TOKEN as environment variables.")
    exit()

# --- Gemini Model Initialization ---
text_model = genai.GenerativeModel('gemini-pro')
vision_model = genai.GenerativeModel('gemini-pro-vision')

# --- Conversation States ---
WAITING_FOR_IMAGE = 1

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 **Hello {user_name}!**\n\n"
        "Welcome to your multi-functional AI assistant!\n\n"
        "I have distinct features, each with its own command. "
        "This makes it easy for you to tell me exactly what you need.\n\n"
        "Click the 'Menu' button or type /help to see all the commands and get started!\n\n"
        "**Credits:** @AADI_IO"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provides a detailed guide on how to use the bot's commands."""
    help_text = (
        "**How to Use This Bot**\n\n"
        "Here are the available commands:\n\n"
        "🤖 **/chat [your question]**\n"
        "Use this command to have a conversation with the AI. "
        "Simply type your question or message after the command.\n"
        "*Example:* `/chat What is the capital of India?`\n\n"
        "📄 **/ocr**\n"
        "Use this command to extract text from an image (Optical Character Recognition). "
        "After sending this command, I will ask you to send the image.\n\n"
        "🔄 **/newchat**\n"
        "Starts a fresh, new conversation with the AI, clearing any previous context.\n\n"
        "ℹ️ **/about**\n"
        "Displays information about the bot, its developer, and the technology it uses."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends information about the bot."""
    about_text = (
        "**About This Bot**\n\n"
        "This bot leverages the power of Google's Gemini API to provide advanced AI capabilities directly within Telegram.\n\n"
        "**Developer:** @AADI_IO\n"
        "**Technology:** Python, python-telegram-bot, Google Gemini"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clears the user's conversation history."""
    if 'chat_session' in context.user_data:
        del context.user_data['chat_session']
    await update.message.reply_text("✅ Conversation history cleared. Let's start a fresh chat!")

# --- Feature Handlers ---

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /chat command and generates a response."""
    user_message = " ".join(context.args)
    if not user_message:
        await update.message.reply_text("Please ask a question after the /chat command.\n*Example:* `/chat Who are you?`", parse_mode='Markdown')
        return

    logger.info(f"Chat query from {update.effective_user.first_name}: {user_message}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        if 'chat_session' not in context.user_data:
            context.user_data['chat_session'] = text_model.start_chat(history=[])
        
        chat = context.user_data['chat_session']
        response = chat.send_message(user_message)
        
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Error in chat_handler: {e}")
        await update.message.reply_text("Sorry, an error occurred. Please try starting a /newchat.")

async def ocr_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user to send an image for OCR."""
    await update.message.reply_text("Please send the image you want me to scan for text.")
    return WAITING_FOR_IMAGE

async def handle_ocr_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the image sent for OCR."""
    logger.info(f"Received image for OCR from {update.effective_user.first_name}")
    await update.message.reply_text("⏳ Processing your image, please wait...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        photo_file: File = await update.message.photo[-1].get_file()
        file_bytes = await photo_file.download_as_bytearray()
        img = Image.open(io.BytesIO(file_bytes))

        prompt = "Extract all text from this image. Present it clearly and accurately."
        response = vision_model.generate_content([prompt, img])

        final_response = (
            f"✅ **Text Extracted:**\n\n---\n\n{response.text}\n\n---\n\n"
            "Credits: @AADI_IO"
        )
        await update.message.reply_text(final_response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in handle_ocr_image: {e}")
        await update.message.reply_text("Sorry, I couldn't process that image. Please ensure it's a clear photo and try the /ocr command again.")
    
    return ConversationHandler.END

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current operation, like waiting for an image."""
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

async def post_init(application: Application) -> None:
    """Sets the bot commands after initialization."""
    commands = [
        BotCommand("start", "▶️ Welcome & Intro"),
        BotCommand("help", "❓ How to use the bot"),
        BotCommand("chat", "🤖 Chat with the AI"),
        BotCommand("ocr", "📄 Extract text from image"),
        BotCommand("newchat", "🔄 Start a new conversation"),
    ]
    await application.bot.set_my_commands(commands)
    # The webhook is now set in the main() function by run_webhook, so we remove it from here.

def main() -> None:
    """Start the bot using webhooks."""
    logger.info("Starting bot in webhook mode...")
    
    # Get webhook URL from environment just before it's needed.
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL environment variable not found!")
        return # Exit if the URL isn't set, as webhook mode is impossible.

    # Render provides the port to listen on in the PORT environment variable. Default to 8080 for local testing.
    PORT = int(os.environ.get('PORT', '8080'))

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Conversation handler for the OCR feature
    ocr_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ocr", ocr_command_handler)],
        states={
            WAITING_FOR_IMAGE: [MessageHandler(filters.PHOTO, handle_ocr_image)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
    )

    # --- Register all handlers here ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("newchat", newchat_command))
    application.add_handler(CommandHandler("chat", chat_handler))
    application.add_handler(ocr_conv_handler)
    
    # A generic message handler to guide users who just type text
    async def guide_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Please use a command to interact with me. Type /help to see what I can do!")
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, guide_user))

    # Add the error handler
    application.add_error_handler(error_handler)

    # Start the Bot with a webhook.
    # The run_webhook function will also automatically set the webhook on Telegram servers.
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == '__main__':
    main()

