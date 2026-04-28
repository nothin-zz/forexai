"""
bot.py — Forex AI Self-Learning Telegram Bot
FREE VERSION:
Twelve Data + Gemini AI + Self-Learning
"""

import logging
import asyncio
import base64
import json
import re

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)

from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from database import (
    init_db, ensure_user, save_signal, update_signal_result,
    get_ai_knowledge, get_global_stats, get_user_stats
)

from oanda_engine import (
    get_candles, get_current_price, analyze_with_ai,
    scan_all_pairs, WATCH_PAIRS
)

# ─────────────────────────────────────────
# SOZLAMALAR
# ─────────────────────────────────────────

TELEGRAM_TOKEN = "8776282635:AAExON8KZhR8w_ZfZthurcLb7LB2AsMuk9A"

# Gemini API key (Claude o‘rniga)
GEMINI_API_KEY = "AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE"

# ─────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Foydalanuvchi sozlamalari
user_cfg = {}


def cfg(uid: int):
    if uid not in user_cfg:
        user_cfg[uid] = {
            "notif": False,
            "interval": 60,
            "timeframe": "H1",
            "job": None,
            "last_sid": None
        }
    return user_cfg[uid]


# ═══════════════════════════════════════════
# KLAVIATURALAR
# ═══════════════════════════════════════════

def main_kb():
    return ReplyKeyboardMarkup([
        ["📸 Manual Tahlil", "🤖 Auto Skan"],
        ["📜 Pine Script", "🧠 AI Bilimi"],
        ["📊 Statistika", "🔔 Bildirishnoma"],
        ["💱 Narxlar", "ℹ️ Yordam"]
    ], resize_keyboard=True)


def result_kb(sid: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ WIN", callback_data=f"r_WIN_{sid}"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"r_LOSS_{sid}")
        ],
        [
            InlineKeyboardButton("⏭ O‘tkazish", callback_data=f"r_SKIP_{sid}")
        ]
    ])


def pairs_kb():
    buttons = []
    row = []

    for pair in WATCH_PAIRS:
        row.append(
            InlineKeyboardButton(
                pair.replace("_", "/"),
                callback_data=f"scan_{pair}"
            )
        )

        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔍 Hammasi", callback_data="scan_ALL")
    ])

    return InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════
# SIGNAL FORMAT
# ═══════════════════════════════════════════

def format_signal(d: dict, sid: int):
    signal = d.get("signal", "WAIT")

    if signal == "BUY":
        icon = "🟢 BUY 🚀"
    elif signal == "SELL":
        icon = "🔴 SELL 📉"
    else:
        icon = "🟡 WAIT ⏳"

    return (
        f"🤖 *FOREX AI SIGNAL*\n\n"
        f"💱 Pair: *{d.get('pair', '?')}*\n"
        f"⏰ TF: `{d.get('timeframe', '?')}`\n"
        f"📡 Signal: *{icon}*\n"
        f"💪 Confidence: `{d.get('confidence', 50)}%`\n\n"

        f"🎯 Entry: `{d.get('entry', '?')}`\n"
        f"🛑 Stop Loss: `{d.get('stop_loss', '?')}`\n"
        f"✅ TP1: `{d.get('tp1', '?')}`\n"
        f"✅ TP2: `{d.get('tp2', '?')}`\n"
        f"✅ TP3: `{d.get('tp3', '?')}`\n\n"

        f"⚖️ RR: `{d.get('risk_reward', '?')}`\n\n"

        f"📊 Trend: `{d.get('trend', '?')}`\n"
        f"🕯 Pattern: `{d.get('pattern', '?')}`\n\n"

        f"💡 Reason:\n_{d.get('reasoning', '')}_\n\n"

        f"🔢 Signal ID: `#{sid}`\n\n"
        f"_Savdo o‘z xavfi bilan_"
    )


