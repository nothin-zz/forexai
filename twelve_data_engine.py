“””
twelve_data_engine.py
Twelve Data API orqali real vaqt Forex ma’lumotlari + Gemini AI tahlil
Bepul plan: 800 so’rov/kun
“””

import requests
import json
import re
import google.generativeai as genai
from datetime import datetime

# ─────────────────────────────────────────

# SOZLAMALAR  ← O’ZGARTIRING!

# ─────────────────────────────────────────

TWELVE_API_KEY = ‘0bfaff2b15804663ae9d9536c6cf0cac’
GEMINI_API_KEY = ‘AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE’

# ─────────────────────────────────────────

TWELVE_BASE_URL = “https://api.twelvedata.com”

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel(“gemini-1.5-flash”)

# Kuzatiladigan Forex juftliklar

WATCH_PAIRS = [
“EUR/USD”, “GBP/USD”, “USD/JPY”,
“USD/CHF”, “AUD/USD”, “XAU/USD”,
“GBP/JPY”, “EUR/GBP”, “NZD/USD”,
“USD/CAD”, “EUR/JPY”, “GBP/CHF”
]

# Timeframe mapping

TF_MAP = {
“M15”: “15min”,
“H1”:  “1h”,
“H4”:  “4h”,
“D1”:  “1day”,
}

# ═══════════════════════════════════════════

# TWELVE DATA API

# ═══════════════════════════════════════════

def get_candles(pair: str, timeframe: str = “H1”, count: int = 100) -> list:
“””
Twelve Data dan candlestick ma’lumotlarini olish
pair: “EUR/USD” formatida
timeframe: “M15”, “H1”, “H4”, “D1”
“””
tf = TF_MAP.get(timeframe, “1h”)
url = f”{TWELVE_BASE_URL}/time_series”
params = {
“symbol”:     pair,
“interval”:   tf,
“outputsize”: count,
“apikey”:     TWELVE_API_KEY,
“format”:     “JSON”
}

```
try:
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if data.get("status") == "error":
        print(f"Twelve Data xato ({pair}): {data.get('message')}")
        return []

    values = data.get("values", [])
    candles = []
    for v in reversed(values):   # eski → yangi tartibda
        candles.append({
            "time":   v.get("datetime", ""),
            "open":   float(v.get("open", 0)),
            "high":   float(v.get("high", 0)),
            "low":    float(v.get("low", 0)),
            "close":  float(v.get("close", 0)),
            "volume": float(v.get("volume", 0)),
        })
    return candles

except Exception as e:
    print(f"get_candles xato ({pair}): {e}")
    return []
```

def get_current_price(pair: str) -> dict:
“”“Joriy narxni olish”””
url = f”{TWELVE_BASE_URL}/price”
params = {“symbol”: pair, “apikey”: TWELVE_API_KEY}

```
try:
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    price = float(data.get("price", 0))

    # Spread taxminiy hisoblash
    is_jpy = "JPY" in pair
    spread = round(price * 0.0001 if not is_jpy else price * 0.001, 5)

    return {
        "price":  price,
        "bid":    round(price - spread / 2, 5),
        "ask":    round(price + spread / 2, 5),
        "spread": spread
    }
except Exception as e:
    print(f"get_current_price xato ({pair}): {e}")
    return {}
```

def get_quote(pair: str) -> dict:
“”“To’liq quote ma’lumotlari”””
url = f”{TWELVE_BASE_URL}/quote”
params = {“symbol”: pair, “apikey”: TWELVE_API_KEY}

```
try:
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    return {
        "open":    float(data.get("open", 0)),
        "high":    float(data.get("high", 0)),
        "low":     float(data.get("low", 0)),
        "close":   float(data.get("close", 0)),
        "change":  data.get("change", "0"),
        "percent": data.get("percent_change", "0"),
        "name":    data.get("name", pair),
    }
except Exception as e:
    print(f"get_quote xato ({pair}): {e}")
    return {}
```

# ═══════════════════════════════════════════

# TEXNIK INDIKATORLAR (ichki hisoblash)

# ═══════════════════════════════════════════

def calc_ema(closes: list, period: int) -> list:
if len(closes) < period:
return []
k = 2 / (period + 1)
ema = [sum(closes[:period]) / period]
for price in closes[period:]:
ema.append(price * k + ema[-1] * (1 - k))
return ema

