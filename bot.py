“””
bot.py — Forex AI Telegram Bot
Twelve Data + Gemini AI + Self-Learning
“””
import logging, asyncio, json, re, io
import google.generativeai as genai
import PIL.Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from database import init_db, ensure_user, save_signal, update_signal_result, get_ai_knowledge, get_global_stats, get_user_stats
from signal_engine import get_candles, get_all_prices, analyze_with_ai, scan_all_pairs, WATCH_PAIRS

# ─── API KALITLAR ─────────────────────────────────────────

TELEGRAM_TOKEN = “8776282635:AAExON8KZhR8w_ZfZthurcLb7LB2AsMuk9A”
GEMINI_API_KEY = “AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE”

# ──────────────────────────────────────────────────────────

logging.basicConfig(format=”%(asctime)s | %(levelname)s | %(message)s”, level=logging.INFO)
logger = logging.getLogger(**name**)
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel(“gemini-1.5-flash”)
user_cfg = {}

def cfg(uid):
if uid not in user_cfg:
user_cfg[uid] = {“notif”:False,“interval”:60,“timeframe”:“H1”,“job”:None,“last_sid”:None}
return user_cfg[uid]

def main_kb():
return ReplyKeyboardMarkup([
[“📸 Manual Tahlil”,“🤖 Auto Skan”],
[“📜 Pine Script”,“🧠 AI Bilimi”],
[“📊 Statistika”,“🔔 Bildirishnoma”],
[“💱 Narxlar”,“ℹ️ Yordam”],
], resize_keyboard=True)

def notif_kb(is_on, tf, interval):
lbl = “✅ Yoqiq” if is_on else “❌ O’chiq”
return InlineKeyboardMarkup([
[InlineKeyboardButton(f”🔔 Holat: {lbl}”, callback_data=“notif_toggle”)],
[InlineKeyboardButton(“M15”,callback_data=“tf_M15”),InlineKeyboardButton(“H1”,callback_data=“tf_H1”),
InlineKeyboardButton(“H4”,callback_data=“tf_H4”),InlineKeyboardButton(“D1”,callback_data=“tf_D”)],
[InlineKeyboardButton(“⏰ 15 daq”,callback_data=“iv_15”),InlineKeyboardButton(“⏰ 30 daq”,callback_data=“iv_30”),
InlineKeyboardButton(“⏰ 1 soat”,callback_data=“iv_60”),InlineKeyboardButton(“⏰ 4 soat”,callback_data=“iv_240”)],
[InlineKeyboardButton(“💾 Saqlash va Yoqish”, callback_data=“notif_save”)],
])

def result_kb(sid):
return InlineKeyboardMarkup([
[InlineKeyboardButton(“✅ WIN”,callback_data=f”r_WIN_{sid}”),InlineKeyboardButton(“❌ LOSS”,callback_data=f”r_LOSS_{sid}”)],
[InlineKeyboardButton(“⏭ O’tkazish”,callback_data=f”r_SKIP_{sid}”)],
])

def pairs_kb():
buttons,row = [],[]
for pair in WATCH_PAIRS:
row.append(InlineKeyboardButton(pair, callback_data=f”scan_{pair}”))
if len(row)==3: buttons.append(row); row=[]
if row: buttons.append(row)
buttons.append([InlineKeyboardButton(“🔍 Hammasi”, callback_data=“scan_ALL”)])
return InlineKeyboardMarkup(buttons)

