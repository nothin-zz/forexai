import sqlite3
import json
import os
from datetime import datetime

DB_PATH = “forex_ai.db”
JSON_PATH = “forex_memory.json”

def init_db():
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

```
c.execute('''CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, pair TEXT, timeframe TEXT,
    signal TEXT, pattern TEXT,
    entry_price TEXT, stop_loss TEXT,
    tp1 TEXT, tp2 TEXT, tp3 TEXT,
    sl_pips TEXT, tp1_pips TEXT, tp2_pips TEXT, tp3_pips TEXT,
    risk_reward TEXT, confidence INTEGER,
    result TEXT DEFAULT NULL, profit_loss REAL DEFAULT NULL,
    timestamp TEXT, market_context TEXT, indicators TEXT,
    source TEXT DEFAULT 'manual'
)''')

c.execute('''CREATE TABLE IF NOT EXISTS pattern_stats (
    pattern TEXT PRIMARY KEY,
    total_signals INTEGER DEFAULT 0,
    correct_signals INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    avg_profit REAL DEFAULT 0.0,
    best_pairs TEXT DEFAULT '{}',
    best_timeframes TEXT DEFAULT '{}',
    last_updated TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER PRIMARY KEY,
    total_signals INTEGER DEFAULT 0,
    correct_signals INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    notifications INTEGER DEFAULT 0,
    interval_min INTEGER DEFAULT 60,
    joined TEXT
)''')

conn.commit()
conn.close()
```

def ensure_user(user_id):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(‘INSERT OR IGNORE INTO user_stats (user_id, joined) VALUES (?, ?)’,
(user_id, datetime.now().isoformat()))
conn.commit()
conn.close()

def save_signal(user_id, pair, timeframe, signal, pattern,
entry, sl, tp1, tp2, tp3,
sl_pips, tp1_pips, tp2_pips, tp3_pips,
rr, confidence, market_context, indicators, source=“auto”):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(’’‘INSERT INTO signals
(user_id,pair,timeframe,signal,pattern,entry_price,stop_loss,
tp1,tp2,tp3,sl_pips,tp1_pips,tp2_pips,tp3_pips,
risk_reward,confidence,timestamp,market_context,indicators,source)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)’’’,
(user_id, pair, timeframe, signal, pattern, entry, sl,
tp1, tp2, tp3, sl_pips, tp1_pips, tp2_pips, tp3_pips,
rr, confidence, datetime.now().isoformat(),
market_context, json.dumps(indicators), source))
sid = c.lastrowid
conn.commit()
conn.close()
_save_to_json(sid, user_id, pair, signal, pattern, confidence)
return sid

def update_signal_result(signal_id, result, profit_loss):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(‘UPDATE signals SET result=?, profit_loss=? WHERE id=?’,
(result, profit_loss, signal_id))
c.execute(‘SELECT pattern, pair, timeframe, user_id FROM signals WHERE id=?’, (signal_id,))
row = c.fetchone()
if row:
pattern, pair, tf, uid = row
_update_pattern_stats(c, pattern, result, profit_loss or 0, pair, tf)
_update_user_stats(c, uid, result)
conn.commit()
conn.close()
_update_json_result(signal_id, result, profit_loss)

def _update_pattern_stats(c, pattern, result, pl, pair, tf):
is_win = 1 if result == “WIN” else 0
c.execute(‘SELECT total_signals,correct_signals,avg_profit,best_pairs,best_timeframes FROM pattern_stats WHERE pattern=?’, (pattern,))
row = c.fetchone()
if row:
total   = row[0] + 1
correct = row[1] + is_win
avg_p   = ((row[2] * row[0]) + pl) / total
wr      = (correct / total) * 100
bp      = json.loads(row[3]) if row[3] else {}
bt      = json.loads(row[4]) if row[4] else {}
if is_win:
bp[pair] = bp.get(pair, 0) + 1
bt[tf]   = bt.get(tf, 0) + 1
c.execute(’’‘UPDATE pattern_stats SET total_signals=?,correct_signals=?,
win_rate=?,avg_profit=?,best_pairs=?,best_timeframes=?,last_updated=?
WHERE pattern=?’’’,
(total, correct, wr, avg_p,
json.dumps(bp), json.dumps(bt),
datetime.now().isoformat(), pattern))
else:
c.execute(’’‘INSERT INTO pattern_stats
(pattern,total_signals,correct_signals,win_rate,avg_profit,
best_pairs,best_timeframes,last_updated)
VALUES (?,1,?,?,?,?,?,?)’’’,
(pattern, is_win, is_win * 100, pl,
json.dumps({pair: 1} if is_win else {}),
json.dumps({tf: 1} if is_win else {}),
datetime.now().isoformat()))

