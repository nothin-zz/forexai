“””
bot.py — Forex AI Self-Learning Telegram Bot
OANDA API + Google Gemini (BEPUL) + Self-Learning
“””

import logging
import asyncio
import base64
import json
import re
import io
import PIL.Image
import google.generativeai as genai

from telegram import (
Update, InlineKeyboardButton, InlineKeyboardMarkup,
ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
Application, CommandHandler, MessageHandler,
CallbackQueryHandler, filters, ContextTypes
)

from database import (
init_db, ensure_user, save_signal, update_signal_result,
get_ai_knowledge, get_global_stats, get_user_stats
)
from twelve_data_engine import (
get_candles, get_current_price, analyze_with_ai,
scan_all_pairs, WATCH_PAIRS
)

# ─────────────────────────────────────────

# SOZLAMALAR  ← O’ZGARTIRING!

# ─────────────────────────────────────────

TELEGRAM_TOKEN = “YOUR_TELEGRAM_BOT_TOKEN”   # @BotFather
GEMINI_API_KEY = “YOUR_GEMINI_API_KEY”       # aistudio.google.com — BEPUL!

# ─────────────────────────────────────────

logging.basicConfig(
format=”%(asctime)s | %(levelname)s | %(message)s”,
level=logging.INFO
)
logger = logging.getLogger(**name**)

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel(“gemini-1.5-flash”)

# Foydalanuvchi sozlamalari (xotirada)

user_cfg: dict[int, dict] = {}

def cfg(uid: int) -> dict:
if uid not in user_cfg:
user_cfg[uid] = {
“notif”: False,
“interval”: 60,
“timeframe”: “H1”,
“job”: None,
“last_sid”: None
}
return user_cfg[uid]

# ═══════════════════════════════════════════

# KLAVIATURALAR

# ═══════════════════════════════════════════

def main_kb():
return ReplyKeyboardMarkup([
[“📸 Manual Tahlil”,  “🤖 Auto Skan”],
[“📜 Pine Script”,    “🧠 AI Bilimi”],
[“📊 Statistika”,     “🔔 Bildirishnoma”],
[“💱 Narxlar”,        “ℹ️ Yordam”],
], resize_keyboard=True)

def notif_kb(is_on: bool, tf: str, interval: int):
lbl = “✅ Yoqiq” if is_on else “❌ O’chiq”
return InlineKeyboardMarkup([
[InlineKeyboardButton(f”🔔 {lbl}”, callback_data=“notif_toggle”)],
[
InlineKeyboardButton(“M15”, callback_data=“tf_M15”),
InlineKeyboardButton(“H1”,  callback_data=“tf_H1”),
InlineKeyboardButton(“H4”,  callback_data=“tf_H4”),
InlineKeyboardButton(“D1”,  callback_data=“tf_D”),
],
[
InlineKeyboardButton(“⏰ 15 daq”,  callback_data=“iv_15”),
InlineKeyboardButton(“⏰ 30 daq”,  callback_data=“iv_30”),
InlineKeyboardButton(“⏰ 1 soat”,  callback_data=“iv_60”),
InlineKeyboardButton(“⏰ 4 soat”,  callback_data=“iv_240”),
],
[InlineKeyboardButton(“💾 Saqlash”, callback_data=“notif_save”)],
])

def result_kb(sid: int):
return InlineKeyboardMarkup([
[
InlineKeyboardButton(“✅ WIN”, callback_data=f”r_WIN_{sid}”),
InlineKeyboardButton(“❌ LOSS”, callback_data=f”r_LOSS_{sid}”),
],
[InlineKeyboardButton(“⏭ O’tkazish”, callback_data=f”r_SKIP_{sid}”)],
])

def pairs_kb():
buttons = []
row = []
for i, pair in enumerate(WATCH_PAIRS):
row.append(InlineKeyboardButton(
pair.replace(”*”, “/”), callback_data=f”scan*{pair}”
))
if len(row) == 3:
buttons.append(row)
row = []
if row:
buttons.append(row)
buttons.append([InlineKeyboardButton(“🔍 Hammasi”, callback_data=“scan_ALL”)])
return InlineKeyboardMarkup(buttons)

# ═══════════════════════════════════════════

# SIGNAL FORMATLASH

