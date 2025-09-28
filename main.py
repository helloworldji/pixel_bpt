import os
import logging
import asyncio
import html
import uuid
import string
import random
import requests
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters
)
from telegram.request import HTTPXRequest
from telegram.error import BadRequest, Forbidden
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
MAIN_MENU, CHAT_MODE, OCR_MODE, SSHOT_MODE, INSTA_MODE = range(5)

# Instagram Reset Bot Configuration
CHANNELS = [
    {"url": "https://t.me/+YEObPfKXsK1hNjU9", "name": "Main Channel", "id": "-1002628211220"},
    {"url": "https://t.me/pytimebruh", "name": "Backup 1", "id": "@pytimebruh"},
    {"url": "https://t.me/HazyPy", "name": "Backup 2", "id": "@HazyPy"},
    {"url": "https://t.me/HazyGC", "name": "Chat Group", "id": "@HazyGC"}
]

# Initialize Gemini 2.5 Flash model
try:
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    logger.info("Successfully initialized Gemini 2.5 Flash model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini 2.5 Flash model: {e}")
    logger.info("Falling back to gemini-1.5-flash model")
    model = genai.GenerativeModel('gemini-1.5-flash')

# =========================
# Instagram Reset Bot Feature
# =========================

async def check_channel_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to all channels"""
    not_joined = []
    
    for channel in CHANNELS:
        try:
            chat_id = channel['id']
            member = await context.bot.get_chat_member(chat_id, user_id)
            
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
                logger.info(f"User {user_id} not in channel {channel['name']}: {member.status}")
                
        except BadRequest as e:
            logger.error(f"BadRequest checking {channel['name']}: {e}")
            not_joined.append(channel)
            
        except Forbidden as e:
            logger.error(f"Bot not admin in {channel['name']}: {e}")
            not_joined.append(channel)
            
        except Exception as e:
            logger.error(f"Error checking channel {channel['name']}: {e}")
            not_joined.append(channel)
            
    return len(not_joined) == 0, not_joined

async def send_password_reset(target: str):
    """Send password reset request to Instagram"""
    try:
        if '@' in target:
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'user_email': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        else: 
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'username': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        
        headers = {
            'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"
        }
        
        response = requests.post(
            'https://i.instagram.com/api/v1/accounts/send_password_reset/',
            headers=headers,
            data=data,
            timeout=30
        )
        
        if 'obfuscated_email' in response.text:
            return f"✅ *Success!* Password reset link sent for: `{target}`"
        else:
            return f"❌ *Failed* for: `{target}`\nError: {response.text}"
            
    except Exception as e:
        return f"❌ *Error* for: `{target}`\nException: {str(e)}"

async def create_subscription_keyboard(not_joined_channels=None):
    """Create subscription check keyboard"""
    keyboard = []
    
    channels_to_show = not_joined_channels if not_joined_channels else CHANNELS
    
    for channel in channels_to_show:
        keyboard.append([InlineKeyboardButton(
            f"🔗 Join {channel['name']}", 
            url=channel['url']
        )])
    
    keyboard.append([InlineKeyboardButton(
        "✅ I JOINED ALL CHANNELS", 
        callback_data="check_subscription"
    )])
    
    return InlineKeyboardMarkup(keyboard)

async def send_force_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE, not_joined_channels=None):
    """Send force join message"""
    keyboard = await create_subscription_keyboard(not_joined_channels)
    
    message_text = """
🚫 **ACCESS RESTRICTED** 🚫

❗️ **You must join ALL our channels to use Instagram Reset feature!**

📋 **Missing channels:**
"""
    
    if not_joined_channels:
        for channel in not_joined_channels:
            message_text += f"• {channel['name']}\n"
    else:
        message_text += "• Please join all channels below\n"
        
    message_text += """
🔄 **Steps:**
1️⃣ Click each "Join" button below
2️⃣ Join ALL channels/groups  
3️⃣ Click "I JOINED ALL CHANNELS"