def calc_rsi(closes: list, period: int = 14) -> float:
if len(closes) < period + 1:
return 50.0
gains, losses = [], []
for i in range(1, len(closes)):
diff = closes[i] - closes[i - 1]
gains.append(max(diff, 0))
losses.append(max(-diff, 0))
avg_gain = sum(gains[-period:]) / period
avg_loss = sum(losses[-period:]) / period
if avg_loss == 0:
return 100.0
return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calc_macd(closes: list) -> dict:
ema12 = calc_ema(closes, 12)
ema26 = calc_ema(closes, 26)
if not ema12 or not ema26:
return {“macd”: 0, “signal”: 0, “histogram”: 0}
min_len   = min(len(ema12), len(ema26))
macd_line = [ema12[i] - ema26[i] for i in range(-min_len, 0)]
sig_line  = calc_ema(macd_line, 9)
if not sig_line:
return {“macd”: 0, “signal”: 0, “histogram”: 0}
m = round(macd_line[-1], 6)
s = round(sig_line[-1], 6)
return {“macd”: m, “signal”: s, “histogram”: round(m - s, 6)}

def calc_atr(candles: list, period: int = 14) -> float:
if len(candles) < period:
return 0.0
trs = []
for i in range(1, len(candles)):
h, l, pc = candles[i][“high”], candles[i][“low”], candles[i-1][“close”]
trs.append(max(h - l, abs(h - pc), abs(l - pc)))
return round(sum(trs[-period:]) / period, 5)

def calc_bollinger(closes: list, period: int = 20) -> dict:
if len(closes) < period:
return {“upper”: 0, “middle”: 0, “lower”: 0}
sma   = sum(closes[-period:]) / period
std   = (sum((x - sma) ** 2 for x in closes[-period:]) / period) ** 0.5
return {
“upper”:  round(sma + 2 * std, 5),
“middle”: round(sma, 5),
“lower”:  round(sma - 2 * std, 5)
}

def find_support_resistance(candles: list, lookback: int = 30) -> dict:
recent = candles[-lookback:] if len(candles) >= lookback else candles
highs  = sorted([c[“high”] for c in recent])
lows   = sorted([c[“low”]  for c in recent])
return {
“strong_resistance”: round(highs[-1], 5),
“mid_resistance”:    round((highs[-1] + highs[-3]) / 2, 5),
“mid_support”:       round((lows[0] + lows[2]) / 2, 5),
“strong_support”:    round(lows[0], 5),
}

def detect_pattern(candles: list) -> str:
if len(candles) < 3:
return “Unknown”
c1, c2, c = candles[-3], candles[-2], candles[-1]
o, h, l, cl = c[“open”], c[“high”], c[“low”], c[“close”]
body         = abs(cl - o)
rng          = h - l if h != l else 0.0001
upper        = h - max(o, cl)
lower        = min(o, cl) - l

```
if body / rng < 0.1:                                          return "Doji"
if lower > 2 * body and upper < body:                         return "Hammer"
if upper > 2 * body and lower < body:                         return "Shooting Star"
if lower > 3 * body:                                          return "Bullish Pin Bar"
if upper > 3 * body:                                          return "Bearish Pin Bar"
if body / rng > 0.9:
    return "Bullish Marubozu" if cl > o else "Bearish Marubozu"
if (c2["close"] < c2["open"] and cl > o
        and o < c2["close"] and cl > c2["open"]):             return "Bullish Engulfing"
if (c2["close"] > c2["open"] and cl < o
        and o > c2["close"] and cl < c2["open"]):             return "Bearish Engulfing"
if (c1["close"] < c1["open"]
        and abs(c2["close"] - c2["open"]) < (c1["open"] - c1["close"]) * 0.3
        and cl > o and cl > (c1["open"] + c1["close"]) / 2): return "Morning Star"
if (c1["close"] > c1["open"]
        and abs(c2["close"] - c2["open"]) < (c1["close"] - c1["open"]) * 0.3
        and cl < o and cl < (c1["open"] + c1["close"]) / 2): return "Evening Star"
if h < candles[-2]["high"] and l > candles[-2]["low"]:        return "Inside Bar"
return "No Clear Pattern"
```

# ═══════════════════════════════════════════

# GEMINI AI TAHLIL

# ═══════════════════════════════════════════

def analyze_with_ai(pair: str, timeframe: str, candles: list, knowledge: list = None) -> dict:
if not candles or len(candles) < 20:
return {}

```
closes  = [c["close"] for c in candles]
current = closes[-1]

ema20   = calc_ema(closes, 20)
ema50   = calc_ema(closes, 50)
ema200  = calc_ema(closes, 200)
rsi     = calc_rsi(closes)
macd    = calc_macd(closes)
atr     = calc_atr(candles)
bb      = calc_bollinger(closes)
levels  = find_support_resistance(candles)
pattern = detect_pattern(candles)

# So'nggi 10 sham
recent_str = ""
for c in candles[-10:]:
    d = "🟢" if c["close"] > c["open"] else "🔴"
    recent_str += f"{d} O:{c['open']:.5f} H:{c['high']:.5f} L:{c['low']:.5f} C:{c['close']:.5f}\n"

know_block = ""
if knowledge:
    know_block = "\n🧠 O'RGANILGAN BILIMLAR (hisobga ol):\n"
    for k in knowledge[:5]:
        know_block += f"  • {k['pattern']}: {k['win_rate']}% win-rate | best: {k['best_pair']}\n"

# ATR ga asosan pip o'lchami
is_jpy  = "JPY" in pair
pip_val = 0.01 if is_jpy else 0.0001
atr_pips = round(atr / pip_val)

prompt = f"""Sen dunyo darajasidagi professional Forex tahlilchisisisan.{know_block}
```

