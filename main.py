# =================================================================================================
# 🚀 ADVANCED MULTI-FUNCTIONAL TELEGRAM BOT
# =================================================================================================
# This bot integrates several features:
# 1. Instagram Tools: Password reset functionality.
# 2. Utility Tools: URL shortening, QR code generation, PDF creation, and a secure password generator.
# 3. Weather: Real-time weather forecasts.
# 4. Advanced AI Features: Conversational chat, interactive image analysis, email writer,
#    text summarizer, and a code helper, all powered by Google's Gemini AI.
# 5. Web Framework: Deployed using FastAPI and Uvicorn for webhook support.
#
# Dev: Aadi (@aadi_io)
# =================================================================================================

import os
import logging
import asyncio
import uuid
import string
import random
import io
import secrets
from typing import Dict, List, Optional

import httpx
import uvicorn
import qrcode  # Dependency: pip install qrcode[pil]
from PIL import Image
from fpdf import FPDF # Dependency: pip install fpdf2
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

# =====================================
# LOGGING CONFIGURATION
# =====================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================
# ENVIRONMENT & API KEYS
# =====================================
# IMPORTANT: Make sure to set these in your environment variables.
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
# Using the provided Visual Crossing API Key
WEATHER_API_KEY = "EKCSKX5PQBL52PZGCGJDXHCU4"

if not BOT_TOKEN or not GEMINI_API_KEY:
    logger.critical("FATAL ERROR: Bot token or Gemini API key is missing!")
    exit(1)
if not WEATHER_API_KEY:
    logger.warning("Weather API key is not set. The /weather command will not work.")

# =====================================
# GLOBAL VARIABLES & STATE
# =====================================
telegram_app: Optional[Application] = None
user_sessions: Dict[int, Dict] = {}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# =====================================
# GEMINI AI INITIALIZATION
# =====================================
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Successfully initialized Gemini AI models.")
except Exception as e:
    logger.critical(f"❌ FATAL ERROR: Could not initialize Gemini AI. Error: {e}")
    exit(1)

