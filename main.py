import os
import logging
import asyncio
import html
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
application = None

# Store conversation history
user_conversations = {}

# Conversation states
WAITING_FOR_IMAGE = 1
WAITING_FOR_SCREENSHOT = 2

# Initialize Gemini models
text_model = genai.GenerativeModel('gemini-pro')
vision_model = genai.GenerativeModel('gemini-pro-vision')

# =========================
# Bot Command Handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        welcome_message = (
            f"👋 Hello {user.first_name}!\n\n"
            "I'm your Gemini-powered AI assistant 🤖\n\n"
            "You can access all features through the commands - "
            "use the 'Menu' button to see what I can do!\n\n"
            "Credits: @AADI_IO"
        )
        await update.message.reply_text(welcome_message)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use the menu to see available commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    try:
        help_text = (
            "🤖 Available Commands:\n\n"
            
            "/start - Welcome message and introduction\n"
            "Example: Just send /start\n\n"
            
            "/help - This help guide\n"
            "Example: /help\n\n"
            
            "/about - Information about the bot\n"
            "Example: /about\n\n"
            
            "/chat [your question] - Chat with Gemini AI\n"
            "Example: /chat What is the capital of France?\n"
            "Example: /chat Explain quantum computing in simple terms\n\n"
            
            "/newchat - Reset your conversation history\n"
            "Example: /newchat\n\n"
            
            "/ocr - Extract text from images\n"
            "Example: Send /ocr and then send an image\n\n"
            
            "/sshot - Analyze screenshots and provide solutions\n"
            "Example: Send /sshot and then send a screenshot for analysis\n\n"
            
            "Credits: @AADI_IO"
        )
        await update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await update.message.reply_text("Help: Use /chat for AI conversations, /ocr for text extraction, /sshot for screenshot analysis.")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    try:
        about_text = (
            "🤖 About This Bot\n\n"
            "Developer: @AADI_IO\n\n"
            "Core Technologies:\n"
            "• Telegram Bot API\n"
            "• Google Gemini AI\n"
            "• FastAPI Web Framework\n"
            "• Python\n\n"
            "Features:\n"
            "• AI-powered conversations\n"
            "• Image text extraction (OCR)\n"
            "• Screenshot analysis & troubleshooting\n\n"
            "Credits: @AADI_IO"
        )
        await update.message.reply_text(about_text)
    except Exception as e:
        logger.error(f"Error in about command: {e}")
        await update.message.reply_text("About: Gemini AI Telegram Bot by @AADI_IO")

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
        
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Generate response using Gemini with history
        chat_session = text_model.start_chat(history=user_conversations[user_id])
        response = chat_session.send_message(question)
        
        # Update conversation history
        user_conversations[user_id].extend([
            {"role": "user", "parts": [question]},
            {"role": "model", "parts": [response.text]}
        ])
        
        # Limit conversation history to prevent excessive memory usage
        if len(user_conversations[user_id]) > 20:  # Keep last 10 exchanges
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        # Escape any special characters that might cause formatting issues
        safe_response = html.escape(response.text)
        await update.message.reply_text(f"{safe_response}\n\nCredits: @AADI_IO")
        
    except Exception as e:
        logger.error(f"Error in chat command: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing your request. Please try again.\n\n"
            "Credits: @AADI_IO"
        )

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newchat command to reset conversation"""
    try:
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
    except Exception as e:
        logger.error(f"Error in newchat command: {e}")
        await update.message.reply_text("Error clearing conversation. Please try again.")

# =========================
# OCR Feature Implementation
# =========================

async def ocr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start OCR conversation"""
    try:
        await update.message.reply_text(
            "📷 OCR Text Extraction\n\n"
            "Please send the image you want me to scan for text.\n\n"
            "To cancel, send /cancel"
        )
        return WAITING_FOR_IMAGE
    except Exception as e:
        logger.error(f"Error in OCR start: {e}")
        return ConversationHandler.END

