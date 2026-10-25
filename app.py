import os
import json
import re
import urllib.request
import urllib.parse
import uuid
import sqlite3
import threading
import time
import requests
from flask import Flask, request, render_template_string, abort, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# ========== إعدادات قاعدة البيانات ==========
DB_FILE = "bans.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS banned_ips (ip TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()
init_db()

def is_ip_banned(ip):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM banned_ips WHERE ip=?", (ip,))
    result = c.fetchone()
    conn.close()
    return result is not None

def ban_ip(ip):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO banned_ips (ip) VALUES (?)", (ip,))
        conn.commit()
    except: pass
    conn.close()

# ========== الحماية ==========
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")
active_bots = {} # لتخزين البوتات النشطة: {token: {'name': name, 'ai_type': ai_type, 'chat_id': chat_id}}

def is_vpn_or_proxy(ip):
    if ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10."):
        return False
    try:
        req = urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=proxy,hosting", timeout=3)
        data = json.loads(req.read().decode())
        return data.get("proxy", False) or data.get("hosting", False)
    except: return False

# ========== دالة الذكاء الاصطناعي ==========
def get_ai_response(ai_type, user_message):
    # هنا تقوم بوضع مفاتيح API الخاصة بك
    if ai_type == "Gemini":
        # مثال باستخدام Gemini API (يحتاج مفتاح API)
        # api_key = "YOUR_GEMINI_API_KEY"
        return f"[Gemini AI]: مرحباً! لقد تلقيت رسالتك: {user_message}. (هذا رد تجريبي، يرجى إضافة مفتاح API)."
    elif ai_type == "ChatGPT":
        # مثال باستخدام OpenAI API
        # api_key = "YOUR_OPENAI_API_KEY"
        return f"[ChatGPT AI]: مرحباً! لقد تلقيت رسالتك: {user_message}. (هذا رد تجريبي، يرجى إضافة مفتاح API)."
    else:
        return "عذراً، لم يتم التعرف على نوع الذكاء الاصطناعي."

# ========== محرك البوت (Polling) ==========
def bot_polling_thread(token, bot_name, ai_type, chat_id=None):
    print(f"[*] Starting Bot: {bot_name} ({ai_type}) | Private: {chat_id is not None}")
    last_update_id = 0
    
    # إذا كان البوت خاصاً، نرسل رسالة تأكيد للمالك
    if chat_id:
        confirm_url = f"https://api.telegram.org/bot{token}/sendMessage"
        msg = f"✅ تم تفعيل البوت الخاص بك ({bot_name}) بنجاح!\nنوع الذكاء الاصطناعي: {ai_type}\nسيتم الرد عليك هنا."
        try:
            requests.post(confirm_url, data={"chat_id": chat_id, "text": msg}, timeout=5)
        except: pass

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=30"
            response = requests.get(url, timeout=35)
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    last_update_id = update["update_id"]
                    
                    if "message" in update and "text" in update["message"]:
                        msg_chat_id = update["message"]["chat"]["id"]
                        user_text = update["message"]["text"]
                        
                        # إذا كان البوت خاصاً، يرد فقط على المالك
                        if chat_id and str(msg_chat_id) != str(chat_id):
                            continue 
                            
                        # الحصول على رد الذكاء الاصطناعي
                        ai_reply = get_ai_response(ai_type, user_text)
                        
                        # إرسال الرد
                        send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                        requests.post(send_url, data={"chat_id": msg_chat_id, "text": ai_reply}, timeout=10)
        except Exception as e:
            time.sleep(5)

