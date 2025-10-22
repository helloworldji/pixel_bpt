import os
from time import time
from flask import Flask, request
import telebot

BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
URL = os.getenv('RENDER_EXTERNAL_URL', '')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False)
app = Flask(__name__)

r = 0
c = {}
t0 = time()

@bot.message_handler(commands=['start'])
def s(m):
    bot.reply_to(m, "👋 <b>Reset Bot</b>\n\n<code>/rst @user</code>\n<code>/ping</code>\n\n⚡ Fast")

@bot.message_handler(commands=['help'])
def h(m):
    bot.reply_to(m, "<code>/rst @username</code>")

@bot.message_handler(commands=['stat'])
def st(m):
    if m.from_user.id not in ADMIN: return
    u = int(time()-t0)
    bot.reply_to(m, f"Resets: {r}\nUptime: {u//3600}h {(u%3600)//60}m")

@bot.message_handler(commands=['rst'])
def rst(m):
    global r
    uid = m.from_user.id
    now = time()
    if uid in c and now-c[uid]<0.2: return
    c[uid] = now
    p = m.text.split()
    if len(p)<2 or p[1][0]!='@':
        bot.reply_to(m, "Use: /rst @user")
        return
    if m.chat.type in ("group","supergroup","channel"):
        bot.reply_to(m, f"✅ {p[1]}\n🔄 <a href='tg://user?id={uid}'>{m.from_user.first_name}</a>")
    else:
        bot.reply_to(m, f"✅ {p[1]}")
    r+=1

@bot.message_handler(commands=['ping'])
def ping(m):
    t=time()
    s=bot.reply_to(m,"🏓")
    bot.edit_message_text(f"🏓 {int((time()-t)*1000)}ms",s.chat.id,s.message_id)

@app.route('/')
def i(): return "OK"

@app.route('/webhook', methods=['POST'])
def w():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return ''

if __name__=='__main__':
    bot.remove_webhook()
    bot.set_webhook(f"{URL}/webhook", drop_pending_updates=True)
    app.run('0.0.0.0', PORT, threaded=True, debug=False)
