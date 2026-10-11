import os, json, time, hmac, hashlib, sqlite3, urllib.parse
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = os.getenv("DATABASE_PATH", str(BASE / "zoomagnat.db"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

app = FastAPI(title="ZooMagnat MVP")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

ANIMALS = {
    "rabbit": {"name": "Кролик", "price": 50, "income": 2, "emoji": "🐰"},
    "fox": {"name": "Лиса", "price": 180, "income": 7, "emoji": "🦊"},
    "deer": {"name": "Олень", "price": 600, "income": 22, "emoji": "🦌"},
    "lion": {"name": "Лев", "price": 1800, "income": 70, "emoji": "🦁"},
}

def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS players(
            user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, coins INTEGER NOT NULL DEFAULT 250,
            last_tick INTEGER NOT NULL, created_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS animals(
            user_id INTEGER NOT NULL, animal_key TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, animal_key))""")
        c.execute("""CREATE TABLE IF NOT EXISTS ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            event TEXT NOT NULL, amount INTEGER NOT NULL, created_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS reward_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL)""")

@app.on_event("startup")
def startup():
    init_db()

def validate_init_data(raw: str) -> dict:
    # Telegram requires server-side validation. Never trust user ID supplied by browser alone.
    if not BOT_TOKEN:
        raise HTTPException(503, "BOT_TOKEN не настроен на сервере")
    if not raw:
        raise HTTPException(401, "Открой игру через Telegram")
    try:
        pairs = urllib.parse.parse_qsl(raw, keep_blank_values=True)
        data = dict(pairs)
        received_hash = data.pop("hash", None)
        if not received_hash:
            raise ValueError("no hash")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            raise ValueError("bad hash")
        auth_date = int(data.get("auth_date", "0"))
        if time.time() - auth_date > 86400 or auth_date > time.time() + 60:
            raise ValueError("expired")
        user = json.loads(data.get("user", "{}"))
        if not isinstance(user.get("id"), int):
            raise ValueError("no user")
        return user
    except Exception:
        raise HTTPException(401, "Не удалось проверить авторизацию Telegram")

def get_player(user):
    uid = user["id"]
    now = int(time.time())
    name = (user.get("first_name") or "Игрок")[:80]
    with db() as c:
        c.execute("INSERT OR IGNORE INTO players(user_id,name,coins,last_tick,created_at) VALUES(?,?,?,?,?)",
                  (uid, name, 250, now, now))
        row = c.execute("SELECT * FROM players WHERE user_id=?", (uid,)).fetchone()
        elapsed = max(0, min(now - row["last_tick"], 8 * 3600))
        holdings = c.execute("SELECT animal_key,qty FROM animals WHERE user_id=?", (uid,)).fetchall()
        income_per_minute = sum(ANIMALS[r["animal_key"]]["income"] * r["qty"] for r in holdings)
        earned = (elapsed // 60) * income_per_minute
        if earned:
            c.execute("UPDATE players SET coins=coins+?, last_tick=? WHERE user_id=?", (earned, now, uid))
            c.execute("INSERT INTO ledger(user_id,event,amount,created_at) VALUES(?,?,?,?)",
                      (uid, "offline_income", earned, now))
        else:
            c.execute("UPDATE players SET last_tick=? WHERE user_id=?", (now, uid))
        row = c.execute("SELECT * FROM players WHERE user_id=?", (uid,)).fetchone()
        holdings = c.execute("SELECT animal_key,qty FROM animals WHERE user_id=?", (uid,)).fetchall()
    animals = []
    for key, info in ANIMALS.items():
        qty = next((r["qty"] for r in holdings if r["animal_key"] == key), 0)
        animals.append({"key": key, **info, "qty": qty})
    total_income = sum(a["income"] * a["qty"] for a in animals)
    return {"user_id": uid, "name": row["name"], "coins": row["coins"],
            "income_per_minute": total_income, "animals": animals,
            "notice": "Игровые монеты не являются криптовалютой и пока не обмениваются на деньги."}

def auth(authorization: Optional[str]):
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(401, "Открой игру из Telegram")
    return validate_init_data(authorization[4:])

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/state")
def state(authorization: Optional[str] = Header(default=None)):
    user = auth(authorization)
    return get_player(user)

class Action(BaseModel):
    animal: str

@app.post("/api/buy")
def buy(action: Action, authorization: Optional[str] = Header(default=None)):
    user = auth(authorization)
    key = action.animal
    if key not in ANIMALS:
        raise HTTPException(400, "Неизвестное животное")
    info = ANIMALS[key]
    uid = user["id"]
    # SQLite transaction prevents balance race conditions for this simple MVP.
    with db() as c:
        row = c.execute("SELECT coins FROM players WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            raise HTTPException(401, "Сначала открой игру")
        if row["coins"] < info["price"]:
            raise HTTPException(400, "Недостаточно монет")
        c.execute("UPDATE players SET coins=coins-? WHERE user_id=?", (info["price"], uid))
        c.execute("""INSERT INTO animals(user_id,animal_key,qty) VALUES(?,?,1)
                     ON CONFLICT(user_id,animal_key) DO UPDATE SET qty=qty+1""", (uid, key))
        c.execute("INSERT INTO ledger(user_id,event,amount,created_at) VALUES(?,?,?,?)",
                  (uid, "buy_" + key, -info["price"], int(time.time())))
    return get_player(user)

@app.get("/api/leaderboard")
def leaderboard(authorization: Optional[str] = Header(default=None)):
    auth(authorization)
    with db() as c:
        rows = c.execute("""SELECT p.name, p.coins + COALESCE(
            (SELECT SUM(a.qty * 10) FROM animals a WHERE a.user_id=p.user_id),0) AS score
            FROM players p ORDER BY score DESC LIMIT 10""").fetchall()
    return [{"name": r["name"], "score": r["score"]} for r in rows]

@app.get("/api/health")
def health():
    return {"ok": True, "game": "ZooMagnat", "version": "0.1.0"}
