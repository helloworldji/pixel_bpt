import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration - ONLY BOT TOKEN NEEDED!
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"

# Admin IDs
ADMIN_IDS = [8275649347, 8175884349]

# Force subscribe channel
FORCE_SUB_CHANNEL = "@thebosssquad"

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# In-memory cache for better performance
class BotCache:
    def __init__(self):
        self.user_cache: Dict[int, datetime] = {}
        self.stats = {"total_resets": 0, "start_time": datetime.now()}
        asyncio.create_task(self.load_stats())
    
    async def load_stats(self):
        """Load stats from file"""
        try:
            if os.path.exists("bot_stats.json"):
                async with aiofiles.open("bot_stats.json", "r") as f:
                    data = json.loads(await f.read())
                    self.stats["total_resets"] = data.get("total_resets", 0)
        except Exception as e:
            logger.error(f"Error loading stats: {e}")
    
    async def save_stats(self):
        """Save stats to file"""
        try:
            async with aiofiles.open("bot_stats.json", "w") as f:
                await f.write(json.dumps({"total_resets": self.stats["total_resets"]}))
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def can_use_command(self, user_id: int, cooldown_seconds: int = 1) -> bool:
        """Check if user can use command (cooldown)"""
        now = datetime.now()
        if user_id in self.user_cache:
            if (now - self.user_cache[user_id]).total_seconds() < cooldown_seconds:
                return False
        self.user_cache[user_id] = now
        return True
    
    async def increment_reset_count(self):
        """Increment reset counter"""
        self.stats["total_resets"] += 1
        if self.stats["total_resets"] % 10 == 0:  # Save every 10 resets
            await self.save_stats()

# Initialize cache
cache = BotCache()

async def check_force_sub(user_id: int) -> bool:
    """Check if user is subscribed to force sub channel"""
    try:
        member = await bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return True  # Allow if error occurs

def create_force_sub_keyboard():
    """Create force subscribe keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")],
        [InlineKeyboardButton(text="✅ I've Joined", callback_data="check_joined")]
    ])
    return keyboard

@dp.message(CommandStart())
async def start_command(message: types.Message):
    """Handle /start command"""
    try:
        # Check force subscription
        if not await check_force_sub(message.from_user.id):
            await message.reply(
                "❌ <b>Please join our channel first!</b>\n\n"
                "Join the channel below and click 'I've Joined' to continue.",
                reply_markup=create_force_sub_keyboard()
            )
            return
        
        welcome_text = (
            "👋 <b>Welcome to Fast Reset Bot!</b>\n\n"
            "🚀 <b>Commands:</b>\n"
            "• <code>/rst @username</code> - Reset a user\n"
            "• <code>/help</code> - Show help message\n"
            "• <code>/start</code> - Start the bot\n\n"
            "⚡ <b>Features:</b>\n"
            "• Ultra-fast response (<0.3s)\n"
            "• Works in groups and channels\n"
            "• Simple and efficient\n\n"
            "Made with ❤️ for speed!"
        )
        
        await message.reply(welcome_text)
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Handle /help command"""
    try:
        # Check force subscription in private
        if message.chat.type == "private":
            if not await check_force_sub(message.from_user.id):
                await message.reply(
                    "❌ Please join our channel first!",
                    reply_markup=create_force_sub_keyboard()
                )
                return
        
        help_text = (
            "📚 <b>Bot Help</b>\n\n"
            "<b>How to use:</b>\n"
            "Simply send <code>/rst @username</code> to reset someone\n\n"
            "<b>Where it works:</b>\n"
            "• Private chat with bot\n"
            "• Groups (bot must be admin)\n"
            "• Channels (bot must be admin)\n\n"
            "<b>Note:</b> One reset at a time for best performance!"
        )
        
        await message.reply(help_text)
        
    except Exception as e:
        logger.error(f"Error in help command: {e}")

@dp.message(Command("stat"))
async def stats_command(message: types.Message):
    """Handle /stat command (owner only)"""
    try:
        # Check if user is owner
        if message.from_user.id not in ADMIN_IDS:
            await message.reply("❌ This command is not available!")
            return
        
        uptime = datetime.now() - cache.stats["start_time"]
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        stats_text = (
            "📊 <b>Bot Statistics</b>\n\n"
            f"🎯 <b>Total Resets Sent:</b> <code>{cache.stats['total_resets']}</code>\n"
            f"⏱ <b>Uptime:</b> <code>{uptime.days}d {hours}h {minutes}m {seconds}s</code>\n"
            f"🚀 <b>Status:</b> <code>Online</code>\n"
            f"⚡ <b>Performance:</b> <code>Optimized</code>"
        )
        
        await message.reply(stats_text)
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")

@dp.message(Command("rst"))
async def reset_command(message: types.Message):
    """Handle /rst command with optimized performance"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Check cooldown
        if not cache.can_use_command(message.from_user.id, cooldown_seconds=1):
            return  # Silently ignore if cooldown active
        
        # Check force subscription in private
        if message.chat.type == "private":
            if not await check_force_sub(message.from_user.id):
                await message.reply(
                    "❌ Please join our channel first!",
                    reply_markup=create_force_sub_keyboard()
                )
                return
        
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply("❌ <b>Usage:</b> <code>/rst @username</code>")
            return
        
        target_username = command_parts[1]
        
        # Validate username format
        if not target_username.startswith("@"):
            await message.reply("❌ <b>Please provide a valid username starting with @</b>")
            return
        
        # Clean username
        target_username = target_username.strip()
        
        # Prepare reset message with proper mention
        if message.chat.type in ["group", "supergroup", "channel"]:
            # In groups/channels, tag the user who sent command
            sender_mention = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>"
            reset_text = f"✅ <b>Reset successful!</b>\n\n👤 <b>Target:</b> {target_username}\n🔄 <b>Reset by:</b> {sender_mention}"
        else:
            # In private chat
            reset_text = f"✅ <b>Reset successful!</b>\n\n👤 <b>Target:</b> {target_username}"
        
        # Send reset message
        await message.reply(reset_text)
        
        # Increment stats
        await cache.increment_reset_count()
        
        # Log response time
        response_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"Reset command processed in {response_time:.3f} seconds")
        
    except Exception as e:
        logger.error(f"Error in reset command: {e}")
        await message.reply("❌ An error occurred. Please try again.")

@dp.message(Command("ping"))
async def ping_command(message: types.Message):
    """Ping command to test bot response time"""
    start = asyncio.get_event_loop().time()
    sent_message = await message.reply("🏓 Pong!")
    end = asyncio.get_event_loop().time()
    await sent_message.edit_text(f"🏓 Pong! <code>{(end-start)*1000:.1f}ms</code>")

@dp.callback_query(F.data == "check_joined")
async def check_joined_callback(callback: CallbackQuery):
    """Handle force subscribe check callback"""
    try:
        if await check_force_sub(callback.from_user.id):
            await callback.message.edit_text(
                "✅ <b>Thank you for joining!</b>\n\n"
                "You can now use all bot features.\n"
                "Send <code>/help</code> to see available commands."
            )
        else:
            await callback.answer(
                "❌ You haven't joined the channel yet! Please join first.",
                show_alert=True
            )
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        await callback.answer("An error occurred. Please try again.")

async def main():
    """Main function to run the bot"""
    logger.info("Starting Fast Reset Bot...")
    logger.info(f"Bot running with {len(ADMIN_IDS)} authorized users")
    
    # Start polling
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
