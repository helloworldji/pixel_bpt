import os
import logging
import asyncio
import html
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.request import HTTPXRequest
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Validate required environment variables
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable not set")
    exit(1)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Initialize FastAPI app
app = FastAPI(title="Telegram Gemini Bot")

# Global variable for Telegram application
application = None

# Store conversation history
user_conversations = {}

# Conversation states
MAIN_MENU, CHAT_MODE, OCR_MODE, SSHOT_MODE = range(4)

# Initialize Gemini 2.5 Flash model
try:
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    logger.info("Successfully initialized Gemini 2.5 Flash model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini 2.5 Flash model: {e}")
    logger.info("Falling back to gemini-1.5-flash model")
    model = genai.GenerativeModel('gemini-1.5-flash')

# =========================
# Main Menu & Mode Management
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - entry point to main menu"""
    try:
        user = update.effective_user
        
        # Create mode selection keyboard
        reply_keyboard = [
            ["💬 Chat Mode", "📷 OCR Mode"],
            ["🖼️ Screenshot Mode", "❌ Cancel"]
        ]
        
        welcome_message = (
            f"👋 Hello {user.first_name}!\n\n"
            "🤖 I'm your Gemini 2.5 Flash powered AI assistant\n\n"
            "🔘 **Select a mode to start:**\n"
            "• 💬 **Chat Mode** - AI conversations\n"
            "• 📷 **OCR Mode** - Extract text from images\n"
            "• 🖼️ **Screenshot Mode** - Analyze screenshots\n\n"
            "Once in a mode, just send messages/images normally!\n\n"
            "Credits: @AADI_IO"
        )
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, 
                resize_keyboard=True,
                one_time_keyboard=False
            )
        )
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use the keyboard to select a mode.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections"""
    text = update.message.text
    
    if text == "💬 Chat Mode":
        return await switch_to_chat_mode(update, context)
    elif text == "📷 OCR Mode":
        return await switch_to_ocr_mode(update, context)
    elif text == "🖼️ Screenshot Mode":
        return await switch_to_sshot_mode(update, context)
    elif text == "❌ Cancel":
        return await cancel_command(update, context)
    else:
        await update.message.reply_text("Please select a mode from the keyboard below:")
        return MAIN_MENU

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to chat mode"""
    try:
        await update.message.reply_text(
            "🔘 **Switched to 💬 Chat Mode**\n\n"
            "Now you can chat with me normally! Just send your messages and I'll respond.\n\n"
            "Use /mode to return to mode selection or /cancel to exit.",
            reply_markup=ReplyKeyboardRemove()
        )
        return CHAT_MODE
    except Exception as e:
        logger.error(f"Error switching to chat mode: {e}")
        return MAIN_MENU

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to OCR mode"""
    try:
        await update.message.reply_text(
            "🔘 **Switched to 📷 OCR Mode**\n\n"
            "Now send me images and I'll extract text from them!\n\n"
            "Use /mode to return to mode selection or /cancel to exit.",
            reply_markup=ReplyKeyboardRemove()
        )
        return OCR_MODE
    except Exception as e:
        logger.error(f"Error switching to OCR mode: {e}")
        return MAIN_MENU

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to screenshot mode"""
    try:
        await update.message.reply_text(
            "🔘 **Switched to 🖼️ Screenshot Mode**\n\n"
            "Now send me screenshots and I'll analyze them for issues and solutions!\n\n"
            "Use /mode to return to mode selection or /cancel to exit.",
            reply_markup=ReplyKeyboardRemove()
        )
        return SSHOT_MODE
    except Exception as e:
        logger.error(f"Error switching to screenshot mode: {e}")
        return MAIN_MENU

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to mode selection"""
    return await start_command(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation and return to main menu"""
    try:
        await update.message.reply_text(
            "Conversation ended. Use /start to begin again.",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Error in cancel command: {e}")
    return ConversationHandler.END

# =========================
# Chat Mode Handlers
# =========================

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle normal messages in chat mode"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Ignore command messages in chat mode
    if message_text.startswith('/'):
        await update.message.reply_text("Use /mode to switch modes or /cancel to exit.")
        return CHAT_MODE
    
    try:
        # Initialize conversation history if not exists
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Generate response using Gemini 2.5 Flash with history
        chat_session = model.start_chat(history=user_conversations[user_id])
        response = chat_session.send_message(message_text)
        
        # Update conversation history
        user_conversations[user_id].extend([
            {"role": "user", "parts": [message_text]},
            {"role": "model", "parts": [response.text]}
        ])
        
        # Limit conversation history to prevent excessive memory usage
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        # Escape any special characters that might cause formatting issues
        safe_response = html.escape(response.text)
        await update.message.reply_text(f"{safe_response}\n\nCredits: @AADI_IO")
        
    except Exception as e:
        logger.error(f"Error in chat mode: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing your message. Please try again."
        )
    
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation history"""
    try:
        user_id = update.effective_user.id
        
        if user_id in user_conversations:
            user_conversations[user_id] = []
            await update.message.reply_text(
                "🔄 Conversation history cleared! Continuing in chat mode...\n\n"
                "Credits: @AADI_IO"
            )
        else:
            await update.message.reply_text(
                "No active chat session to clear. Continuing in chat mode...\n\n"
                "Credits: @AADI_IO"
            )
    except Exception as e:
        logger.error(f"Error in newchat command: {e}")
        await update.message.reply_text("Error clearing conversation. Continuing in chat mode...")
    
    return CHAT_MODE

# =========================
# OCR Mode Handlers
# =========================

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in OCR mode"""
    if not update.message.photo:
        await update.message.reply_text(
            "📷 **OCR Mode Active**\n\n"
            "Please send an image containing text for extraction.\n\n"
            "Use /mode to switch modes or /cancel to exit."
        )
        return OCR_MODE
    
    try:
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Get the highest quality photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(photo_bytes))
        
        # Process with Gemini 2.5 Flash Vision
        response = model.generate_content([
            "Extract all the text from this image. Return only the extracted text without any additional commentary or formatting.",
            image
        ])
        
        extracted_text = response.text.strip()
        
        if extracted_text:
            # Escape any special characters
            safe_text = html.escape(extracted_text)
            await update.message.reply_text(
                f"📝 **Extracted Text:**\n\n{safe_text}\n\n"
                f"📷 **OCR Mode still active** - send another image or use /mode to switch.\n\n"
                f"Credits: @AADI_IO"
            )
        else:
            await update.message.reply_text(
                "No text could be extracted from the image.\n\n"
                "📷 **OCR Mode still active** - send another image or use /mode to switch.\n\n"
                "Credits: @AADI_IO"
            )
            
    except Exception as e:
        logger.error(f"Error in OCR mode processing: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing the image. Please try again.\n\n"
            "📷 **OCR Mode still active**\n\n"
            "Credits: @AADI_IO"
        )
    
    return OCR_MODE

# =========================
# Screenshot Mode Handlers
# =========================

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in screenshot mode"""
    if not update.message.photo:
        await update.message.reply_text(
            "🖼️ **Screenshot Mode Active**\n\n"
            "Please send a screenshot for analysis.\n\n"
            "Use /mode to switch modes or /cancel to exit."
        )
        return SSHOT_MODE
    
    try:
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Get the highest quality photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(photo_bytes))
        
        # Analyze with Gemini 2.5 Flash
        analysis_prompt = """
        Analyze this screenshot thoroughly and provide a structured response with:

        1. **Overview**: Brief description of what's visible
        2. **Key Elements**: Important UI components, text, or visual elements
        3. **Issues & Analysis**: Any problems, errors, or notable observations
        4. **Solutions & Recommendations**: Practical steps to resolve identified issues
        5. **Best Practices**: Suggestions for prevention or improvement

        Be specific, actionable, and focus on providing clear guidance.
        """
        
        response = model.generate_content([analysis_prompt, image])
        
        analysis_text = response.text.strip()
        
        if analysis_text:
            # Escape any special characters
            safe_analysis = html.escape(analysis_text)
            await update.message.reply_text(
                f"🖼️ **Screenshot Analysis:**\n\n{safe_analysis}\n\n"
                f"🖼️ **Screenshot Mode still active** - send another screenshot or use /mode to switch.\n\n"
                f"Credits: @AADI_IO"
            )
        else:
            await update.message.reply_text(
                "I couldn't generate a detailed analysis for this screenshot. Please try with a clearer image.\n\n"
                "🖼️ **Screenshot Mode still active** - send another screenshot or use /mode to switch.\n\n"
                "Credits: @AADI_IO"
            )
            
    except Exception as e:
        logger.error(f"Error in screenshot mode analysis: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error analyzing the screenshot. Please try again.\n\n"
            "🖼️ **Screenshot Mode still active**\n\n"
            "Credits: @AADI_IO"
        )
    
    return SSHOT_MODE