async def ocr_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel OCR conversation"""
    try:
        await update.message.reply_text("OCR operation cancelled.")
    except Exception as e:
        logger.error(f"Error in OCR cancel: {e}")
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
            # Escape any special characters
            safe_text = html.escape(extracted_text)
            await update.message.reply_text(
                f"📝 Extracted Text:\n\n{safe_text}\n\nCredits: @AADI_IO"
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

# =========================
# Screenshot Analysis Feature Implementation
# =========================

async def sshot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start screenshot analysis conversation"""
    try:
        await update.message.reply_text(
            "🖼️ Screenshot Analysis\n\n"
            "Please send the screenshot you want me to analyze.\n\n"
            "I can help with:\n"
            "• Error message analysis\n"
            "• UI/UX feedback\n"
            "• Technical troubleshooting\n"
            "• General insights\n\n"
            "To cancel, send /cancel"
        )
        return WAITING_FOR_SCREENSHOT
    except Exception as e:
        logger.error(f"Error in sshot start: {e}")
        return ConversationHandler.END

async def sshot_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel screenshot analysis conversation"""
    try:
        await update.message.reply_text("Screenshot analysis cancelled.")
    except Exception as e:
        logger.error(f"Error in sshot cancel: {e}")
    return ConversationHandler.END

async def analyze_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze screenshot and provide solutions"""
    if not update.message.photo:
        await update.message.reply_text(
            "Please send a screenshot image. To cancel, send /cancel"
        )
        return WAITING_FOR_SCREENSHOT
    
    try:
        # Send "typing" action
        await update.message.chat.send_action(action="typing")
        
        # Get the highest quality photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(photo_bytes))
        
        # Analyze with Gemini Vision
        analysis_prompt = """
        Analyze this screenshot and provide:

        1. Overview: What appears to be happening in this screenshot?
        2. Key Elements: What are the main UI components, text, or error messages visible?
        3. Issues Identified: If there are any problems, errors, or areas of concern, list them clearly.
        4. Solutions/Recommendations: Provide step-by-step solutions or recommendations to fix any identified issues.
        5. Best Practices: If applicable, suggest best practices to prevent similar issues.

        Be specific, practical, and helpful. Focus on actionable advice.
        """
        
        response = vision_model.generate_content([analysis_prompt, image])
        
        analysis_text = response.text.strip()
        
        if analysis_text:
            # Escape any special characters
            safe_analysis = html.escape(analysis_text)
            await update.message.reply_text(
                f"🖼️ Screenshot Analysis\n\n{safe_analysis}\n\nCredits: @AADI_IO"
            )
        else:
            await update.message.reply_text(
                "I couldn't generate a detailed analysis for this screenshot. Please try with a clearer image.\n\nCredits: @AADI_IO"
            )
            
    except Exception as e:
        logger.error(f"Error in screenshot analysis: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error analyzing the screenshot. Please try again.\n\n"
            "Credits: @AADI_IO"
        )
    
    return ConversationHandler.END

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        # Notify user about the error
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an error processing your request. Please try again."
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
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Get help and usage guide"),
            BotCommand("about", "About this bot"),
            BotCommand("chat", "Chat with Gemini AI"),
            BotCommand("newchat", "Reset conversation"),
            BotCommand("ocr", "Extract text from images"),
            BotCommand("sshot", "Analyze screenshots"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands menu set successfully")
    except Exception as e:
        logger.error(f"Error setting up commands: {e}")

async def initialize_bot():
    """Initialize the Telegram bot and set webhook"""
    global application
    
    # Wait for WEBHOOK_URL to be available (for Render deployment)
    max_retries = 24  # 2 minutes at 5-second intervals
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
        
        # Screenshot Analysis Conversation Handler
        sshot_handler = ConversationHandler(
            entry_points=[CommandHandler("sshot", sshot_start)],
            states={
                WAITING_FOR_SCREENSHOT: [
                    MessageHandler(filters.PHOTO, analyze_screenshot),
                    CommandHandler("cancel", sshot_cancel)
                ],
            },
            fallbacks=[CommandHandler("cancel", sshot_cancel)],
        )
        
        # Regular command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("chat", chat_command))
        application.add_handler(CommandHandler("newchat", newchat_command))
        application.add_handler(ocr_handler)
        application.add_handler(sshot_handler)
        
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
