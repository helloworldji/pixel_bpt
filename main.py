import os
import logging
import asyncio
import google.generativeai as genai
from telegram import Update, BotCommand
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
telegram_app = None

# Store conversation history
user_conversations = {}

# Conversation states for OCR
WAITING_FOR_IMAGE = 1

# Initialize Gemini models
text_model = genai.GenerativeModel('gemini-pro')
vision_model = genai.GenerativeModel('gemini-pro-vision')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    welcome_message = (
        f"👋 Hello {user.first_name}!\n\n"
        "I'm your Gemini-powered AI assistant 🤖\n\n"
        "You can access all features through the commands - "
        "use the 'Menu' button to see what I can do!\n\n"
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "🤖 **Available Commands:**\n\n"
        
        "**/start** - Welcome message and introduction\n"
        "_Example: Just send /start_\n\n"
        
        "**/help** - This help guide\n"
        "_Example: /help_\n\n"
        
        "**/about** - Information about the bot\n"
        "_Example: /about_\n\n"
        
        "**/chat [your question]** - Chat with Gemini AI\n"
        "_Example: /chat What is the capital of France?_\n"
        "_Example: /chat Explain quantum computing in simple terms_\n\n"
        
        "**/newchat** - Reset your conversation history\n"
        "_Example: /newchat_\n\n"
        
        "**/ocr** - Extract text from images\n"
        "_Example: Send /ocr and then send an image_\n\n"
        
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = (
        "🤖 **About This Bot**\n\n"
        "**Developer:** @AADI_IO\n\n"
        "**Core Technologies:**\n"
        "• Telegram Bot API\n"
        "• Google Gemini AI\n"
        "• FastAPI Web Framework\n"
        "• Python\n\n"
        "This bot demonstrates the integration of Google's Gemini AI "
        "with Telegram to provide intelligent conversation and image "
        "analysis capabilities.\n\n"
        "Credits: @AADI_IO"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chat command with Gemini AI"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Extract the question after /chat command
    if len(message_text.split()) < 2:
        await update.message.reply_text(
            "Please provide a question after the /chat command.\n"
            "Example: /chat What is artificial intelligence?"
        )
        return
    
    question = ' '.join(message_text.split()[1:])
    
    try:
        # Initialize conversation history if not exists
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        # Add user message to history
        user_conversations[user_id].append({"role": "user", "parts": [question]})
        
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Generate response using Gemini
        chat_session = text_model.start_chat(history=user_conversations[user_id][:-1])
        response = chat_session.send_message(question)
        
        # Add assistant response to history
        user_conversations[user_id].append({"role": "model", "parts": [response.text]})
        
        # Limit conversation history to prevent excessive memory usage
        if len(user_conversations[user_id]) > 20:  # Keep last 10 exchanges
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        await update.message.reply_text(f"{response.text}\n\nCredits: @AADI_IO")
        
    except Exception as e:
        logger.error(f"Error in chat command: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing your request. Please try again."
        )

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newchat command to reset conversation"""
    user_id = update.effective_user.id
    
    if user_id in user_conversations:
        user_conversations[user_id] = []
        await update.message.reply_text(
            "🔄 Conversation history cleared! Starting a new chat session.\n\n"
            "Credits: @AADI_IO"
        )
    else:
        await update.message.reply_text(
            "You don't have an active chat session. Start one with /chat!\n\n"
            "Credits: @AADI_IO"
        )

async def ocr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start OCR conversation"""
    await update.message.reply_text(
        "📷 Please send the image you want me to scan for text.\n\n"
        "To cancel, send /cancel"
    )
    return WAITING_FOR_IMAGE

async def ocr_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel OCR conversation"""
    await update.message.reply_text("OCR operation cancelled.")
    return ConversationHandler.END

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process image for OCR"""
    if not update.message.photo:
        await update.message.reply_text(
            "Please send an image file. To cancel, send /cancel"
        )
        return WAITING_FOR_IMAGE
    
    try:
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Get the highest quality photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(photo_bytes))
        
        # Process with Gemini Vision
        response = vision_model.generate_content([
            "Extract all the text from this image. Return only the extracted text without any additional commentary or formatting.",
            image
        ])
        
        extracted_text = response.text.strip()
        
        if extracted_text:
            await update.message.reply_text(
                f"📝 **Extracted Text:**\n\n{extracted_text}\n\nCredits: @AADI_IO",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "No text could be extracted from the image.\n\nCredits: @AADI_IO"
            )
            
    except Exception as e:
        logger.error(f"Error in OCR processing: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing the image. Please try again.\n\n"
            "Credits: @AADI_IO"
        )
    
    return ConversationHandler.END

async def setup_commands(application: Application):
    """Setup bot commands menu"""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help and usage guide"),
        BotCommand("about", "About this bot"),
        BotCommand("chat", "Chat with Gemini AI"),
        BotCommand("newchat", "Reset conversation"),
        BotCommand("ocr", "Extract text from images"),
    ]
    await application.bot.set_my_commands(commands)

async def initialize_bot():
    """Initialize the Telegram bot and set webhook"""
    global telegram_app
    
    # Wait for WEBHOOK_URL to be available (for Render deployment)
    max_retries = 24  # 2 minutes at 5-second intervals
    for i in range(max_retries):
        webhook_url = os.getenv('WEBHOOK_URL')
        if webhook_url:
            logger.info(f"WEBHOOK_URL found: {webhook_url}")
            break
        elif i == max_retries - 1:
            logger.error("WEBHOOK_URL not found after 2 minutes. Exiting.")
            return
        else:
            logger.info(f"Waiting for WEBHOOK_URL... (attempt {i+1}/{max_retries})")
            await asyncio.sleep(5)
    
    # Initialize Telegram application
    telegram_app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .request(HTTPXRequest(connect_timeout=30, read_timeout=30))
        .build()
    )
    
    # Add handlers
    # OCR Conversation Handler
    ocr_handler = ConversationHandler(
        entry_points=[CommandHandler("ocr", ocr_start)],
        states={
            WAITING_FOR_IMAGE: [
                MessageHandler(filters.PHOTO, process_image),
                CommandHandler("cancel", ocr_cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", ocr_cancel)],
    )
    
    # Regular command handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("about", about_command))
    telegram_app.add_handler(CommandHandler("chat", chat_command))
    telegram_app.add_handler(CommandHandler("newchat", newchat_command))
    telegram_app.add_handler(ocr_handler)
    
    # Setup commands menu
    await setup_commands(telegram_app)
    
    # Set webhook
    webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")
    
    logger.info("Bot initialization completed successfully!")

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    logger.info("Starting up FastAPI application...")
    asyncio.create_task(initialize_bot())

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
    if token != TELEGRAM_TOKEN:
        logger.warning(f"Invalid token received: {token}")
        return JSONResponse(
            content={"status": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
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
