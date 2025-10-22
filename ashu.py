import os
from time import time
from flask import Flask, request
import telebot

BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
URL = os.getenv('RENDER_EXTERNAL_URL', '')

# Fast bot initialization with connection pooling
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False, num_threads=1)
app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

r = 0
t0 = time()

@bot.message_handler(commands=['start'])
def s(m):
    bot.send_message(m.chat.id, "👋 <b>Reset Bot</b>\n\n/rst @user\n/ping\n\n⚡ Fast", reply_to_message_id=m.message_id)

@bot.message_handler(commands=['help'])
def h(m):
    bot.send_message(m.chat.id, "/rst @username", reply_to_message_id=m.message_id)

@bot.message_handler(commands=['stat'])
def st(m):
    if m.from_user.id not in ADMIN: return
    u = int(time()-t0)
    bot.send_message(m.chat.id, f"Resets: {r}\nUptime: {u//3600}h {(u%3600)//60}m", reply_to_message_id=m.message_id)

@bot.message_handler(commands=['rst'])
def rst(m):
    global r
    uid = m.from_user.id
    p = m.text.split()
    if len(p)<2 or p[1][0]!='@':
        bot.send_message(m.chat.id, "Use: /rst @user", reply_to_message_id=m.message_id)
        return
    if m.chat.type in ("group","supergroup","channel"):
        bot.send_message(m.chat.id, f"✅ {p[1]}\n🔄 <a href='tg://user?id={uid}'>{m.from_user.first_name}</a>", reply_to_message_id=m.message_id)
    else:
        bot.send_message(m.chat.id, f"✅ {p[1]}", reply_to_message_id=m.message_id)
    r+=1

@bot.message_handler(commands=['ping'])
def ping(m):
    t=time()
    bot.send_message(m.chat.id, f"🏓 {int((time()-t)*1000)}ms", reply_to_message_id=m.message_id)

@app.route('/')
def i(): 
    return "OK"

@app.route('/webhook', methods=['POST'])
def w():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return ''

if __name__=='__main__':
    bot.remove_webhook()
    bot.set_webhook(f"{URL}/webhook", drop_pending_updates=True)
    
    # Use waitress production server - MUCH FASTER than Flask dev server
    from waitress import serve
    print("🚀 Bot running - Production mode")
    serve(app, host='0.0.0.0', port=PORT, threads=8, channel_timeout=120, connection_limit=1000)