# ========== قوالب HTML ==========
BASE_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Bot AI</title>
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #cbd5e1; --accent: #38bdf8; --border: #334155; }
        * { box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { margin: 0; background: var(--bg); color: white; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 40px 20px; }
        .container { width: 100%; max-width: 600px; }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: var(--accent); margin-bottom: 5px; }
        .card { background: var(--card); padding: 30px; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        label { display: block; margin-bottom: 8px; color: var(--text); font-size: 14px; }
        input, select { width: 100%; padding: 12px; background: var(--bg); border: 1px solid var(--border); color: white; border-radius: 8px; margin-bottom: 15px; font-size: 15px; }
        input:focus, select:focus { outline: none; border-color: var(--accent); }
        button { width: 100%; padding: 14px; background: var(--accent); color: var(--bg); font-weight: bold; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; transition: 0.3s; }
        button:hover { opacity: 0.9; }
        .info-box { background: rgba(56, 189, 248, 0.1); border-right: 4px solid var(--accent); padding: 15px; border-radius: 6px; font-size: 13px; color: #bae6fd; margin-bottom: 20px; line-height: 1.6; }
        .info-box a { color: white; font-weight: bold; text-decoration: underline; }
        .success { color: #10b981; text-align: center; font-weight: bold; margin-top: 15px; }
        .error { color: #ef4444; text-align: center; font-weight: bold; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Token Bot AI</h1>
            <p>اربط بوتك بالذكاء الاصطناعي في ثوانٍ</p>
        </div>

        {% if message %}
            <div class="card">
                <div class="{{ 'success' if success else 'error' }}">{{ message }}</div>
                <br><a href="/"><button>العودة</button></a>
            </div>
        {% else %}
            <div class="card">
                <form method="POST" action="/create">
                    <label>توكن البوت (Bot Token):</label>
                    <input type="text" name="token" placeholder="123456:ABC-DEF..." required>
                    
                    <label>اسم البوت (إذا تركته فارغاً، سيسمي نفسه):</label>
                    <input type="text" name="bot_name" placeholder="مثال: مساعدي الذكي">
                    
                    <label>اختر الذكاء الاصطناعي:</label>
                    <select name="ai_type">
                        <option value="Gemini">Google Gemini</option>
                        <option value="ChatGPT">OpenAI ChatGPT</option>
                    </select>

                    <label>نوع البوت:</label>
                    <select name="bot_type" id="bot_type" onchange="toggleChatId()">
                        <option value="public">عام (Public) - يرد على الجميع</option>
                        <option value="private">خاص (Private) - يرد عليك فقط</option>
                    </select>

                    <div id="chat_id_div" style="display: none;">
                        <label>معرف المحادثة (Chat ID):</label>
                        <input type="text" name="chat_id" placeholder="123456789">
                    </div>

                    <button type="submit">تشغيل البوت</button>
                </form>
            </div>
            
            <div class="info-box">
                <strong>💡 ملاحظة هامة للبوت الخاص:</strong><br>
                للحصول على رقم <strong>Chat ID</strong> الخاص بك، يرجى التوجه إلى بوت 
                <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a> 
                في تيليجرام، والضغط على Start. سيعطيك البوت رقمك مباشرة. ضع الرقم في الحقل المخصص لكي يكون البوت خاصاً بك وحدك.
            </div>
        {% endif %}
    </div>
    <script>
        function toggleChatId() {
            var type = document.getElementById('bot_type').value;
            document.getElementById('chat_id_div').style.display = (type === 'private') ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""

# ========== المسارات ==========
@app.before_request
def check_ban_and_vpn():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    if is_ip_banned(ip):
        abort(403, description="Your IP has been permanently banned.")
    if is_vpn_or_proxy(ip):
        ban_ip(ip)
        abort(403, description="VPN/Proxy usage detected. Your IP has been permanently banned.")

@app.route('/')
@limiter.limit("20 per minute")
def index():
    return render_template_string(BASE_HTML)

@app.route('/create', methods=['POST'])
@limiter.limit("5 per minute")
def create_bot():
    token = request.form.get('token', '').strip()
    bot_name = request.form.get('bot_name', '').strip()
    ai_type = request.form.get('ai_type', 'Gemini')
    bot_type = request.form.get('bot_type', 'public')
    chat_id = request.form.get('chat_id', '').strip()

    # التحقق من صحة التوكن
    if not re.match(r"^[0-9]+:[a-zA-Z0-9_-]+$", token):
        return render_template_string(BASE_HTML, message="صيغة التوكن غير صحيحة.", success=False)

    # التحقق من أن البوت غير مشغل مسبقاً
    if token in active_bots:
        return render_template_string(BASE_HTML, message="هذا البوت قيد التشغيل بالفعل!", success=False)

    if bot_type == 'private':
        if not chat_id or not re.match(r"^-?[0-9]+$", chat_id):
            return render_template_string(BASE_HTML, message="يجب إدخال Chat ID صحيح للبوت الخاص.", success=False)
    else:
        chat_id = None

    # جلب اسم البوت من تيليجرام إذا لم يتم إدخاله
    if not bot_name:
        try:
            res = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            data = res.json()
            if data.get("ok"):
                bot_name = data["result"]["first_name"]
            else:
                return render_template_string(BASE_HTML, message="التوكن غير صالح أو البوت غير موجود.", success=False)
        except:
            return render_template_string(BASE_HTML, message="فشل الاتصال بتيليجرام للتحقق من البوت.", success=False)

    # تشغيل البوت في الخلفية
    active_bots[token] = {'name': bot_name, 'ai_type': ai_type, 'chat_id': chat_id}
    threading.Thread(target=bot_polling_thread, args=(token, bot_name, ai_type, chat_id), daemon=True).start()

    type_str = "خاص (Private)" if bot_type == 'private' else "عام (Public)"
    msg = f"تم تشغيل البوت '{bot_name}' بنجاح!\nالنوع: {type_str}\nالذكاء الاصطناعي: {ai_type}."
    
    return render_template_string(BASE_HTML, message=msg, success=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)