import logging, asyncio, json, re, io
import google.generativeai as genai
import PIL.Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Fayllaringizdan importlar
from database import init_db, ensure_user, save_signal, update_signal_result, get_ai_knowledge, get_global_stats, get_user_stats
from signal_engine import get_candles, get_all_prices, analyze_with_ai, scan_all_pairs, WATCH_PAIRS

# ─── API KALITLAR ─────────────────────────────────────────
TELEGRAM_TOKEN = "8776282635:AAExON8KZhR8w_ZfZthurcLb7LB2AsMuk9A"
GEMINI_API_KEY = "AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE"

# ──────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-1.5-flash")
user_cfg = {}

def cfg(uid):
    if uid not in user_cfg:
        user_cfg[uid] = {"notif": False, "interval": 60, "timeframe": "H1", "job": None, "last_sid": None}
    return user_cfg[uid]

def main_kb():
    return ReplyKeyboardMarkup([
        ["📸 Manual Tahlil", "🤖 Auto Skan"],
        ["📜 Pine Script", "🧠 AI Bilimi"],
        ["📊 Statistika", "🔔 Bildirishnoma"],
        ["💱 Narxlar", "ℹ️ Yordam"],
    ], resize_keyboard=True)

def notif_kb(is_on, tf, interval):
    lbl = "✅ Yoqiq" if is_on else "❌ O'chiq"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔔 Holat: {lbl}", callback_data="notif_toggle")],
        [InlineKeyboardButton("M15", callback_data="tf_M15"), InlineKeyboardButton("H1", callback_data="tf_H1"),
         InlineKeyboardButton("H4", callback_data="tf_H4"), InlineKeyboardButton("D1", callback_data="tf_D")],
        [InlineKeyboardButton("⏰ 15 daq", callback_data="iv_15"), InlineKeyboardButton("⏰ 30 daq", callback_data="iv_30"),
         InlineKeyboardButton("⏰ 1 soat", callback_data="iv_60"), InlineKeyboardButton("⏰ 4 soat", callback_data="iv_240")],
        [InlineKeyboardButton("💾 Saqlash va Yoqish", callback_data="notif_save")],
    ])

def result_kb(sid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ WIN", callback_data=f"r_WIN_{sid}"), InlineKeyboardButton("❌ LOSS", callback_data=f"r_LOSS_{sid}")],
        [InlineKeyboardButton("⏭ O'tkazish", callback_data=f"r_SKIP_{sid}")],
    ])

def pairs_kb():
    buttons, row = [], []
    for pair in WATCH_PAIRS:
        row.append(InlineKeyboardButton(pair, callback_data=f"scan_{pair}"))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔍 Hammasi", callback_data="scan_ALL")])
    return InlineKeyboardMarkup(buttons)

