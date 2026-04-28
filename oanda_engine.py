"""
oanda_engine.py (YAXSHILANGAN FREE VERSION)
Twelve Data + Gemini AI integration
"""

import requests
import json
import google.generativeai as genai
from datetime import datetime

# ─────────────────────────────────────────
# API SETTINGS
# ─────────────────────────────────────────

TWELVE_API_KEY = "0bfaff2b15804663ae9d9536c6cf0cac"
GEMINI_API_KEY = "AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Watch list — SLASHSIZ format (Twelve Data uchun to'g'ri)
WATCH_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "USDCHF", "AUDUSD", "XAUUSD",
    "GBPJPY", "EURGBP", "NZDUSD"
]

# ─────────────────────────────────────────
# CANDLELARI Olish (Asosiy tuzatilgan qism)
# ─────────────────────────────────────────

def get_candles(pair: str, timeframe="1h", count=100):
    """
    Twelve Data dan candle olish - YAXSHILANGAN
    """
    url = "https://api.twelvedata.com/time_series"

    # Timeframe ni Twelve Data formatiga moslashtirish
    interval_map = {
        "H1": "1h",
        "H4": "4h",
        "D1": "1day",
        "1h": "1h",
        "4h": "4h",
        "1d": "1day",
        "1day": "1day"
    }
    
    interval = interval_map.get(timeframe, timeframe)

    params = {
        "symbol": pair,
        "interval": interval,
        "outputsize": count,
        "apikey": TWELVE_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        # Xatolikni aniq ko'rsatish
        if "values" not in data:
            error_msg = data.get("message", str(data))
            print(f"❌ Twelve Data Error [{pair}]: {error_msg}")
            return []

        candles = []
        for c in reversed(data["values"]):  # Eng yangi candle oxirida bo'lsin
            try:
                candles.append({
                    "time": c["datetime"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0))
                })
            except (ValueError, KeyError) as e:
                print(f"Data parse error in candle: {e}")
                continue

        print(f"✅ {pair} — {len(candles)} ta candle muvaffaqiyatli yuklandi")
        return candles

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error {pair}: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error {pair}: {e}")
        return []


# ─────────────────────────────────────────
# JORIY NARX
# ─────────────────────────────────────────

def get_current_price(pair: str):
    url = "https://api.twelvedata.com/price"

    params = {
        "symbol": pair,
        "apikey": TWELVE_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        price = float(data.get("price", 0))
        
        return {
            "bid": price,
            "ask": price + 0.0002,
            "spread": 0.0002
        }
    except Exception as e:
        print(f"Price error {pair}: {e}")
        return {"bid": 0, "ask": 0, "spread": 0}


# ─────────────────────────────────────────
# SODDA INDIKATORLAR
# ─────────────────────────────────────────

def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema_list = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_list.append(v * k + ema_list[-1] * (1 - k))
    return ema_list


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50

    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ─────────────────────────────────────────
# PATTERN DETECTION
# ─────────────────────────────────────────

def detect_pattern(candles):
    if len(candles) < 3:
        return "Unknown"

    c = candles[-1]
    o, h, l, cl = c["open"], c["high"], c["low"], c["close"]

    body = abs(cl - o)
    total_range = h - l if h != l else 0.0001

    if body / total_range < 0.15:
        return "Doji"
    elif cl > o and body > (total_range * 0.6):
        return "Strong Bullish"
    elif cl < o and body > (total_range * 0.6):
        return "Strong Bearish"
    
    return "Bullish Candle" if cl > o else "Bearish Candle"


# ─────────────────────────────────────────
# GEMINI AI TAHLILI
# ─────────────────────────────────────────

def analyze_with_ai(pair, timeframe, candles, knowledge=None):
    if not candles:
        return {}

    closes = [c["close"] for c in candles]
    current = closes[-1]

    ema20 = ema(closes, 20)[-1] if len(ema(closes, 20)) > 0 else current
    rsi_val = rsi(closes)
    pattern = detect_pattern(candles)

    last_candles = "\n".join([
        f"O:{c['open']:.5f} H:{c['high']:.5f} L:{c['low']:.5f} C:{c['close']:.5f}"
        for c in candles[-7:]
    ])

    prompt = f"""
You are an experienced Forex trader. Analyze the following data and give trading signal.

Pair: {pair}
Timeframe: {timeframe}
Current Price: {current:.5f}
RSI: {rsi_val:.1f}
Pattern: {pattern}
EMA20: {ema20:.5f}

Last 7 candles:
{last_candles}

Return **ONLY valid JSON** (hech qanday qo'shimcha matn bo'lmasin):
{{
  "signal": "BUY" or "SELL" or "WAIT",
  "confidence": 65-95,
  "entry": current price yoki yaqin daraja,
  "stop_loss": number,
  "tp1": number,
  "tp2": number,
  "tp3": number,
  "risk_reward": "1:2" or "1:3",
  "reasoning": "qisqa va aniq sabab (1-2 jumla)"
}}
"""

    try:
        resp = model.generate_content(prompt)
        text = resp.text.strip()

        # JSON ni topish
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            print("JSON topilmadi")
            return {}

        data = json.loads(match.group(0))

        # Qo'shimcha ma'lumotlar qo'shish
        data["pair"] = pair.replace("USD", "/USD") if "USD" in pair else pair
        data["timeframe"] = timeframe
        data["pattern"] = pattern

        print(f"✅ AI tahlili muvaffaqiyatli: {pair} → {data.get('signal')}")
        return data

    except Exception as e:
        print(f"AI Error {pair}: {e}")
        return {}


# ─────────────────────────────────────────
# BARCHA JUFTLIKLARNI SKAN QILISH
# ─────────────────────────────────────────

def scan_all_pairs(timeframe="1h", knowledge=None):
    results = []
    print(f"🔍 {len(WATCH_PAIRS)} ta juftlik skan qilinmoqda...")

    for pair in WATCH_PAIRS:
        try:
            candles = get_candles(pair, timeframe, 100)
            if not candles:
                continue

            result = analyze_with_ai(pair, timeframe, candles, knowledge)
            if result and result.get("signal") in ["BUY", "SELL"]:
                if result.get("confidence", 0) >= 60:
                    results.append(result)
        except Exception as e:
            print(f"Scan error {pair}: {e}")

    print(f"✅ Skan tugadi. Signal topildi: {len(results)} ta")
    return results