def fmt(d, sid):
sig = d.get(“signal”,“WAIT”)
sl,bg = (“🟢 BUY  🚀”,“📗”) if sig==“BUY” else ((“🔴 SELL 📉”,“📕”) if sig==“SELL” else (“🟡 WAIT ⏳”,“📒”))
conf = d.get(“confidence”,50)
bar = “🟩”*(conf//20)+“⬜”*(5-conf//20)
return (f”{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n      🤖 *FOREX AI SIGNAL*\n{bg}━━━━━━━━━━━━━━━━━━━━{bg}\n\n”
f”💱 *{d.get(‘pair’,’?’)}*  ⏰ `{d.get('timeframe','?')}`\n”
f”🌊 `{d.get('trend','?')}`  🕯 `{d.get('pattern','?')}`\n”
f”🏗 *{d.get(‘market_structure’,’?’)}*  🕐 `{d.get('session','?')}`\n\n”
f”━━━━━━━━━━━━━━━━━━━━\n📡 *SIGNAL: {sl}*\n💪 {bar} `{conf}%`\n━━━━━━━━━━━━━━━━━━━━\n\n”
f”💰 *KIRISH:*\n   🎯 Entry: `{d.get('entry','?')}`\n\n”
f”🛡 *RISK:*\n   🛑 SL: `{d.get('stop_loss','?')}` ← `{d.get('sl_pips','?')} pips`\n”
f”   *{d.get(‘sl_reason’,’’)}*\n\n”
f”🏆 *MAQSADLAR:*\n”
f”   ✅ TP1: `{d.get('tp1','?')}` ← `{d.get('tp1_pips','?')} pips`\n”
f”   ✅✅ TP2: `{d.get('tp2','?')}` ← `{d.get('tp2_pips','?')} pips`\n”
f”   ✅✅✅ TP3: `{d.get('tp3','?')}` ← `{d.get('tp3_pips','?')} pips`\n”
f”   *{d.get(‘tp_reason’,’’)}*\n   ⚖️ `{d.get('risk_reward','?')}`\n\n”
f”📊 *{d.get(‘indicators_summary’,’’)}*\n💡 *{d.get(‘reasoning’,’’)}*\n”
f”⚠️ *{d.get(‘risk_warning’,’’)}*\n\n🔢 `#{sid}`\n━━━━━━━━━━━━━━━━━━━━\n_⚠️ Savdo o’z xavf-xataringiz bilan_”)

def save_sig(uid, d, source):
return save_signal(uid, d.get(“pair”,”?”), d.get(“timeframe”,”?”),
d.get(“signal”,“WAIT”), d.get(“pattern”,“Unknown”),
str(d.get(“entry”,”?”)), str(d.get(“stop_loss”,”?”)),
str(d.get(“tp1”,”?”)), str(d.get(“tp2”,”?”)), str(d.get(“tp3”,”?”)),
str(d.get(“sl_pips”,”?”)), str(d.get(“tp1_pips”,”?”)),
str(d.get(“tp2_pips”,”?”)), str(d.get(“tp3_pips”,”?”)),
str(d.get(“risk_reward”,”?”)), d.get(“confidence”,50),
d.get(“market_structure”,””), d.get(“indicators_summary”,””), source)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid=update.effective_user.id; name=update.effective_user.first_name; ensure_user(uid)
frames=[“🌑”,“🌒”,“🌓”,“🌔”,“🌕 Tayyor!”]; m=await update.message.reply_text(“🌑”)
for f in frames: await asyncio.sleep(0.3); await m.edit_text(f)
await m.delete()
await update.message.reply_text(
f”🤖 *Assalomu alaykum, {name}!*\n\n”
“`\n╔══════════════════════════════╗\n║  🧠 FOREX AI BOT v3.0       ║\n" "║  Twelve Data + Gemini AI    ║\n╚══════════════════════════════╝\n`\n”
“🚀 *Imkoniyatlar:*\n┣ 🤖 Twelve Data → real signal\n┣ 📸 Chart rasm → manual tahlil\n”
“┣ 🎯 Entry · SL · TP1/2/3\n┣ 🧠 Har signaldan o’rganadi\n┣ 📜 Pine Script\n┗ 🔔 Bildirishnoma\n\n👇 Tugmani bosing!”,
parse_mode=“Markdown”, reply_markup=main_kb())

async def auto_scan_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid=update.effective_user.id; tf=cfg(uid).get(“timeframe”,“H1”)
await update.message.reply_text(f”🤖 *Auto Skan*\nTimeframe: `{tf}`\nQaysi juftlik?”,
parse_mode=“Markdown”, reply_markup=pairs_kb())

async def do_scan(update, ctx, pair, timeframe, uid):
tf_map={“M15”:“15min”,“H1”:“1h”,“H4”:“4h”,“D”:“1day”}; td_tf=tf_map.get(timeframe,“1h”)
steps=[f”📡 {pair} olinmoqda…”,“📊 Shamlar…”,“🧠 Gemini…”,“🎯 Entry·SL·TP…”,“✨ Tayyor!”]
m=await update.effective_message.reply_text(steps[0])
for s in steps[1:]: await asyncio.sleep(0.5); await m.edit_text(s)
try:
candles=get_candles(pair,td_tf,100)
if not candles: await m.edit_text(f”❌ {pair} topilmadi.”); return
d=analyze_with_ai(pair,timeframe,candles,get_ai_knowledge())
if not d: await m.edit_text(“❌ AI tahlil qila olmadi.”); return
sid=save_sig(uid,d,“auto”); cfg(uid)[“last_sid”]=sid
await m.delete()
await update.effective_message.reply_text(fmt(d,sid),parse_mode=“Markdown”,reply_markup=result_kb(sid))
except Exception as e: await m.edit_text(f”❌ Xato: {str(e)[:150]}”)

async def analyze_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid=update.effective_user.id; ensure_user(uid)
steps=[“🔍 Rasm…”,“🧠 Gemini…”,“📐 Darajalar…”,“🎯 Entry·SL·TP…”,“✨ Tayyor!”]
m=await update.message.reply_text(steps[0])
for s in steps[1:]: await asyncio.sleep(0.5); await m.edit_text(s)
try:
if update.message.photo: file=await ctx.bot.get_file(update.message.photo[-1].file_id)
elif update.message.document and “image” in (update.message.document.mime_type or “”):
file=await ctx.bot.get_file(update.message.document.file_id)
else: await m.edit_text(“❌ Faqat rasm!”); return
raw_bytes=await file.download_as_bytearray()
pil_img=PIL.Image.open(io.BytesIO(raw_bytes))
knowledge=get_ai_knowledge()
know_block=”\n🧠 O’RGANILGAN:\n”+””.join(f”  • {k[‘pattern’]}: {k[‘win_rate’]}%\n” for k in knowledge[:5]) if knowledge else “”
prompt=f””“Sen Forex AI tahlilchisisisan.{know_block}
FAQAT JSON javob ber:
{{“pair”:”?”,“timeframe”:”?”,“trend”:”?”,“pattern”:”?”,“signal”:“BUY/SELL/WAIT”,“confidence”:80,
“entry”:”?”,“stop_loss”:”?”,“tp1”:”?”,“tp2”:”?”,“tp3”:”?”,
“sl_pips”:”?”,“tp1_pips”:”?”,“tp2_pips”:”?”,“tp3_pips”:”?”,“risk_reward”:“1:3”,
“sl_reason”:”?”,“tp_reason”:”?”,“market_structure”:”?”,“session”:”?”,
“indicators_summary”:”?”,“reasoning”:”?”,“risk_warning”:”?”}}”””
resp=gemini.generate_content([prompt,pil_img]); raw=resp.text
match=re.search(r’{.*}’,raw,re.DOTALL)
if not match: raise ValueError(“JSON topilmadi”)
d=json.loads(match.group())
sid=save_sig(uid,d,“manual”); cfg(uid)[“last_sid”]=sid
await m.delete()
await update.message.reply_text(fmt(d,sid),parse_mode=“Markdown”,reply_markup=result_kb(sid))
except Exception as e: await m.edit_text(f”❌ Xato: {str(e)[:150]}”)

async def show_prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
m=await update.message.reply_text(“📡 Narxlar olinmoqda…”)
prices=get_all_prices()
if not prices: await m.edit_text(“❌ Narxlar topilmadi.”); return
lines=[“💱 *Joriy Forex Narxlar* *(Twelve Data)*\n”]
for p in prices: lines.append(f”`{p['pair']:<10}` → `{p['price']:.5f}`”)
await m.edit_text(”\n”.join(lines),parse_mode=“Markdown”)

async def generate_pine(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
knowledge=get_ai_knowledge()
know_txt=f”\nEng yaxshi: {knowledge[0][‘pattern’]} ({knowledge[0][‘win_rate’]}%)” if knowledge else “”
steps=[“⚙️ Strategiya…”,“🧠 Gemini kod…”,“📝 Yakunlanmoqda…”]; m=await update.message.reply_text(steps[0])
for s in steps[1:]: await asyncio.sleep(0.8); await m.edit_text(s)
prompt=f””“TradingView Pine Script v5.{know_txt} EMA 20/50/200, RSI, MACD, Bollinger, Support/Resistance, BUY/SELL signallari, SL/TP1/TP2/TP3, background, jadval, Alert. FAQAT kod.”””
try:
resp=gemini.generate_content(prompt); code=resp.text.strip()
match=re.search(r’`(?:pine|pinescript)?\n(.*?)`’,code,re.DOTALL)
if match: code=match.group(1).strip()
await m.delete()
await update.message.reply_text(“📜 *AI Pine Script*\n✅ EMA+RSI+MACD+BB · SL·TP1/2/3 · Alert\n*TradingView → Pine Editor*”,parse_mode=“Markdown”)
for i in range(0,len(code),3800):
await update.message.reply_text(f”`pine\n{code[i:i+3800]}\n`”,parse_mode=“Markdown”)
except Exception as e: await m.edit_text(f”❌ Xato: {str(e)[:150]}”)

async def show_knowledge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
k=get_ai_knowledge()
if not k: await update.effective_message.reply_text(“🧠 *AI o’rganmoqda…*\nKamida 2 natija!”,parse_mode=“Markdown”); return
medals=[“🥇”,“🥈”,“🥉”,“4️⃣”,“5️⃣”]; txt=“╔════════════════════╗\n║  🧠 AI BILIM BANKI ║\n╚════════════════════╝\n\n”
for i,kk in enumerate(k[:5]):
bar=“█”*int(kk[“win_rate”]//10)+“░”*(10-int(kk[“win_rate”]//10))
txt+=f”{medals[i]} *{kk[‘pattern’]}*\n   `{bar}` *{kk[‘win_rate’]}%*\n   💱 {kk[‘best_pair’]}  ⏰ {kk[‘best_timeframe’]}\n   📡 {kk[‘total’]}\n\n”
await update.effective_message.reply_text(txt+“🔄 *Har natija AI ni aqlliroq qiladi!*”,parse_mode=“Markdown”)

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid=update.effective_user.id; g=get_global_stats(); u=get_user_stats(uid)
txt=(f”📊 *STATISTIKA*\n\n🌍 Foydalanuvchilar: `{g['users']}`\n📡 Jami: `{g['total']}`\n”
f”✅ Tahlil: `{g['analyzed']}`\n🏆 Win Rate: `{g['win_rate']}%`\n\n🏅 Top:\n”)
for p in g.get(“top_patterns”,[]): txt+=f”⭐ {p[0]}: `{round(p[1],1)}%`\n”
txt+=f”\n👤 Siz: `{u['total']}` signal · `{u['correct']}` to’g’ri · `{u['win_rate']}%`”
await update.message.reply_text(txt,parse_mode=“Markdown”)

async def notif_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
uid=update.effective_user.id; s=cfg(uid)
await update.message.reply_text(
f”🔔 *Bildirishnoma*\n{‘✅ Yoqiq’ if s[‘notif’] else ‘❌ Ochiq’}\nTF: `{s['timeframe']}`  Interval: `{s['interval']}` daq”,
parse_mode=“Markdown”,reply_markup=notif_kb(s[“notif”],s[“timeframe”],s[“interval”]))

async def auto_signal_job(ctx: ContextTypes.DEFAULT_TYPE):
uid=ctx.job.data; s=cfg(uid)
tf_map={“M15”:“15min”,“H1”:“1h”,“H4”:“4h”,“D”:“1day”}
signals=scan_all_pairs(tf_map.get(s.get(“timeframe”,“H1”),“1h”),get_ai_knowledge())
for d in signals[:2]:
sid=save_sig(uid,d,“auto”)
try: await ctx.bot.send_message(uid,f”🔔 *AVTOMATIK SIGNAL*\n\n{fmt(d,sid)}”,parse_mode=“Markdown”,reply_markup=result_kb(sid))
except Exception as e: logger.error(f”Auto signal xato: {e}”)

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
q=update.callback_query; await q.answer(); uid=q.from_user.id; d=q.data; s=cfg(uid)
if d.startswith(“r_”):
parts=d.split(”*”); rtype,sid=parts[1],int(parts[2])
if rtype==“SKIP”: await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(“⏭ O’tkazildi.”); return
update_signal_result(sid,rtype,2.0 if rtype==“WIN” else -1.0)
await q.edit_message_reply_markup(reply_markup=None)
await q.message.reply_text(f”{‘🎉’ if rtype==‘WIN’ else ‘📚’} `#{sid}` saqlandi.”,parse_mode=“Markdown”); return
if d.startswith(“scan*”):
pair=d.replace(“scan_”,””); tf=s.get(“timeframe”,“H1”)
await q.edit_message_reply_markup(reply_markup=None)
if pair==“ALL”:
await q.message.reply_text(f”🔍 Skanlanmoqda (`{tf}`)… ⏳”)
tf_map={“M15”:“15min”,“H1”:“1h”,“H4”:“4h”,“D”:“1day”}
signals=scan_all_pairs(tf_map.get(tf,“1h”),get_ai_knowledge())
if not signals: await q.message.reply_text(“😔 Kuchli signal topilmadi.”); return
for sig in signals[:3]:
sid=save_sig(uid,sig,“auto”)
await q.message.reply_text(fmt(sig,sid),parse_mode=“Markdown”,reply_markup=result_kb(sid))
else: await do_scan(update,ctx,pair,tf,uid); return
tf_map2={“tf_M15”:“M15”,“tf_H1”:“H1”,“tf_H4”:“H4”,“tf_D”:“D”}
if d in tf_map2:
s[“timeframe”]=tf_map2[d]
await q.edit_message_text(f”✅ TF: *{tf_map2[d]}*”,parse_mode=“Markdown”,reply_markup=notif_kb(s[“notif”],s[“timeframe”],s[“interval”])); return
iv_map={“iv_15”:15,“iv_30”:30,“iv_60”:60,“iv_240”:240}
if d in iv_map:
s[“interval”]=iv_map[d]
await q.edit_message_text(f”✅ Interval: *{iv_map[d]} daqiqa*”,parse_mode=“Markdown”,reply_markup=notif_kb(s[“notif”],s[“timeframe”],s[“interval”])); return
if d==“notif_toggle”:
s[“notif”]=not s[“notif”]
await q.edit_message_text(f”🔔 {‘✅’ if s[‘notif’] else ‘❌’}”,parse_mode=“Markdown”,reply_markup=notif_kb(s[“notif”],s[“timeframe”],s[“interval”])); return
if d==“notif_save”:
if s.get(“job”): s[“job”].schedule_removal(); s[“job”]=None
if s[“notif”]:
s[“job”]=ctx.job_queue.run_repeating(auto_signal_job,interval=s[“interval”]*60,first=10,data=uid,name=str(uid))
await q.edit_message_text(f”✅ *Yoqildi!*\n⏰ Har `{s['interval']}` daqiqada\n📊 `{s['timeframe']}`”,parse_mode=“Markdown”)
else: await q.edit_message_text(“❌ *O’chirildi.*”,parse_mode=“Markdown”)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
await update.effective_message.reply_text(
“ℹ️ *Qo’llanma*\n\n📸 Manual — rasm → tahlil\n🤖 Auto Skan — real signal\n”
“📜 Pine Script — TradingView\n🧠 AI Bilimi\n📊 Statistika\n🔔 Bildirishnoma\n💱 Narxlar\n\n✅ WIN/LOSS → AI o’rganadi!”,
parse_mode=“Markdown”)

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
txt=update.message.text
d={“📸 Manual Tahlil”:lambda:update.message.reply_text(“📸 Screenshot yuboring!”),
“🤖 Auto Skan”:lambda:auto_scan_menu(update,ctx),
“📜 Pine Script”:lambda:generate_pine(update,ctx),
“🧠 AI Bilimi”:lambda:show_knowledge(update,ctx),
“📊 Statistika”:lambda:show_stats(update,ctx),
“🔔 Bildirishnoma”:lambda:notif_menu(update,ctx),
“💱 Narxlar”:lambda:show_prices(update,ctx),
“ℹ️ Yordam”:lambda:help_cmd(update,ctx)}
fn=d.get(txt)
if fn: await fn()
else: await update.message.reply_text(“📸 Rasm yuboring yoki tugmadan foydalaning!”)

def main():
init_db()
app=Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler(“start”,cmd_start))
app.add_handler(CommandHandler(“help”,help_cmd))
app.add_handler(MessageHandler(filters.PHOTO|filters.Document.IMAGE,analyze_chart))
app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,on_text))
app.add_handler(CallbackQueryHandler(on_callback))
logger.info(“🤖 Bot ishga tushdi!”)
app.run_polling(drop_pending_updates=True)

if **name**==”**main**”:
main()