# ═══════════════════════════════════════════

def format_signal(d: dict, sid: int) -> str:
sig = d.get(“signal”, “WAIT”)
if sig == “BUY”:
sig_line, bg = “🟢 BUY  🚀”, “📗”
elif sig == “SELL”:
sig_line, bg = “🔴 SELL 📉”, “📕”
else:
sig_line, bg = “🟡 WAIT ⏳”, “📒”

```
conf = d.get("confidence", 50)
bar  = "🟩" * (conf // 20) + "⬜" * (5 - conf // 20)

return (
    f"{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n"
    f"      🤖 *FOREX AI SIGNAL*\n"
    f"{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n\n"
    f"💱 *{d.get('pair','?')}*  ⏰ `{d.get('timeframe','?')}`\n"
    f"🌊 Trend: `{d.get('trend','?')}`\n"
    f"🕯 Pattern: `{d.get('pattern','?')}`\n"
    f"🏗 Struktura: _{d.get('market_structure','?')}_\n"
    f"🕐 Sessiya: `{d.get('session','?')}`\n\n"
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"📡 *SIGNAL: {sig_line}*\n"
    f"💪 Ishonch: {bar} `{conf}%`\n"
    f"━━━━━━━━━━━━━━━━━━━━\n\n"
    f"💰 *IDEAL KIRISH:*\n"
    f"   🎯 Entry:  `{d.get('entry','?')}`\n\n"
    f"🛡 *RISK BOSHQARUVI:*\n"
    f"   🛑 Stop Loss: `{d.get('stop_loss','?')}` ← `{d.get('sl_pips','?')} pips`\n"
    f"   _{d.get('sl_reason','')}_\n\n"
    f"🏆 *MAQSADLAR:*\n"
    f"   ✅ TP1: `{d.get('tp1','?')}` ← `{d.get('tp1_pips','?')} pips`\n"
    f"   ✅✅ TP2: `{d.get('tp2','?')}` ← `{d.get('tp2_pips','?')} pips`\n"
    f"   ✅✅✅ TP3: `{d.get('tp3','?')}` ← `{d.get('tp3_pips','?')} pips`\n"
    f"   _{d.get('tp_reason','')}_\n\n"
    f"   ⚖️ Risk/Reward: `{d.get('risk_reward','?')}`\n\n"
    f"📊 *Tahlil:*\n_{d.get('indicators_summary','')}_\n\n"
    f"💡 *Sabab:*\n_{d.get('reasoning','')}_\n\n"
    f"⚠️ _{d.get('risk_warning','')}_\n\n"
    f"🔢 Signal ID: `#{sid}`\n"
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"_⚠️ Savdo o'z xavf-xataringiz bilan_"
)
```

def save_and_get_sid(uid, d, source=“auto”):
return save_signal(
uid,
d.get(“pair”,”?”), d.get(“timeframe”,”?”),
d.get(“signal”,“WAIT”), d.get(“pattern”,“Unknown”),
str(d.get(“entry”,”?”)), str(d.get(“stop_loss”,”?”)),
str(d.get(“tp1”,”?”)), str(d.get(“tp2”,”?”)), str(d.get(“tp3”,”?”)),
str(d.get(“sl_pips”,”?”)), str(d.get(“tp1_pips”,”?”)),
str(d.get(“tp2_pips”,”?”)), str(d.get(“tp3_pips”,”?”)),
str(d.get(“risk_reward”,”?”)), d.get(“confidence”, 50),
d.get(“market_structure”,””), d.get(“indicators_summary”,””), source
)

# ═══════════════════════════════════════════

# /start

# ═══════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid  = update.effective_user.id
name = update.effective_user.first_name
ensure_user(uid)

```
frames = ["🌑","🌒","🌓","🌔","🌕 Tayyor!"]
m = await update.message.reply_text("🌑")
for f in frames:
    await asyncio.sleep(0.3)
    await m.edit_text(f)
await m.delete()