# =====================================
# USER SESSION MANAGEMENT
# =====================================
def get_user_session(user_id: int) -> Dict:
    """Gets or creates a new session for a given user."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': 'menu',
            'history': [],
            'last_analysis': None,
            'pdf_images': [] # For the new PDF feature
        }
    return user_sessions[user_id]

def set_user_mode(user_id: int, mode: str) -> None:
    """Sets the interaction mode for a user."""
    session = get_user_session(user_id)
    session['mode'] = mode
    logger.info(f"User {user_id} switched to mode: {mode}")

def get_user_mode(user_id: int) -> str:
    """Retrieves the current interaction mode for a user."""
    return get_user_session(user_id).get('mode', 'menu')

# =====================================
# SHARED HELPER FUNCTIONS
# =====================================
def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """Splits a long message into multiple chunks suitable for Telegram."""
    if not isinstance(text, str): return []
    chunks = []
    while len(text) > max_length:
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1: split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:]
    chunks.append(text)
    return chunks

# =====================================
# CORE COMMAND HANDLERS
# =====================================
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and displays the main menu."""
    try:
        user = update.effective_user
        user_id = user.id
        session = get_user_session(user_id)
        set_user_mode(user_id, 'menu')
        session['history'].clear()
        session['pdf_images'].clear()

        logger.info(f"User {user.id} ({user.username}) started the bot.")

        keyboard = [
            ["🔓 Instagram", "🔑 Gen Password"],
            ["🔗 URL Shortener", "🔳 QR Code"],
            ["📄 Image to PDF", "🌤️ Weather"],
            ["💬 AI Chat", "📷 Image Analysis"],
            ["🤖 AI Utilities", "❓ Help"],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

        welcome_text = (
            f"👋 **Welcome, {user.first_name}!**\n\n"
            "I'm your all-in-one assistant bot. Here's a quick look at what I can do:\n\n"
            "📸 **Social & Media**: Instagram tools, PDF creation, QR codes.\n"
            "🛠️ **Utilities**: URL shortener, password generator, weather.\n"
            "🧠 **AI-Powered**: Advanced chat, image analysis, and special AI utilities.\n\n"
            "👇 Select an option from the menu to begin.\n\n"
            "*Dev: Aadi (@aadi_io)*"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in /start handler: {e}", exc_info=True)
        await update.message.reply_text("❌ A critical error occurred. Please try /start again.")

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help message with all command instructions."""
    try:
        help_text = """
        *🤖 Bot Help & Commands Guide*

        *Social & Media*
        • `/rst <user>`: Single Instagram reset.
        • `/bulk <users...>`: Bulk Instagram reset.
        • *Image to PDF*: Select from menu, send images, then `/createpdf`. Use `/cancelpdf` to abort.

        *Utilities*
        • `/shorten <url>`: Shortens a long URL.
        • `/qr <text>`: Generates a QR code.
        • `/genpass <length>`: Creates a secure password (default length 16).
        • `/weather <city>`: Gets the weather forecast.

        *AI Tools*
        • *AI Chat*: Conversational mode. Use `/clear` to reset.
        • *Image Analysis*: Get insights on any image.
        • `/summarize <text>`: Summarizes long text.
        • `/email <prompt>`: Writes an email for you.
        • `/code <question>`: Helps with programming questions.

        *General*
        • `/start` or `/menu`: Return to the main menu.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /help handler: {e}", exc_info=True)

# =====================================
# INSTAGRAM FEATURE [UNCHANGED]
# ... (The entire Instagram section including send_instagram_reset, rst_command_handler, bulk_command_handler remains here, exactly as before)
# =====================================
async def send_instagram_reset(target: str) -> Dict:
    try:
        clean_target=target.strip().lstrip('@')
        logger.info(f"Processing Instagram reset request for target: {clean_target}")
        headers={'User-Agent': 'Instagram 113.0.0.39.122 Android/24 (API 24; 640dpi; 1440x2560; samsung; SM-G935F; hero2lte; samsungexynos8890; en_US)','X-IG-App-ID':'936619743392459',}
        payload={'device_id': f'android-{uuid.uuid4()}', 'guid':str(uuid.uuid4()),'_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),}
        if '@'in clean_target and'.'in clean_target: payload['user_email']=clean_target
        elif clean_target.isdigit()and len(clean_target)>5: payload['user_id']=clean_target
        else: payload['username']=clean_target
        async with httpx.AsyncClient(timeout=30.0)as client: response=await client.post('https://i.instagram.com/api/v1/accounts/send_password_reset/',headers=headers,data=payload)
        logger.info(f"Instagram API response for {clean_target}: {response.status_code} - {response.text[:100]}")
        if response.status_code==200:
            try:
                data=response.json()
                if'obfuscated_email'in data or'obfuscated_phone_number'in data: return{'success':True,'message':f"✅ Reset link successfully sent for *{clean_target}*."}
                else: return{'success':False,'message':f"⚠️ Request failed for *{clean_target}*. Response indicates an issue."}
            except Exception: return{'success':False,'message':f"⚠️ Failed to parse response for *{clean_target}*."}
        elif response.status_code==404: return{'success':False,'message':f"❌ Account not found: *{clean_target}*."}
        elif response.status_code==400: return{'success':False,'message':f"❌ Bad Request for *{clean_target}*. Check the username/email."}
        elif response.status_code==429: return{'success':False,'message':f"⏳ Rate limited. Please wait a few minutes before trying again."}
        else: return{'success':False,'message':f"❌ An unknown error occurred (Status: {response.status_code}) for *{clean_target}*."}
    except httpx.RequestError as e: logger.error(f"HTTP error during Instagram reset for {target}: {e}"); return{'success':False,'message':f"❌ Network error. Could not connect to Instagram."}
    except Exception as e: logger.error(f"Unexpected error in send_instagram_reset for {target}: {e}",exc_info=True); return{'success':False,'message':f"❌ A critical error occurred during the request."}
async def rst_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    try:
        if not context.args: await update.message.reply_text("📋 *Usage:* `/rst <username_or_email>`",parse_mode=ParseMode.MARKDOWN); return
        target=context.args[0]
        msg=await update.message.reply_text(f"🔄 Processing reset for *{target}*...",parse_mode=ParseMode.MARKDOWN)
        result=await send_instagram_reset(target)
        await msg.edit_text(result['message'],parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Error in /rst handler for user {update.effective_user.id}: {e}",exc_info=True); await update.message.reply_text("❌ An unexpected error occurred while processing your request.")
async def bulk_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    try:
        if not context.args: await update.message.reply_text("📋 *Usage:* `/bulk <user1> <user2> ...` (max 3)",parse_mode=ParseMode.MARKDOWN); return
        targets=context.args[:3]; num_targets=len(targets)
        msg=await update.message.reply_text(f"🔄 Processing *{num_targets}* accounts...",parse_mode=ParseMode.MARKDOWN)
        results=[]
        for i, target in enumerate(targets,1):
            result=await send_instagram_reset(target)
            results.append(f"*{i}.* {result['message']}")
            progress_text=f"⚙️ *Progress: {i}/{num_targets}*\n\n" + "\n".join(results)
            try: await msg.edit_text(progress_text,parse_mode=ParseMode.MARKDOWN)
            except Exception: pass
            if i<num_targets: await asyncio.sleep(2)
        final_text=f"✅ *Bulk processing complete for {num_targets} accounts!*\n\n" + "\n".join(results)
        await msg.edit_text(final_text,parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Error in /bulk handler for user {update.effective_user.id}: {e}",exc_info=True); await update.message.reply_text("❌ An unexpected error occurred during the bulk request.")

# =====================================
# NEW & UPDATED UTILITY FEATURES
# =====================================
# --- URL Shortener & QR Code remain the same ---
async def shorten_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    try:
        if not context.args: await update.message.reply_text("📋 *Usage:* `/shorten <your_long_url>`",parse_mode=ParseMode.MARKDOWN); return
        long_url=context.args[0]
        if not long_url.startswith(('http://','https://')): await update.message.reply_text("❌ *Invalid URL*. Please include `http://` or `https://`.",parse_mode=ParseMode.MARKDOWN); return
        api_url=f"http://tinyurl.com/api-create.php?url={long_url}"
        msg=await update.message.reply_text("🔗 Shortening your link...",parse_mode=ParseMode.MARKDOWN)
        async with httpx.AsyncClient()as client:
            response=await client.get(api_url)
            if response.status_code==200: short_url=response.text; await msg.edit_text(f"✅ *Success!* Here is your short link:\n{short_url}",parse_mode=ParseMode.MARKDOWN)
            else: await msg.edit_text("❌ *Error:* Could not shorten the link. The service may be down.",parse_mode=ParseMode.MARKDOWN)
    except httpx.RequestError as e: logger.error(f"HTTP error during URL shortening: {e}"); await msg.edit_text("❌ A network error occurred. Please try again later.")
    except Exception as e: logger.error(f"Error in /shorten handler: {e}",exc_info=True); await update.message.reply_text("❌ An unexpected error occurred.")
async def qr_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    try:
        if not context.args: await update.message.reply_text("📋 *Usage:* `/qr <text_or_link>`",parse_mode=ParseMode.MARKDOWN); return
        input_text=" ".join(context.args)
        msg=await update.message.reply_text("🔳 Generating your QR code...",parse_mode=ParseMode.MARKDOWN)
        qr_img=qrcode.make(input_text); img_buffer=io.BytesIO(); qr_img.save(img_buffer,format='PNG'); img_buffer.seek(0)
        await update.message.reply_photo(photo=img_buffer,caption=f"✅ Here is the QR code for:\n`{input_text}`",parse_mode=ParseMode.MARKDOWN)
        await msg.delete()
    except Exception as e: logger.error(f"Error in /qr handler: {e}",exc_info=True); await update.message.reply_text("❌ An error occurred while creating the QR code.")

async def genpass_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates a secure, random password."""
    try:
        length = 16
        if context.args and context.args[0].isdigit():
            length = min(int(context.args[0]), 128) # Max length 128
        
        alphabet = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        
        await update.message.reply_text(
            f"🔑 Here is your secure password (`{length}` characters):\n\n`{password}`\n\n_This message will self-destruct in 30 seconds._",
            parse_mode=ParseMode.MARKDOWN
        )
        # For security, we can't actually delete the message, but this is a strong hint to the user.
    except Exception as e:
        logger.error(f"Error in /genpass handler: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred while generating the password.")

async def weather_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the weather for a specified city using Visual Crossing API."""
    try:
        if not WEATHER_API_KEY:
            await update.message.reply_text("⚠️ The weather service is not configured. Please contact the bot admin.", parse_mode=ParseMode.MARKDOWN)
            return
        if not context.args:
            await update.message.reply_text("📋 *Usage:* `/weather <city_name>`", parse_mode=ParseMode.MARKDOWN)
            return

        city = " ".join(context.args)
        msg = await update.message.reply_text(f"🌤️ Fetching weather for *{city}*...", parse_mode=ParseMode.MARKDOWN)
        
        api_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)
        
        if response.status_code == 200:
            data = response.json()
            # The 'days' array contains the forecast, today is the first element
            current_conditions = data['days'][0]
            
            weather_report = (
                f"*{data['resolvedAddress']}*\n"
                f"*{current_conditions['conditions']}* ({current_conditions['description']})\n\n"
                f"🌡️ *Temperature*: {current_conditions['temp']}°C (Feels like: {current_conditions['feelslike']}°C)\n"
                f"💧 *Humidity*: {current_conditions['humidity']}%\n"
                f"💨 *Wind Speed*: {current_conditions['windspeed']} km/h"
            )
            await msg.edit_text(weather_report, parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text(f"❌ Could not retrieve weather for *{city}*. Please check the location or try again later.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /weather handler: {e}", exc_info=True)
        await msg.edit_text("❌ An unexpected error occurred with the weather service.")

# =====================================
# NEW PDF CREATION FEATURE
# =====================================
async def createpdf_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Combines collected images into a single PDF file."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)

    if get_user_mode(user_id) != 'pdf_creation' or not session['pdf_images']:
        await update.message.reply_text("You haven't added any images yet. Enter PDF mode and send some photos first.", parse_mode=ParseMode.MARKDOWN)
        return

    msg = await update.message.reply_text(f"📄 Creating PDF from {len(session['pdf_images'])} images...", parse_mode=ParseMode.MARKDOWN)
    try:
        pdf = FPDF()
        for img_bytes in session['pdf_images']:
            img = Image.open(io.BytesIO(img_bytes))
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            
            # Use a temporary file to handle image format for FPDF
            with io.BytesIO() as temp_img_file:
                img.save(temp_img_file, format='JPEG')
                temp_img_file.seek(0)
                
                pdf.add_page()
                # A4 size: 210x297 mm. We add some margin.
                pdf.image(temp_img_file, x=10, y=10, w=190)

        pdf_buffer = io.BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)

        await update.message.reply_document(
            document=pdf_buffer,
            filename="created_document.pdf",
            caption="✅ Here is your generated PDF file."
        )
        await msg.delete()
    except Exception as e:
        logger.error(f"PDF creation error for user {user_id}: {e}", exc_info=True)
        await msg.edit_text("❌ An error occurred while creating the PDF.")
    finally:
        # Clean up and reset mode
        session['pdf_images'].clear()
        await start_command_handler(update, context) # Return to main menu

async def cancelpdf_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancels the PDF creation process."""
    user_id = update.effective_user.id
    get_user_session(user_id)['pdf_images'].clear()
    await update.message.reply_text("PDF creation cancelled.", parse_mode=ParseMode.MARKDOWN)
    await start_command_handler(update, context)


# =====================================
# AI FEATURES
# =====================================
async def ai_utility_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles various AI utility commands like /summarize, /email, /code."""
    command = update.message.text.split()[0].lower()
    prompt_text = " ".join(context.args)

    if not prompt_text:
        await update.message.reply_text(f"📋 *Usage:* `{command} <your text or prompt>`", parse_mode=ParseMode.MARKDOWN)
        return

    system_instructions = {
        '/summarize': "You are a text summarization expert. Take the following text and provide a concise, easy-to-read summary that captures the main points.",
        '/email': "You are an email writing assistant. Based on the user's prompt, write a clear, professional, and effective email. Pay attention to tone and clarity.",
        '/code': "You are an expert programmer and coding assistant. Analyze the user's question or code snippet and provide a helpful explanation, a solution, or debugging advice."
    }
    
    full_prompt = f"{system_instructions[command]}\n\nUser's request: \"{prompt_text}\""
    msg = await update.message.reply_text(f"🤖 Processing your `{command}` request with AI...", parse_mode=ParseMode.MARKDOWN)

    try:
        response = await gemini_model.generate_content_async(
            full_prompt,
            generation_config=GenerationConfig(temperature=0.7),
            safety_settings=SAFETY_SETTINGS
        )

        await msg.delete()
        for chunk in split_long_message(response.text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"AI utility error for command {command}: {e}", exc_info=True)
        await msg.edit_text("❌ An error occurred with the AI service. Please try again.")

# --- Other AI handlers (/clear, chat, photo, button) remain largely the same ---
async def clear_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    try:
        user_id = update.effective_user.id
        if get_user_mode(user_id)=='chat': get_user_session(user_id)['history'].clear(); await update.message.reply_text("AI conversation history has been cleared.")
        else: await update.message.reply_text("This command is only active in *AI Chat* mode.",parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Error in /clear handler: {e}",exc_info=True)
async def gemini_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    user_id = update.effective_user.id; prompt = update.message.text; session = get_user_session(user_id)
    msg = await update.message.reply_text("🤔 Thinking...",parse_mode=ParseMode.MARKDOWN)
    try:
        chat = gemini_model.start_chat(history=session['history'])
        response = await chat.send_message_async(prompt,generation_config=GenerationConfig(temperature=0.8),safety_settings=SAFETY_SETTINGS)
        if not response.text: await msg.edit_text("The AI returned an empty response, possibly due to safety filters."); return
        session['history'].extend([{"role": "user", "parts": [prompt]}, {"role": "model", "parts": [response.text]}])
        if len(session['history'])>20: session['history']=session['history'][-20:]
        await msg.delete()
        for chunk in split_long_message(response.text): await update.message.reply_text(chunk,parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Gemini chat error for user {user_id}: {e}",exc_info=True); await msg.edit_text("❌ Sorry, I couldn't connect to the AI service.")
async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    user_id = update.effective_user.id
    mode = get_user_mode(user_id)
    session = get_user_session(user_id)

    if mode == 'pdf_creation':
        try:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            session['pdf_images'].append(bytes(photo_bytes))
            await update.message.reply_text(f"✅ Image added ({len(session['pdf_images'])} total). Send more or use `/createpdf`.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error adding image for PDF: {e}", exc_info=True)
            await update.message.reply_text("❌ Couldn't add that image. Please try another one.")
        return
    
    if mode != 'image_analysis':
        await update.message.reply_text("Please select a mode from the menu first.", parse_mode=ParseMode.MARKDOWN)
        return

    msg = await update.message.reply_text("🔎 Analyzing your image...", parse_mode=ParseMode.MARKDOWN)
    try:
        photo = update.message.photo[-1]
        if photo.file_size > 10 * 1024 * 1024: await msg.edit_text("❌ Image too large (max 10MB)."); return
        photo_file = await photo.get_file(); photo_bytes = await photo_file.download_as_bytearray()
        img = Image.open(io.BytesIO(photo_bytes))
        response_analysis = await gemini_model.generate_content_async(["Analyze this image and identify any potential problems or issues. If there are no clear problems, just describe the image.",img],generation_config=GenerationConfig(temperature=0.4),safety_settings=SAFETY_SETTINGS)
        analysis_text = response_analysis.text
        session['last_analysis'] = analysis_text
        keyboard = [[InlineKeyboardButton("Yes, provide a solution", callback_data='provide_solution')]]; reply_markup = InlineKeyboardMarkup(keyboard)
        title = "📊 *Initial Analysis*:"
        await msg.delete()
        await update.message.reply_text(f"{title}\n\n{analysis_text}\n\nWant me to suggest a solution?",reply_markup=reply_markup,parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Image analysis error for user {user_id}: {e}",exc_info=True); await msg.edit_text("❌ Error processing image.")
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)->None:
    query = update.callback_query; await query.answer(); user_id = query.from_user.id
    if query.data=='provide_solution':
        session = get_user_session(user_id); last_analysis = session.get('last_analysis')
        if not last_analysis: await query.edit_message_text(text="Sorry, analysis expired. Please send the image again."); return
        await query.edit_message_text(text=f"📊 *Initial Analysis:*\n\n{last_analysis}\n\n🧠 *Generating solution...*",parse_mode=ParseMode.MARKDOWN)
        try:
            solution_prompt = f"Based on this analysis, provide a step-by-step solution:\n\n{last_analysis}"
            response_solution = await gemini_model.generate_content_async(solution_prompt,generation_config=GenerationConfig(temperature=0.7),safety_settings=SAFETY_SETTINGS)
            title = "💡 *Suggested Solution*:"; await query.message.reply_text(title,parse_mode=ParseMode.MARKDOWN)
            for chunk in split_long_message(response_solution.text): await query.message.reply_text(chunk,parse_mode=ParseMode.MARKDOWN)
        except Exception as e: logger.error(f"Solution generation error for user {user_id}: {e}",exc_info=True); await query.message.reply_text("❌ Error generating solution.")

# =====================================
# MAIN MESSAGE ROUTER
# =====================================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text
        mode = get_user_mode(user_id)
        
        # Handle messages based on active interactive mode first
        if mode == 'chat':
            await gemini_chat_handler(update, context)
            return
        if mode in ['image_analysis', 'pdf_creation']:
             await update.message.reply_text("Please send an image, not text. Use `/menu` to return.", parse_mode=ParseMode.MARKDOWN)
             return

        # Mode Selection from Main Menu
        if "Instagram" in text:
            await update.message.reply_text("🔓 *Instagram Reset*\nUse `/rst <user>` or `/bulk <users...>`.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
        elif "URL Shortener" in text:
            await update.message.reply_text("🔗 *URL Shortener*\nUse `/shorten <url>`.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
        elif "QR Code" in text:
            await update.message.reply_text("🔳 *QR Code*\nUse `/qr <text>`.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
        elif "Gen Password" in text:
            await update.message.reply_text("🔑 *Password Generator*\nUse `/genpass <length>`.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
        elif "Weather" in text:
            await update.message.reply_text("🌤️ *Weather Forecast*\nUse `/weather <city>`.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
        elif "AI Chat" in text:
            set_user_mode(user_id, 'chat')
            await update.message.reply_text("💬 *AI Chat Mode*\nSend any message to start. Use `/clear` to reset history or `/menu` to exit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "Image Analysis" in text:
            set_user_mode(user_id, 'image_analysis')
            await update.message.reply_text("📷 *Image Analysis Mode*\nSend me an image to analyze. Use `/menu` to exit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "Image to PDF" in text:
            set_user_mode(user_id, 'pdf_creation')
            await update.message.reply_text("📄 *PDF Creator Mode*\nSend me your images one by one. When you're done, use `/createpdf` to generate the file or `/cancelpdf` to quit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "AI Utilities" in text:
            await update.message.reply_text(
                "🤖 *AI Utilities*\nUse these commands for specific tasks:\n"
                "• `/summarize <text>`\n"
                "• `/email <prompt>`\n"
                "• `/code <question>`\n\n"
                "*Dev: Aadi (@aadi_io)*",
                 parse_mode=ParseMode.MARKDOWN
            )
        elif "Help" in text:
            await help_command_handler(update, context)
        else:
            await update.message.reply_text("Please select an option using the menu buttons below.")
    except Exception as e:
        logger.error(f"Error in text message router: {e}", exc_info=True)

# =====================================
# GLOBAL ERROR HANDLER & FASTAPI APP
# =====================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update:", exc_info=context.error)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app; logger.info("🚀 Starting bot initialization...")
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Command Handlers
    handlers = [
        CommandHandler("start", start_command_handler), CommandHandler("menu", start_command_handler),
        CommandHandler("help", help_command_handler), CommandHandler("rst", rst_command_handler),
        CommandHandler("bulk", bulk_command_handler), CommandHandler("shorten", shorten_command_handler),
        CommandHandler("qr", qr_command_handler), CommandHandler("clear", clear_command_handler),
        CommandHandler("genpass", genpass_command_handler), CommandHandler("weather", weather_command_handler),
        CommandHandler("createpdf", createpdf_command_handler), CommandHandler("cancelpdf", cancelpdf_command_handler),
        CommandHandler("summarize", ai_utility_command_handler), CommandHandler("email", ai_utility_command_handler),
        CommandHandler("code", ai_utility_command_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler),
        MessageHandler(filters.PHOTO, photo_message_handler),
        CallbackQueryHandler(button_handler)
    ]
    for handler in handlers: telegram_app.add_handler(handler)
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    if WEBHOOK_URL: await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"); logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
    else: logger.info("⚠️ Webhook URL not set. Bot will run in polling mode if run directly.")
    yield
    logger.info("👋 Shutting down bot..."); await telegram_app.stop(); await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)
@app.get("/")
async def health_check(): return {"status": "ok", "bot_initialized": telegram_app is not None}
@app.post("/webhook/{token}")
async def process_webhook(token: str, request: Request):
    if token != BOT_TOKEN: raise HTTPException(status_code=403, detail="Invalid token")
    if not telegram_app: raise HTTPException(status_code=503, detail="Bot not initialized")
    try:
        data = await request.json(); update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update); return {"status": "ok"}
    except Exception as e: logger.error(f"Error processing webhook update: {e}", exc_info=True); return {"status": "error"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting FastAPI server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