def _update_user_stats(c, uid, result):
is_win = 1 if result == “WIN” else 0
c.execute(‘SELECT total_signals,correct_signals FROM user_stats WHERE user_id=?’, (uid,))
row = c.fetchone()
if row:
total   = row[0] + 1
correct = row[1] + is_win
c.execute(‘UPDATE user_stats SET total_signals=?,correct_signals=?,win_rate=? WHERE user_id=?’,
(total, correct, (correct / total) * 100, uid))

def get_ai_knowledge():
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(’’‘SELECT pattern,win_rate,avg_profit,best_pairs,best_timeframes,total_signals
FROM pattern_stats WHERE total_signals>=2 ORDER BY win_rate DESC’’’)
rows = c.fetchall()
conn.close()
result = []
for r in rows:
bp = json.loads(r[3]) if r[3] else {}
bt = json.loads(r[4]) if r[4] else {}
result.append({
“pattern”: r[0], “win_rate”: round(r[1], 1),
“avg_profit”: round(r[2], 2),
“best_pair”: max(bp, key=bp.get) if bp else “—”,
“best_timeframe”: max(bt, key=bt.get) if bt else “—”,
“total”: r[5]
})
return result

def get_global_stats():
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(‘SELECT COUNT(*),COUNT(result) FROM signals’)
total, analyzed = c.fetchone()
c.execute(’SELECT COUNT(*) FROM signals WHERE result=“WIN”’)
wins = c.fetchone()[0]
c.execute(‘SELECT COUNT(DISTINCT user_id) FROM signals’)
users = c.fetchone()[0]
c.execute(‘SELECT pattern,win_rate FROM pattern_stats ORDER BY win_rate DESC LIMIT 3’)
top = c.fetchall()
conn.close()
wr = round((wins / analyzed * 100), 1) if analyzed > 0 else 0
return {“total”: total, “analyzed”: analyzed, “win_rate”: wr, “users”: users, “top_patterns”: top}

def get_user_stats(user_id):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(‘SELECT total_signals,correct_signals,win_rate FROM user_stats WHERE user_id=?’, (user_id,))
row = c.fetchone()
conn.close()
if row:
return {“total”: row[0], “correct”: row[1], “win_rate”: round(row[2], 1)}
return {“total”: 0, “correct”: 0, “win_rate”: 0.0}

def _save_to_json(sid, uid, pair, signal, pattern, confidence):
data = {}
if os.path.exists(JSON_PATH):
with open(JSON_PATH, ‘r’) as f:
data = json.load(f)
data[str(sid)] = {
“user_id”: uid, “pair”: pair, “signal”: signal,
“pattern”: pattern, “confidence”: confidence,
“timestamp”: datetime.now().isoformat(), “result”: None
}
with open(JSON_PATH, ‘w’) as f:
json.dump(data, f, indent=2, ensure_ascii=False)

def _update_json_result(sid, result, pl):
if not os.path.exists(JSON_PATH):
return
with open(JSON_PATH, ‘r’) as f:
data = json.load(f)
if str(sid) in data:
data[str(sid)][“result”] = result
data[str(sid)][“profit_loss”] = pl
with open(JSON_PATH, ‘w’) as f:
json.dump(data, f, indent=2, ensure_ascii=False)