txt = (
    f"🤖 *Assalomu alaykum, {name}!*\n\n"
    "```\n"
    "╔══════════════════════════════╗\n"
    "║   🧠 FOREX AI BOT v3.0      ║\n"
    "║  OANDA + Gemini (BEPUL) AI  ║\n"
    "╚══════════════════════════════╝\n"
    "```\n"
    "🚀 *Imkoniyatlar:*\n"
    "┣ 🤖 OANDA → real narxlar → auto signal\n"
    "┣ 📸 Chart rasm → manual tahlil\n"
    "┣ 🎯 Entry · SL · TP1 · TP2 · TP3\n"
    "┣ 🧠 Har signaldan o'rganadi\n"
    "┣ 🌍 Global tajriba bazasi\n"
    "┣ 📜 Pine Script generatsiya\n"
    "┗ 🔔 Avtomatik bildirishnoma\n\n"
    "👇 Pastdagi tugmani bosing!"
)
await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb())
```

# ═══════════════════════════════════════════

# AUTO SKAN MENYU

# ═══════════════════════════════════════════

async def auto_scan_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“🤖 *Avtomatik Skan*\n\n”
“Qaysi juftlikni tahlil qilaylik?\n”
“*(OANDA real narxlari + Gemini AI)*”,
parse_mode=“Markdown”,
reply_markup=pairs_kb()
)

# ═══════════════════════════════════════════

# BITTA JUFTLIK SKAN

# ═══════════════════════════════════════════

async def do_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
pair: str, timeframe: str, uid: int):
m = await update.effective_message.reply_text(
f”⏳ {pair.replace(’_’,’/’)} tahlil qilinmoqda…”
)
steps = [
f”📡 OANDA dan {pair} narxi olinmoqda…”,
f”📊 {timeframe} candlelar yuklanmoqda…”,
“🧠 Gemini AI tahlil qilmoqda…”,
“🎯 Entry · SL · TP hisoblanmoqda…”,
“✨ Natija tayyorlanmoqda…”
]
for s in steps:
await asyncio.sleep(0.5)
await m.edit_text(s)

```
try:
    candles = get_candles(pair, timeframe, count=100)
    if not candles:
        await m.edit_text(f"❌ {pair} ma'lumoti topilmadi.")
        return

    knowledge = get_ai_knowledge()
    d = analyze_with_ai(pair, timeframe, candles, knowledge)

    if not d:
        await m.edit_text("❌ AI tahlil qila olmadi. Qayta urinib ko'ring.")
        return

    sid = save_and_get_sid(uid, d, "auto")
    cfg(uid)["last_sid"] = sid

    await m.delete()
    await update.effective_message.reply_text(
        format_signal(d, sid),
        parse_mode="Markdown",
        reply_markup=result_kb(sid)
    )
except Exception as e:
    logger.error(f"do_scan xato: {e}")
    await m.edit_text(f"❌ Xato: {str(e)[:150]}")
```

# ═══════════════════════════════════════════

# MANUAL CHART TAHLIL (rasm yuborilganda)

# ═══════════════════════════════════════════

async def analyze_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid = update.effective_user.id
ensure_user(uid)

```
steps = [
    "🔍 Rasm qabul qilindi...",
    "🧠 Gemini AI tahlil qilmoqda...",
    "📐 Support/Resistance aniqlanmoqda...",
    "🎯 Entry · SL · TP hisoblanmoqda...",
    "✨ Natija tayyorlanmoqda..."
]
m = await update.message.reply_text(steps[0])
for s in steps[1:]:
    await asyncio.sleep(0.55)
    await m.edit_text(s)