⚠️ **Bot will verify your membership!**
    """
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram reset in Instagram mode"""
    user_id = update.effective_user.id
    
    # Check subscription
    subscribed, not_joined = await check_channel_subscription(user_id, context)
    
    if not subscribed:
        await send_force_join_message(update, context, not_joined)
        return INSTA_MODE
    
    # Check if target is provided
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** /rst username_or_email\n**Example:** /rst johndoe",
            parse_mode='Markdown'
        )
        return INSTA_MODE
    
    target = context.args[0]
    processing_msg = await update.message.reply_text(
        f"🔄 **Processing Instagram reset for:** `{target}`", 
        parse_mode='Markdown'
    )
    
    # Send reset request
    result = await send_password_reset(target)
    await processing_msg.edit_text(result, parse_mode='Markdown')
    return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk Instagram reset"""
    user_id = update.effective_user.id
    
    # Check subscription
    subscribed, not_joined = await check_channel_subscription(user_id, context)
    
    if not subscribed:
        await send_force_join_message(update, context, not_joined)
        return INSTA_MODE
    
    # Check if targets are provided
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** /blk user1 user2 user3...\n**Max 10 accounts per request**",
            parse_mode='Markdown'
        )
        return INSTA_MODE
    
    targets = context.args[:10]
    if len(context.args) > 10:
        await update.message.reply_text(
            "⚠️ **Limited to 10 accounts per request**", 
            parse_mode='Markdown'
        )
    
    processing_msg = await update.message.reply_text(
        f"🔄 **Processing bulk Instagram reset for {len(targets)} accounts...**", 
        parse_mode='Markdown'
    )
    
    results = []
    for i, target in enumerate(targets, 1):
        result = await send_password_reset(target)
        results.append(f"{i}. {result}")
        
        if i % 3 == 0 or i == len(targets):
            try:
                await processing_msg.edit_text(
                    "\n".join(results), 
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text(
                    "\n".join(results), 
                    parse_mode='Markdown'
                )
                results = []
        
        await asyncio.sleep(1)
    
    return INSTA_MODE

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
            ["🖼️ Screenshot Mode", "🔓 Instagram Reset"],
            ["❌ Cancel"]
        ]
        
        welcome_message = (
            f"👋 Hello {user.first_name}!\n\n"
            "🤖 **Multi-Feature AI Assistant**\n\n"
            "✨ **Now with INSTAGRAM RESET FEATURE!** ✨\n\n"
            "🔘 **Select a mode to start:**\n"
            "• 💬 **Chat Mode** - AI conversations with Gemini 2.5 Flash\n"
            "• 📷 **OCR Mode** - Extract text from images\n"
            "• 🖼️ **Screenshot Mode** - Analyze screenshots\n"
            "• 🔓 **Instagram Reset** - NEW! Password recovery tool\n\n"
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
    elif text == "🔓 Instagram Reset":
        return await switch_to_insta_mode(update, context)
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

async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to Instagram reset mode"""
    try:
        user_id = update.effective_user.id
        
        # Check subscription status first
        subscribed, not_joined = await check_channel_subscription(user_id, context)
        
        if not subscribed:
            await send_force_join_message(update, context, not_joined)
            return INSTA_MODE
        
        await update.message.reply_text(
            "🔓 **Switched to Instagram Reset Mode**\n\n"
            "✨ **INSTAGRAM PASSWORD RECOVERY TOOL** ✨\n\n"
            "🔑 **Available Commands:**\n"
            "• /rst username - Single account reset\n"
            "• /blk user1 user2 - Bulk reset (max 10)\n"
            "• /mode - Return to mode selection\n\n"
            "📝 **Examples:**\n"
            "/rst johndoe\n"
            "/rst johndoe@gmail.com\n"
            "/blk user1 user2 user3\n\n"
            "Credits: @AADI_IO",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return INSTA_MODE
    except Exception as e:
        logger.error(f"Error switching to Instagram mode: {e}")
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
# Instagram Mode Handlers
# =========================

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in Instagram mode"""
    message_text = update.message.text
    
    # Ignore command messages in Instagram mode
    if message_text.startswith('/'):
        await update.message.reply_text(
            "Use /rst or /blk commands for Instagram reset, or /mode to switch modes."
        )
        return INSTA_MODE
    
    # Show Instagram mode help
    help_text = """
🔓 **Instagram Reset Mode Active**

🔑 **Available Commands:**
• /rst username - Single account reset
• /blk user1 user2 - Bulk reset (max 10 accounts)

📝 **Examples:**
/rst johndoe
/rst johndoe@gmail.com  
/blk user1 user2 user3

💡 **Tips:**
• Use username or email
• Works for both public and private accounts
• High success rate

Use /mode to return to main menu.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')
    return INSTA_MODE

# =========================
# Callback Handlers
# =========================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks for channel subscription"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "check_subscription":
        # Re-check subscription
        subscribed, not_joined = await check_channel_subscription(user_id, context)
        
        if subscribed:
            await query.edit_message_text(
                "✅ **Verification Successful!** 🎉\n\n"
                "🔓 **You can now use Instagram Reset features!**\n\n"
                "Use /rst for single account reset\n"
                "Use /blk for bulk reset\n"
                "Use /mode to return to main menu",
                parse_mode='Markdown'
            )
        else:
            await send_force_join_message(update, context, not_joined)

# =========================
# Help & About Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🤖 **Multi-Feature AI Assistant - Complete Help Guide**

🔘 **Available Modes:**
• 💬 **Chat Mode** - AI conversations with Gemini 2.5 Flash
• 📷 **OCR Mode** - Extract text from images  
• 🖼️ **Screenshot Mode** - Analyze screenshots & provide solutions
• 🔓 **Instagram Reset** - Password recovery tool (requires channel join)

🔑 **Instagram Reset Commands:**
/rst username - Single account reset
/blk user1 user2 - Bulk reset (max 10)

🔄 **General Commands:**
/start - Start bot and select mode
/mode - Return to mode selection  
/newchat - Reset conversation history (in chat mode)
/cancel - End conversation

📝 **Usage:** Select a mode, then interact normally!

✨ **Now featuring INSTAGRAM RESET - Join channels to access!**

Credits: @AADI_IO
    """
    await update.message.reply_text(help_text)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = """
🤖 **About This Multi-Feature Bot**

**Developer:** @AADI_IO

**Core Technologies:**
• Telegram Bot API
• Google Gemini 2.5 Flash AI
• FastAPI Web Framework
• Python

**✨ Featured Capabilities:**
• AI-powered conversations
• Image text extraction (OCR)
• Screenshot analysis & troubleshooting
• **NEW: Instagram Password Recovery**

**Instagram Reset Feature:**
• High success rate password recovery
• Bulk account support
• Advanced reset methods
• Channel-verified access

Credits: @AADI_IO
    """
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
            BotCommand("rst", "Instagram single account reset"),
            BotCommand("blk", "Instagram bulk reset (max 10)"),
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
                INSTA_MODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler),
                    CommandHandler("rst", insta_reset_command),
                    CommandHandler("blk", insta_bulk_command),
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
        
        # Add callback handler for Instagram reset
        application.add_handler(CallbackQueryHandler(button_callback))
        
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