# =========================
# Help & About Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "🤖 **Available Commands:**\n\n"
        "/start - Start the bot and select mode\n"
        "/mode - Return to mode selection\n"
        "/newchat - Reset conversation history (in chat mode)\n"
        "/cancel - End conversation\n\n"
        
        "🔘 **Modes:**\n"
        "• 💬 **Chat Mode** - Normal AI conversations\n"
        "• 📷 **OCR Mode** - Extract text from images\n"
        "• 🖼️ **Screenshot Mode** - Analyze screenshots\n\n"
        
        "**Usage:** Select a mode, then interact normally!\n\n"
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = (
        "🤖 **About This Bot**\n\n"
        "**Developer:** @AADI_IO\n\n"
        "**Core Technologies:**\n"
        "• Telegram Bot API\n"
        "• Google Gemini 2.5 Flash AI\n"
        "• FastAPI Web Framework\n"
        "• Python\n\n"
        "**Features:**\n"
        "• Mode-based conversations\n"
        "• AI-powered chat\n"
        "• Image text extraction (OCR)\n"
        "• Screenshot analysis\n\n"
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(about_text)

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an error. Use /mode to return to mode selection."
            )
    except Exception as e:
        logger.error(f"Error while sending error message: {e}")

# =========================
# Bot Setup & Webhook Configuration
# =========================