try:
    # Rasm olish
    if update.message.photo:
        file = await ctx.bot.get_file(update.message.photo[-1].file_id)
    elif (update.message.document
          and update.message.document.mime_type
          and "image" in update.message.document.mime_type):
        file = await ctx.bot.get_file(update.message.document.file_id)
    else:
        await m.edit_text("❌ Faqat rasm yuboring (JPG/PNG/WebP)")
        return

    raw_bytes = await file.download_as_bytearray()

    # AI bilimlarini olish
    knowledge = get_ai_knowledge()
    know_block = ""
    if knowledge:
        know_block = "\n🧠 O'RGANILGAN BILIMLAR (bularni hisobga ol):\n"
        for k in knowledge[:5]:
            know_block += f"  • {k['pattern']}: {k['win_rate']}% win-rate\n"

    prompt = f"""Sen dunyo darajasidagi Forex tahlilchisisisan.{know_block}
```

Ushbu Forex chart rasmini JUDA CHUQUR tahlil qil.
FAQAT quyidagi JSON formatida javob ber (boshqa hech narsa yozma):

{{
“pair”: “valyuta juftligi (masalan XAUUSD, EURUSD)”,
“timeframe”: “vaqt oralig’i (M15/H1/H4/D1)”,
“trend”: “UPTREND | DOWNTREND | SIDEWAYS”,
“pattern”: “eng kuchli candlestick/chart pattern”,
“signal”: “BUY | SELL | WAIT”,
“confidence”: 82,

“entry”: “aniq kirish narxi”,
“stop_loss”: “aniq SL narxi (swing high/low tashqarisida)”,
“tp1”: “TP1 narxi (1:1 RR)”,
“tp2”: “TP2 narxi (1:2 RR)”,
“tp3”: “TP3 narxi (1:3 RR)”,

“sl_pips”: “SL pipslarda soni”,
“tp1_pips”: “TP1 pipslarda”,
“tp2_pips”: “TP2 pipslarda”,
“tp3_pips”: “TP3 pipslarda”,
“risk_reward”: “masalan 1:3”,

“sl_reason”: “SL nima uchun shu joyda (support/resistance/swing)”,
“tp_reason”: “TP darajalari sababi (resistance/fibonacci/structure)”,

“market_structure”: “Higher Highs/Lows yoki boshqa struktura”,
“session”: “London | New York | Tokyo | Sydney | Overlap”,
“indicators_summary”: “RSI, MACD, EMA holati qisqacha”,
“reasoning”: “signal sababi 3-4 jumlada”,
“risk_warning”: “muhim ogohlantirish”
}}”””

```
    # Gemini ga rasm + matn yuborish
    pil_img = PIL.Image.open(io.BytesIO(raw_bytes))
    resp  = gemini.generate_content([prompt, pil_img])
    raw   = resp.text
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError("JSON topilmadi")
    d = json.loads(match.group())

    sid = save_and_get_sid(uid, d, "manual")
    cfg(uid)["last_sid"] = sid

    await m.delete()
    await update.message.reply_text(
        format_signal(d, sid),
        parse_mode="Markdown",
        reply_markup=result_kb(sid)
    )

except Exception as e:
    logger.error(f"analyze_chart xato: {e}")
    await m.edit_text(f"❌ Xato: {str(e)[:150]}")
```

# ═══════════════════════════════════════════

# JORIY NARXLAR

# ═══════════════════════════════════════════

async def show_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
m = await update.message.reply_text(“📡 Narxlar yuklanmoqda…”)
lines = [“💱 *Joriy Forex Narxlar (OANDA)*\n”]
for pair in WATCH_PAIRS:
price = get_current_price(pair)
if price:
lines.append(
f”`{pair.replace('_','/'):<10}` “
f”Bid:`{price['bid']:.5f}`  “
f”Spread:`{price['spread']:.5f}`”
)
else:
lines.append(f”`{pair.replace('_','/'):<10}` — yuklanmadi”)
await m.edit_text(”\n”.join(lines), parse_mode=“Markdown”)

# ═══════════════════════════════════════════

# PINE SCRIPT

# ═══════════════════════════════════════════

async def generate_pine(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
knowledge = get_ai_knowledge()
know_txt  = “”
if knowledge:
best = knowledge[0]
know_txt = f”\nEng muvaffaqiyatli pattern: {best[‘pattern’]} ({best[‘win_rate’]}% win-rate)”

```
steps = ["⚙️ Strategiya tayyorlanmoqda...", "🧠 Gemini kod yozmoqda...", "📝 Yakunlanmoqda..."]
m = await update.message.reply_text(steps[0])
for s in steps[1:]:
    await asyncio.sleep(0.9)
    await m.edit_text(s)

prompt = f"""Sen TradingView Pine Script v5 ekspertisisan.{know_txt}
```

Kuchli Forex strategiya yoz. MAJBURIY:

1. EMA 20 (yashil), EMA 50 (sariq), EMA 200 (qizil)
1. RSI(14) — pastki panel
1. MACD — pastki panel
1. Avtomatik Support/Resistance (so’nggi 20 bar)
1. BUY → yashil o’q (plotshape, pastdan)
1. SELL → qizil o’q (plotshape, ustidan)
1. SL chizig’i → qizil punktir
1. TP1, TP2, TP3 → yashil darajalar
1. Trend background (ochiq rangli)
1. Win/Loss hisobchi jadval (o’ng yuqori)
1. BUY va SELL uchun alohida Alert shartlari

FAQAT Pine Script kodi yoz, boshqa hech narsa. //@version=5 bilan boshlash shart.”””

```
try:
    resp = gemini.generate_content(prompt)
    code = resp.text.strip()
    match = re.search(r'```(?:pine|pinescript)?\n(.*?)```', code, re.DOTALL)
    if match:
        code = match.group(1).strip()

    await m.delete()
    await update.message.reply_text(
        "📜 *AI Pine Script (Gemini)*\n\n"
        "✅ O'rganilgan strategiya asosida\n"
        "✅ Entry · SL · TP1/2/3 chiziqlari\n"
        "✅ Alert tayyor\n\n"
        "*TradingView → Pine Editor → Joylashtiring*",
        parse_mode="Markdown"
    )
    for i in range(0, len(code), 3800):
        await update.message.reply_text(
            f"```pine\n{code[i:i+3800]}\n```",
            parse_mode="Markdown"
        )
