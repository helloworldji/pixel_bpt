import os
import logging
import google.generativeai as genai
from telegram import Update, File
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image
import io

# --- Basic Setup ---
# Enable logging to see errors
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API Configuration ---
# It's recommended to use environment variables for security
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    genai.configure(api_key=GEMINI_API_KEY)
except TypeError:
    logger.error("API keys not found. Make sure GEMINI_API_KEY and TELEGRAM_BOT_TOKEN are set as environment variables.")
    exit()


# --- Gemini Model Initialization ---
# Model for text-based chat
text_model = genai.GenerativeModel('gemini-pro')
# Model for processing images (vision)
vision_model = genai.GenerativeModel('gemini-pro-vision')

# --- Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"👋 Hello {user_name}!\n\n"
        "Welcome to the Gemini Powered Bot!\n\n"
        "Here's what I can do:\n\n"
        "🤖 **Chat Bot:** Just send me any message, and I'll chat with you!\n\n"
        "📄 **Image to Text (OCR):** Send me a screenshot or any image with text, and I'll extract it for you.\n\n"
        "To get started, just type a message or send an image!\n\n"
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(welcome_message)

# --- Message Handlers ---

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages for the chatbot feature."""
    user_message = update.message.text
    logger.info(f"Received text message from {update.effective_user.first_name}: {user_message}")

    try:
        # Show a "typing..." status to the user
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        # Send text to Gemini API
        response = text_model.generate_content(user_message)
        
        # Send Gemini's response back to the user
        await update.message.reply_text(response.text)
        
    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        await update.message.reply_text("Sorry, I encountered an error while processing your message. Please try again later.")

async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles image messages for the OCR feature."""
    logger.info(f"Received image from {update.effective_user.first_name}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    await update.message.reply_text("Processing your image, please wait...")

    try:
        # Get the photo file sent by the user (highest resolution)
        photo_file: File = await update.message.photo[-1].get_file()
        
        # Download the file into memory
        file_bytes = await photo_file.download_as_bytearray()
        img = Image.open(io.BytesIO(file_bytes))

        # Prepare the prompt for the vision model
        prompt = "Extract all text from this image. Present it clearly."
        
        # Send image and prompt to Gemini Vision API
        response = vision_model.generate_content([prompt, img])

        # Construct the final response
        final_response = (
            f"✅ Here is the text I found in your image:\n\n---\n\n{response.text}\n\n---\n\n"
            "Credits: @AADI_IO"
        )
        
        await update.message.reply_text(final_response)

    except Exception as e:
        logger.error(f"Error handling image message: {e}")
        await update.message.reply_text("Sorry, I couldn't process that image. Please make sure it's a clear image with visible text.")


def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Register Handlers ---
    # Command handlers
    application.add_handler(CommandHandler("start", start))

    # Message handlers
    # Use `~filters.COMMAND` to ensure commands are not treated as text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image_message))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == '__main__':
    main()