def fmt(d, sid):
    sig = d.get("signal", "WAIT")
    sl, bg = ("🟢 BUY  🚀", "📗") if sig == "BUY" else (("🔴 SELL 📉", "📕") if sig == "SELL" else ("🟡 WAIT ⏳", "📒"))
    conf = d.get("confidence", 50)
    bar = "🟩" * (conf // 20) + "⬜" * (5 - conf // 20)
    return (f"{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n      🤖 *FOREX AI SIGNAL*\n{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n\n"
            f"💱 *{d.get('pair', '?')}* ⏰ `{d.get('timeframe', '?')}`\n"
            f"🌊 `{d.get('trend', '?')}`  🕯 `{d.get('pattern', '?')}`\n"
            f"🏗 *{d.get('market_structure', '?')}* 🕐 `{d.get('session', '?')}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n📡 *SIGNAL: {sl}*\n💪 {bar} `{conf}%`\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *KIRISH:*\n   🎯 Entry: `{d.get('entry', '?')}`\n\n"
            f"🛡 *RISK:*\n   🛑 SL: `{d.get('stop_loss', '?')}` ← `{d.get('sl_pips', '?')} pips`\n"
            f"   *{d.get('sl_reason', '')}*\n\n"
            f"🏆 *MAQSADLAR:*\n"
            f"   ✅ TP1: `{d.get('tp1', '?')}` ← `{d.get('tp1_pips', '?')} pips`\n"
            f"   ✅✅ TP2: `{d.get('tp2', '?')}` ← `{d.get('tp2_pips', '?')} pips`\n"
            f"   ✅✅✅ TP3: `{d.get('tp3', '?')}` ← `{d.get('tp3_pips', '?')} pips`\n"
            f"   *{d.get('tp_reason', '')}*\n   ⚖️ `{d.get('risk_reward', '?')}`\n\n"
            f"📊 *{d.get('indicators_summary', '')}*\n💡 *{d.get('reasoning', '')}*\n"
            f"⚠️ *{d.get('risk_warning', '')}*\n\n🔢 `#{sid}`\n━━━━━━━━━━━━━━━━━━━━\n_⚠️ Savdo o'z xavf-xataringiz bilan_")

def save_sig(uid, d, source):
    return save_signal(uid, d.get("pair", "?"), d.get("timeframe", "?"),
                       d.get("signal", "WAIT"), d.get("pattern", "Unknown"),
                       str(d.get("entry", "?")), str(d.get("stop_loss", "?")),
                       str(d.get("tp1", "?")), str(d.get("tp2", "?")), str(d.get("tp3", "?")),
                       str(d.get("sl_pips", "?")), str(d.get("tp1_pips", "?")),
                       str(d.get("tp2_pips", "?")), str(d.get("tp3", "?")),
                       str(d.get("risk_reward", "?")), d.get("confidence", 50),
                       d.get("market_structure", ""), d.get("indicators_summary", ""), source)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; name = update.effective_user.first_name; ensure_user(uid)
    frames = ["🌑", "🌒", "🌓", "🌔", "🌕 Tayyor!"]
    m = await update.message.reply_text("🌑")
    for f in frames: 
        await asyncio.sleep(0.2)
        await m.edit_text(f)
    await m.delete()
    await update.message.reply_text(
        f"🤖 *Assalomu alaykum, {name}!*\n\n"
        "```\n╔══════════════════════════════╗\n║  🧠 FOREX AI BOT v3.0       ║\n║  Twelve Data + Gemini AI    ║\n╚══════════════════════════════╝\n```\n"
        "🚀 *Imkoniyatlar:*\n┣ 🤖 Twelve Data → real signal\n┣ 📸 Chart rasm → manual tahlil\n"
        "┣ 🎯 Entry · SL · TP1/2/3\n┣ 🧠 Har signaldan o'rganadi\n┣ 📜 Pine Script\n┗ 🔔 Bildirishnoma\n\n👇 Tugmani bosing!",
        parse_mode="Markdown", reply_markup=main_kb())

async def auto_scan_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; tf = cfg(uid).get("timeframe", "H1")
    await update.message.reply_text(f"🤖 *Auto Skan*\nTimeframe: `{tf}`\nQaysi juftlik?",
                                     parse_mode="Markdown", reply_markup=pairs_kb())

async def do_scan(update, ctx, pair, timeframe, uid):
    tf_map = {"M15": "15min", "H1": "1h", "H4": "4h", "D": "1day"}
    td_tf = tf_map.get(timeframe, "1h")
    steps = [f"📡 {pair} olinmoqda...", "📊 Shamlar...", "🧠 Gemini...", "🎯 Entry·SL·TP...", "✨ Tayyor!"]
    m = await update.effective_message.reply_text(steps[0])
    for s in steps[1:]: 
        await asyncio.sleep(0.4)
        await m.edit_text(s)
    try:
        candles = get_candles(pair, td_tf, 100)
        if not candles: 
            await m.edit_text(f"❌ {pair} topilmadi.")
            return
        d = analyze_with_ai(pair, timeframe, candles, get_ai_knowledge())
        if not d: 
            await m.edit_text("❌ AI tahlil qila olmadi.")
            return
        sid = save_sig(uid, d, "auto"); cfg(uid)["last_sid"] = sid
        await m.delete()
        await update.effective_message.reply_text(fmt(d, sid), parse_mode="Markdown", reply_markup=result_kb(sid))
    except Exception as e: 
        await m.edit_text(f"❌ Xato: {str(e)[:150]}")

async def analyze_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; ensure_user(uid)
    m = await update.message.reply_text("🔍 Rasm tahlil qilinmoqda...")
    try:
        if update.message.photo: 
            file = await ctx.bot.get_file(update.message.photo[-1].file_id)
        elif update.message.document and "image" in (update.message.document.mime_type or ""):
            file = await ctx.bot.get_file(update.message.document.file_id)
        else: 
            await m.edit_text("❌ Faqat rasm yuboring!"); return
            
        raw_bytes = await file.download_as_bytearray()
        pil_img = PIL.Image.open(io.BytesIO(raw_bytes))
        knowledge = get_ai_knowledge()
        know_block = "\n🧠 O'RGANILGAN:\n" + "".join(f"  • {k['pattern']}: {k['win_rate']}%\n" for k in knowledge[:5]) if knowledge else ""
        
        prompt = f"""Sen Forex AI tahlilchisisisan.{know_block}
        FAQAT JSON javob ber:
        {{"pair":"?","timeframe":"?","trend":"?","pattern":"?","signal":"BUY/SELL/WAIT","confidence":80,
        "entry":"?","stop_loss":"?","tp1":"?","tp2":"?","tp3":"?",
        "sl_pips":"?","tp1_pips":"?","tp2_pips":"?","tp3_pips":"?","risk_reward":"1:3",
        "sl_reason":"?","tp_reason":"?","market_structure":"?","session":"?",
        "indicators_summary":"?","reasoning":"?","risk_warning":"?"}}"""
        
        resp = gemini.generate_content([prompt, pil_img])
        raw = resp.text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match: raise ValueError("JSON topilmadi")
        d = json.loads(match.group())
        sid = save_sig(uid, d, "manual"); cfg(uid)["last_sid"] = sid
        await m.delete()
        await update.message.reply_text(fmt(d, sid), parse_mode="Markdown", reply_markup=result_kb(sid))
    except Exception as e: 
        await m.edit_text(f"❌ Xato: {str(e)[:150]}")

async def show_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("📡 Narxlar olinmoqda...")
    prices = get_all_prices()
    if not prices: 
        await m.edit_text("❌ Narxlar topilmadi.")
        return
    lines = ["💱 *Joriy Forex Narxlar*\n"]
    for p in prices: 
        lines.append(f"`{p['pair']:<10}` → `{p['price']:.5f}`")
    await m.edit_text("\n".join(lines), parse_mode="Markdown")

async def generate_pine(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("⚙️ Strategiya tayyorlanmoqda...")
    knowledge = get_ai_knowledge()
    know_txt = f"\nEng yaxshi: {knowledge[0]['pattern']} ({knowledge[0]['win_rate']}%)" if knowledge else ""
    prompt = f"TradingView Pine Script v5.{know_txt} EMA 20/50/200, RSI, MACD, Bollinger, Support/Resistance, BUY/SELL signallari, SL/TP1/TP2/TP3. FAQAT kodni o'zini ber."
    try:
        resp = gemini.generate_content(prompt); code = resp.text.strip()
        code = re.sub(r'
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1

### Nimalar o'zgartirildi:
1. **Sintaksis:** Barcha `“ ”` qo'shtirnoqlar `"` ga almashtirildi. 
2. **Asinxronlik:** `on_text` ichidagi funksiyalar `await` bilan chaqirildi, aks holda bot buyruqlarga javob bermasdi.
3. **Callback Mantiqi:** `r_WIN_123` kabi ma'lumotlarni ajratishda kodingizdagi `*` o'rniga `_` ishlatildi (chunki tugmada tagchiziq yozilgan).
4. **Pine Script:** Gemini qaytargan koddan Markdown belgilarini (` ``` `) olib tashlash uchun `re.sub` qo'shildi, aks holda kod o'qishga noqulay bo'ladi.
5. **Start Animatsiyasi:** Kutish vaqti biroz qisqartirildi (foydalanuvchi zerikmasligi uchun).