except Exception as e:
    await m.edit_text(f"❌ Xato: {str(e)[:150]}")
```

# ═══════════════════════════════════════════

# AI BILIMI

# ═══════════════════════════════════════════

async def show_knowledge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
knowledge = get_ai_knowledge()
if not knowledge:
await update.effective_message.reply_text(
“🧠 *AI hali o’rganmoqda…*\n\n”
“Signallar yuboring va WIN/LOSS bosing.\n”
“Kamida 2 natija kerak! 📚”,
parse_mode=“Markdown”
)
return

```
medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
txt = "╔════════════════════╗\n║  🧠 AI BILIM BANKI ║\n╚════════════════════╝\n\n"
for i, k in enumerate(knowledge[:5]):
    bar = "█" * int(k["win_rate"] // 10) + "░" * (10 - int(k["win_rate"] // 10))
    txt += (
        f"{medals[i] if i < 5 else '•'} *{k['pattern']}*\n"
        f"   `{bar}` *{k['win_rate']}%*\n"
        f"   💱 {k['best_pair']}  ⏰ {k['best_timeframe']}\n"
        f"   📡 {k['total']} signal\n\n"
    )
txt += "🔄 _Har natija AI ni yanada aqlliroq qiladi!_"
await update.effective_message.reply_text(txt, parse_mode="Markdown")
```

# ═══════════════════════════════════════════

# STATISTIKA

# ═══════════════════════════════════════════

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid = update.effective_user.id
g   = get_global_stats()
u   = get_user_stats(uid)

```
txt = (
    "╔══════════════════════╗\n"
    "║   📊 STATISTIKA      ║\n"
    "╚══════════════════════╝\n\n"
    "🌍 *Global natijalar:*\n"
    f"   👥 Foydalanuvchilar: `{g['users']}`\n"
    f"   📡 Jami signal: `{g['total']}`\n"
    f"   🔍 Tahlil qilingan: `{g['analyzed']}`\n"
    f"   🏆 Win Rate: `{g['win_rate']}%`\n\n"
    "🏅 *Top Patternlar:*\n"
)
for p in g.get("top_patterns", []):
    txt += f"   ⭐ {p[0]}: `{round(p[1],1)}%`\n"
txt += (
    f"\n👤 *Sizning natijangiz:*\n"
    f"   📊 Signallar: `{u['total']}`\n"
    f"   ✅ To'g'ri: `{u['correct']}`\n"
    f"   📈 Win Rate: `{u['win_rate']}%`\n\n"
    "🧠 _Har WIN/LOSS bossangiz — AI o'rganadi!_"
)
await update.message.reply_text(txt, parse_mode="Markdown")
```

# ═══════════════════════════════════════════

# BILDIRISHNOMA MENYU

# ═══════════════════════════════════════════

async def notif_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid = update.effective_user.id
s   = cfg(uid)
txt = (
“🔔 *Bildirishnoma Sozlamalari*\n\n”
f”Holat: {‘✅ Yoqiq’ if s[‘notif’] else ‘❌ O\‘chiq’}\n”
f”Timeframe: `{s['timeframe']}`\n”
f”Interval: `{s['interval']}` daqiqa\n\n”
“Sozlamalarni o’zgartiring:”
)
await update.message.reply_text(
txt, parse_mode=“Markdown”,
reply_markup=notif_kb(s[“notif”], s[“timeframe”], s[“interval”])
)

# ═══════════════════════════════════════════

# AVTOMATIK SIGNAL JOB

# ═══════════════════════════════════════════

async def auto_signal_job(ctx: ContextTypes.DEFAULT_TYPE):
uid = ctx.job.data
s   = cfg(uid)
tf  = s.get(“timeframe”, “H1”)

```
knowledge = get_ai_knowledge()
signals   = scan_all_pairs(tf, knowledge)

if not signals:
    return

for d in signals[:3]:
    sid = save_and_get_sid(uid, d, "auto")
    try:
        await ctx.bot.send_message(
            chat_id=uid,
            text=f"🔔 *AVTOMATIK SIGNAL*\n\n{format_signal(d, sid)}",
            parse_mode="Markdown",
            reply_markup=result_kb(sid)
        )
    except Exception as e:
        logger.error(f"Auto signal yuborish xato: {e}")
```

# ═══════════════════════════════════════════

# CALLBACK HANDLER

# ═══════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
q   = update.callback_query
await q.answer()
uid = q.from_user.id
d   = q.data
s   = cfg(uid)

```
# ── Natija qaydlash ─────────────────────
if d.startswith("r_"):
    parts = d.split("_")
    rtype = parts[1]
    sid   = int(parts[2])
    if rtype == "SKIP":
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("⏭ O'tkazib yuborildi.")
        return
    pl = 2.0 if rtype == "WIN" else -1.0
    update_signal_result(sid, rtype, pl)
    emoji = "🎉 To'g'ri signal!" if rtype == "WIN" else "📚 AI o'rgandi!"
    await q.edit_message_reply_markup(reply_markup=None)
    await q.message.reply_text(
        f"{emoji}\n`#{sid}` saqlandi. 🧠",
        parse_mode="Markdown"
    )
    return

# ── Juftlik skan ────────────────────────
if d.startswith("scan_"):
    pair = d.replace("scan_", "")
    tf   = s.get("timeframe", "H1")
    if pair == "ALL":
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(
            f"🔍 Barcha {len(WATCH_PAIRS)} juftlik skanlanmoqda... `{tf}`\n⏳ Bir oz kuting..."
        )
        knowledge = get_ai_knowledge()
        signals   = scan_all_pairs(tf, knowledge)
        if not signals:
            await q.message.reply_text("😔 Hozir kuchli signal topilmadi.")
            return
        for sig in signals[:5]:
            sid = save_and_get_sid(uid, sig, "auto")
            await q.message.reply_text(
                format_signal(sig, sid),
                parse_mode="Markdown",
                reply_markup=result_kb(sid)
            )
    else:
        await q.edit_message_reply_markup(reply_markup=None)
        await do_scan(update, ctx, pair, tf, uid)
    return

# ── Timeframe ───────────────────────────
tf_map = {"tf_M15": "M15", "tf_H1": "H1", "tf_H4": "H4", "tf_D": "D"}
if d in tf_map:
    s["timeframe"] = tf_map[d]
    await q.edit_message_text(
        f"⏰ Timeframe: *{tf_map[d]}* tanlandi!\n"
        f"Holat: {'✅ Yoqiq' if s['notif'] else '❌ O\\'chiq'}\n"
        f"Interval: `{s['interval']}` daqiqa",
        parse_mode="Markdown",
        reply_markup=notif_kb(s["notif"], s["timeframe"], s["interval"])
    )
    return

# ── Interval ────────────────────────────
iv_map = {"iv_15": 15, "iv_30": 30, "iv_60": 60, "iv_240": 240}
if d in iv_map:
    s["interval"] = iv_map[d]
    await q.edit_message_text(
        f"⏰ Interval: *{iv_map[d]} daqiqa* tanlandi!\n"
        f"Timeframe: `{s['timeframe']}`\n"
        f"Holat: {'✅ Yoqiq' if s['notif'] else '❌ O\\'chiq'}",
        parse_mode="Markdown",
        reply_markup=notif_kb(s["notif"], s["timeframe"], s["interval"])
    )
    return

# ── Toggle ──────────────────────────────
if d == "notif_toggle":
    s["notif"] = not s["notif"]
    status = "✅ Yoqildi" if s["notif"] else "❌ O'chirildi"
    await q.edit_message_text(
        f"🔔 *{status}*\n"
        f"Timeframe: `{s['timeframe']}`\n"
        f"Interval: `{s['interval']}` daqiqa",
        parse_mode="Markdown",
        reply_markup=notif_kb(s["notif"], s["timeframe"], s["interval"])
    )
    return

# ── Saqlash ─────────────────────────────
if d == "notif_save":
    if s.get("job"):
        s["job"].schedule_removal()
        s["job"] = None

    if s["notif"]:
        job = ctx.job_queue.run_repeating(
            auto_signal_job,
            interval=s["interval"] * 60,
            first=10,
            data=uid,
            name=str(uid)
        )
        s["job"] = job
        await q.edit_message_text(
            f"✅ *Bildirishnoma yoqildi!*\n\n"
            f"⏰ Har `{s['interval']}` daqiqada signal\n"
            f"📊 Timeframe: `{s['timeframe']}`\n"
            f"🔍 OANDA → Gemini AI → Telegram\n\n"
            f"_Kuchli signal topilgandagina yuboriladi_",
            parse_mode="Markdown"
        )
    else:
        await q.edit_message_text("❌ *Bildirishnoma o'chirildi.*", parse_mode="Markdown")
```

# ═══════════════════════════════════════════

# YORDAM

# ═══════════════════════════════════════════

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
await update.effective_message.reply_text(
“ℹ️ *Qo’llanma*\n\n”
“📸 *Manual Tahlil* — chart rasm yuboring → AI tahlil\n”
“🤖 *Auto Skan* — OANDA real narx → Gemini signal\n”
“📜 *Pine Script* — TradingView strategiya kodi\n”
“🧠 *AI Bilimi* — o’rganilgan patternlar\n”
“📊 *Statistika* — win/loss natijalari\n”
“🔔 *Bildirishnoma* — avtomatik signal sozlash\n”
“💱 *Narxlar* — OANDA joriy Forex narxlari\n\n”
“✅ *Natija bildirish:*\n”
“Har signal ostida WIN/LOSS → AI o’rganadi!\n\n”
“🆓 *Powered by Google Gemini (bepul)*”,
parse_mode=“Markdown”
)

# ═══════════════════════════════════════════

# MATN HANDLER

# ═══════════════════════════════════════════

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
txt = update.message.text
routes = {
“📸 Manual Tahlil”:  lambda: update.message.reply_text(“📸 Chart screenshot yuboring!”),
“🤖 Auto Skan”:      lambda: auto_scan_menu(update, ctx),
“📜 Pine Script”:    lambda: generate_pine(update, ctx),
“🧠 AI Bilimi”:      lambda: show_knowledge(update, ctx),
“📊 Statistika”:     lambda: show_stats(update, ctx),
“🔔 Bildirishnoma”:  lambda: notif_menu(update, ctx),
“💱 Narxlar”:        lambda: show_prices(update, ctx),
“ℹ️ Yordam”:         lambda: help_cmd(update, ctx),
}
handler = routes.get(txt)
if handler:
await handler()
else:
await update.message.reply_text(
“📸 Rasm yuboring yoki tugmalardan foydalaning!”
)

# ═══════════════════════════════════════════

# MAIN

# ═══════════════════════════════════════════

def main():
init_db()
app = Application.builder().token(TELEGRAM_TOKEN).build()

```
app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("help",  help_cmd))
app.add_handler(MessageHandler(
    filters.PHOTO | filters.Document.IMAGE, analyze_chart
))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND, on_text
))
app.add_handler(CallbackQueryHandler(on_callback))

logger.info("🤖 Forex AI Bot (Gemini) ishga tushdi!")
app.run_polling(drop_pending_updates=True)
```

if **name** == “**main**”:
main()