# ═══════════════════════════════════════════
# /start
# ═══════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name

    ensure_user(uid)

    await update.message.reply_text(
        f"🤖 Assalomu alaykum, *{name}!*\n\n"
        f"FREE Forex AI Bot tayyor.\n\n"
        f"👇 Tugmalardan foydalaning",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )


# ═══════════════════════════════════════════
# AUTO SKAN
# ═══════════════════════════════════════════

async def auto_scan_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Auto Skan*\n\n"
        "Qaysi juftlikni tahlil qilamiz?",
        parse_mode="Markdown",
        reply_markup=pairs_kb()
    )


async def do_scan(update, ctx, pair, timeframe, uid):
    m = await update.effective_message.reply_text(
        f"⏳ {pair.replace('_', '/')} tahlil qilinmoqda..."
    )

    try:
        candles = get_candles(pair, timeframe, 100)

        if not candles:
            await m.edit_text("❌ Candle topilmadi")
            return

        knowledge = get_ai_knowledge()

        result = analyze_with_ai(
            pair,
            timeframe,
            candles,
            knowledge
        )

        if not result:
            await m.edit_text("❌ AI signal topmadi")
            return

        sid = save_signal(
            uid,
            result.get("pair", "?"),
            result.get("timeframe", "?"),
            result.get("signal", "WAIT"),
            result.get("pattern", "Unknown"),
            str(result.get("entry", "?")),
            str(result.get("stop_loss", "?")),
            str(result.get("tp1", "?")),
            str(result.get("tp2", "?")),
            str(result.get("tp3", "?")),
            str(result.get("sl_pips", "?")),
            str(result.get("tp1_pips", "?")),
            str(result.get("tp2_pips", "?")),
            str(result.get("tp3_pips", "?")),
            str(result.get("risk_reward", "?")),
            result.get("confidence", 50),
            result.get("market_structure", ""),
            result.get("indicators_summary", ""),
            "auto"
        )

        await m.delete()

        await update.effective_message.reply_text(
            format_signal(result, sid),
            parse_mode="Markdown",
            reply_markup=result_kb(sid)
        )

    except Exception as e:
        logger.error(e)
        await m.edit_text(f"❌ Xato: {str(e)}")


# ═══════════════════════════════════════════
# CALLBACK
# ═══════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data

    if data.startswith("scan_"):
        pair = data.replace("scan_", "")
        tf = cfg(uid)["timeframe"]

        await q.edit_message_reply_markup(reply_markup=None)

        if pair == "ALL":
            await q.message.reply_text(
                "🔍 Barcha juftliklar skan qilinmoqda..."
            )
        else:
            await do_scan(update, ctx, pair, tf, uid)

        return

    if data.startswith("r_"):
        parts = data.split("_")
        result_type = parts[1]
        sid = int(parts[2])

        if result_type == "SKIP":
            await q.edit_message_reply_markup(reply_markup=None)
            return

        pl = 2.0 if result_type == "WIN" else -1.0

        update_signal_result(
            sid,
            result_type,
            pl
        )

        await q.edit_message_reply_markup(reply_markup=None)

        await q.message.reply_text(
            f"🧠 Natija saqlandi: `{result_type}`",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════
# TEXT HANDLER
# ═══════════════════════════════════════════

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🤖 Auto Skan":
        await auto_scan_menu(update, ctx)

    elif text == "ℹ️ Yordam":
        await update.message.reply_text(
            "📘 Tugmalar orqali foydalaning:\n\n"
            "🤖 Auto Skan\n"
            "📸 Manual\n"
            "📜 Pine Script\n"
            "🔔 Bildirishnoma"
        )

    else:
        await update.message.reply_text(
            "Tugmalardan foydalaning 🙂"
        )


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    init_db()

    app = Application.builder().token(
        TELEGRAM_TOKEN
    ).build()

    app.add_handler(
        CommandHandler("start", cmd_start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_text
        )
    )

    app.add_handler(
        CallbackQueryHandler(on_callback)
    )

    logger.info("🤖 FREE Forex AI Bot ishga tushdi!")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