📊 BOZOR MA’LUMOTLARI (Twelve Data):
Juftlik: {pair}  |  Timeframe: {timeframe}
Joriy narx: {current:.5f}

📈 INDIKATORLAR:
• EMA20:  {ema20[-1]:.5f if ema20 else ‘N/A’}  {‘▲ narx ustida’ if ema20 and current > ema20[-1] else ‘▼ narx ostida’}
• EMA50:  {ema50[-1]:.5f if ema50 else ‘N/A’}
• EMA200: {ema200[-1]:.5f if ema200 else ‘N/A’}
• RSI(14): {rsi}  {‘→ Overbought’ if rsi > 70 else ‘→ Oversold’ if rsi < 30 else ‘→ Neytral’}
• MACD: {macd[‘macd’]:.6f} | Signal: {macd[‘signal’]:.6f} | Hist: {macd[‘histogram’]:.6f}
• Bollinger: U:{bb[‘upper’]:.5f} M:{bb[‘middle’]:.5f} L:{bb[‘lower’]:.5f}
• ATR(14): {atr:.5f}  (~{atr_pips} pips)

🗺 KALIT DARAJALAR:
• Kuchli Resistance: {levels[‘strong_resistance’]:.5f}
• O’rta Resistance:  {levels[‘mid_resistance’]:.5f}
• O’rta Support:     {levels[‘mid_support’]:.5f}
• Kuchli Support:    {levels[‘strong_support’]:.5f}

🕯 PATTERN: {pattern}

📉 SO’NGGI 10 SHAM:
{recent_str}

Chuqur tahlil qilib FAQAT quyidagi JSON formatida javob ber (boshqa hech narsa yozma):

{{
“signal”: “BUY | SELL | WAIT”,
“confidence”: 82,
“trend”: “UPTREND | DOWNTREND | SIDEWAYS”,

“entry”: {current:.5f},
“stop_loss”: 0.00000,
“tp1”: 0.00000,
“tp2”: 0.00000,
“tp3”: 0.00000,

“sl_pips”: {atr_pips},
“tp1_pips”: 0,
“tp2_pips”: 0,
“tp3_pips”: 0,
“risk_reward”: “1:3”,

“sl_reason”: “SL nima uchun shu joyda (swing/support/resistance asosida)”,
“tp_reason”: “TP darajalari sababi (resistance/fib/structure)”,

“market_structure”: “HH/HL yoki LH/LL yoki range”,
“session”: “London | New York | Tokyo | Sydney | Overlap”,
“indicators_summary”: “RSI, MACD, EMA holati qisqacha”,
“reasoning”: “signal sababi 3-4 jumlada”,
“risk_warning”: “muhim ogohlantirish”
}}

QOIDALAR:

- SL: so’nggi swing high/low tashqarisida, ATR*1.5 kamida
- TP1: 1:1 RR, TP2: 1:2 RR, TP3: 1:3 RR
- Barcha narxlar ANIQ bo’lsin
- confidence 60 dan past bo’lsa signal=WAIT”””
  
  try:
  resp  = gemini.generate_content(prompt)
  raw   = resp.text
  match = re.search(r’{.*}’, raw, re.DOTALL)
  if not match:
  return {}
  result = json.loads(match.group())
  result[“pair”]      = pair
  result[“timeframe”] = timeframe
  result[“pattern”]   = pattern
  result[“atr”]       = atr
  result[“levels”]    = levels
  return result
  except Exception as e:
  print(f”AI tahlil xato ({pair}): {e}”)
  return {}

def scan_all_pairs(timeframe: str = “H1”, knowledge: list = None) -> list:
“”“Barcha juftliklarni skan qilib kuchli signallarni qaytarish”””
signals = []
for pair in WATCH_PAIRS:
try:
candles = get_candles(pair, timeframe, count=100)
if not candles:
print(f”⚠️ {pair} — candle yo’q”)
continue
result = analyze_with_ai(pair, timeframe, candles, knowledge)
if result and result.get(“signal”) in [“BUY”, “SELL”]:
conf = result.get(“confidence”, 0)
if conf >= 70:
signals.append(result)
print(f”✅ {pair} → {result[‘signal’]} ({conf}%)”)
else:
print(f”⏭ {pair} — past ishonch ({conf}%)”)
else:
print(f”😐 {pair} — WAIT yoki signal yo’q”)
except Exception as e:
print(f”❌ Skan xato ({pair}): {e}”)
return signals