async def setup_commands(app: Application):
    """Setup bot commands menu"""
    try:
        commands = [
            BotCommand("start", "Start bot and select mode"),
            BotCommand("mode", "Return to mode selection"),
            BotCommand("newchat", "Reset conversation history"),
            BotCommand("help", "Get help guide"),
            BotCommand("about", "About this bot"),
            BotCommand("cancel", "End conversation"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands menu set successfully")
    except Exception as e:
        logger.error(f"Error setting up commands: {e}")

async def initialize_bot():
    """Initialize the Telegram bot and set webhook"""
    global application
    
    # Wait for WEBHOOK_URL to be available (for Render deployment)
    max_retries = 24
    webhook_url_env = None
    
    for i in range(max_retries):
        webhook_url_env = os.getenv('WEBHOOK_URL')
        if webhook_url_env:
            logger.info(f"WEBHOOK_URL found: {webhook_url_env}")
            break
        elif i == max_retries - 1:
            logger.error("WEBHOOK_URL not found after 2 minutes. Exiting.")
            return
        else:
            logger.info(f"Waiting for WEBHOOK_URL... (attempt {i+1}/{max_retries})")
            await asyncio.sleep(5)
    
    if not webhook_url_env:
        logger.error("WEBHOOK_URL not available after retries")
        return

    try:
        # Initialize Telegram application
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .request(HTTPXRequest(connect_timeout=30, read_timeout=30))
            .build()
        )
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Create main conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)
                ],
                CHAT_MODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, chat_mode_handler),
                    CommandHandler("newchat", newchat_command),
                ],
                OCR_MODE: [
                    MessageHandler(filters.PHOTO, ocr_mode_handler),
                ],
                SSHOT_MODE: [
                    MessageHandler(filters.PHOTO, sshot_mode_handler),
                ],
            },
            fallbacks=[
                CommandHandler("mode", mode_command),
                CommandHandler("cancel", cancel_command),
                CommandHandler("start", start_command),
            ],
            allow_reentry=True
        )
        
        # Add conversation handler
        application.add_handler(conv_handler)
        
        # Add global command handlers
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("mode", mode_command))
        
        # Initialize the application properly
        await application.initialize()
        await application.start()
        logger.info("Telegram application initialized and started")
        
        # Setup commands menu
        await setup_commands(application)
        
        # Set webhook
        webhook_url = f"{webhook_url_env}/{TELEGRAM_TOKEN}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
        
        logger.info("Bot initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during bot initialization: {e}")
        if application:
            await application.stop()
        raise

# =========================
# FastAPI Routes & Server Setup
# =========================

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    logger.info("Starting up FastAPI application...")
    asyncio.create_task(initialize_bot())

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown bot application properly"""
    global application
    if application:
        logger.info("Shutting down Telegram application...")
        await application.stop()
        await application.shutdown()
        logger.info("Telegram application stopped successfully")

@app.get("/")
@app.head("/")
async def health_check():
    """Health check endpoint for Render"""
    return JSONResponse(
        content={"status": "ok"},
        status_code=status.HTTP_200_OK
    )

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    """Webhook endpoint for Telegram updates"""
    global application
    
    if token != TELEGRAM_TOKEN:
        logger.warning(f"Invalid token received: {token}")
        return JSONResponse(
            content={"status": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    if not application:
        logger.error("Application not initialized yet")
        return JSONResponse(
            content={"status": "service unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(
            content={"status": "ok"},
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(
            content={"status": "error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
