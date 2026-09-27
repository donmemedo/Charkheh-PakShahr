"""SabzBank API — points for separated dry waste. Single demo user, SQLite storage."""
import json
import os
import random
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.getenv("DB_PATH", "data/sabz.db")

# points per kg, kg CO2 saved per kg
MATERIALS = {
    "paper":   {"fa": "کاغذ و مقوا", "en": "Paper & cardboard", "pts": 80,  "co2": 0.9, "color": "#f59e0b"},
    "plastic": {"fa": "پلاستیک و پت", "en": "Plastic & PET",     "pts": 120, "co2": 1.5, "color": "#0ea5e9"},
    "metal":   {"fa": "فلز و قوطی", "en": "Metal & cans",        "pts": 200, "co2": 4.0, "color": "#a855f7"},
    "glass":   {"fa": "شیشه", "en": "Glass",                     "pts": 50,  "co2": 0.3, "color": "#10b981"},
    "ewaste":  {"fa": "پسماند الکترونیکی", "en": "E-waste",      "pts": 300, "co2": 2.0, "color": "#ef4444"},
}
SLOTS = ["08-11", "11-14", "14-17", "17-20"]
TIERS = [("bronze", 0), ("silver", 2000), ("gold", 6000)]

REWARDS = [
    {"id": "metro",   "cat": "transport", "cost": 300,  "fa": "شارژ ۵۰ هزار تومانی بلیت مترو", "en": "50K toman metro top-up", "partner": {"fa": "متروی تهران", "en": "Tehran Metro"}},
    {"id": "coffee",  "cat": "food",      "cost": 450,  "fa": "یک قهوه رایگان", "en": "One free coffee", "partner": {"fa": "کافه سبز", "en": "Cafe Sabz"}},
    {"id": "grocery", "cat": "shopping",  "cost": 900,  "fa": "۱۵٪ تخفیف خرید سوپرمارکت", "en": "15% off groceries", "partner": {"fa": "فروشگاه زنجیره‌ای", "en": "Chain market"}},
    {"id": "book",    "cat": "shopping",  "cost": 700,  "fa": "کارت هدیه کتاب", "en": "Book gift card", "partner": {"fa": "کتاب‌فروشی شهر", "en": "City Books"}},
    {"id": "net",     "cat": "digital",   "cost": 600,  "fa": "بسته اینترنت ۱۰ گیگ", "en": "10 GB data pack", "partner": {"fa": "اپراتور همراه", "en": "Mobile operator"}},
    {"id": "tree",    "cat": "impact",    "cost": 500,  "fa": "کاشت یک درخت به نام شما", "en": "Plant a tree in your name", "partner": {"fa": "پویش درخت", "en": "Tree campaign"}},
    {"id": "bike",    "cat": "transport", "cost": 250,  "fa": "۲ ساعت دوچرخه اشتراکی", "en": "2 h shared bike", "partner": {"fa": "بی‌دود", "en": "Bidood"}},
    {"id": "cinema",  "cat": "food",      "cost": 1200, "fa": "دو بلیت سینما", "en": "Two cinema tickets", "partner": {"fa": "سینما آزادی", "en": "Azadi Cinema"}},
]

MISSIONS = [
    {"id": "pet", "pts": 40, "fa": {"q": "قبل از تحویل بطری پت، بهتر است چه کنیم؟", "a": ["بشوییم و له کنیم", "با درب محکم ببندیم", "در کیسه زباله تر بیندازیم"]},
     "en": {"q": "What should you do with a PET bottle before handing it in?", "a": ["Rinse and crush it", "Close it tight with the cap", "Put it in the wet-waste bag"]}, "ok": 0},
    {"id": "pizza", "pts": 40, "fa": {"q": "جعبه پیتزای چرب قابل بازیافت است؟", "a": ["بله، همیشه", "نه، بخش چرب آن نه", "فقط اگر سفید باشد"]},
     "en": {"q": "Is a greasy pizza box recyclable?", "a": ["Yes, always", "No, not the greasy part", "Only if it's white"]}, "ok": 1},
    {"id": "battery", "pts": 60, "fa": {"q": "باتری‌های مصرف‌شده را کجا تحویل دهیم؟", "a": ["همراه پسماند خشک", "در مخزن پسماند الکترونیکی", "در سطل زباله معمولی"]},
     "en": {"q": "Where do used batteries go?", "a": ["With dry waste", "In the e-waste bin", "In the regular trash"]}, "ok": 1},
    {"id": "glass", "pts": 50, "fa": {"q": "کدام شیشه در بازیافت شیشه پذیرفته نمی‌شود؟", "a": ["شیشه مربا", "بطری نوشابه", "آینه و شیشه پنجره"]},
     "en": {"q": "Which glass is NOT accepted in glass recycling?", "a": ["Jam jar", "Soda bottle", "Mirrors and window glass"]}, "ok": 2},
]

DISTRICTS = [("d6", "منطقه ۶", "District 6", 48210), ("d3", "منطقه ۳", "District 3", 45120), ("d2", "منطقه ۲", "District 2", 39870),
             ("d1", "منطقه ۱", "District 1", 36540), ("d5", "منطقه ۵", "District 5", 30110), ("d22", "منطقه ۲۲", "District 22", 24380)]
USER_DISTRICT = "d6"


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(db()) as con, con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS pickups(id INTEGER PRIMARY KEY, created TEXT, day TEXT, slot TEXT, address TEXT,
            items TEXT, status TEXT, est INTEGER, points INTEGER DEFAULT 0, weight REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS txns(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, ref TEXT, points INTEGER);
        CREATE TABLE IF NOT EXISTS missions_done(id TEXT PRIMARY KEY, ts TEXT);
        """)
        if con.execute("SELECT COUNT(*) FROM pickups").fetchone()[0]:
            return
        # seed a believable history
        today = date.today()
        for i, (ago, items) in enumerate([(62, {"paper": 6, "plastic": 3}), (41, {"plastic": 4, "metal": 1.5}),
                                          (23, {"paper": 8, "glass": 5}), (9, {"plastic": 5, "metal": 2, "paper": 4})]):
            d = (today - timedelta(days=ago)).isoformat()
            pts = estimate(items)
            con.execute("INSERT INTO pickups(created,day,slot,address,items,status,est,points,weight) VALUES(?,?,?,?,?,?,?,?,?)",
                        (d, d, SLOTS[i % 4], "تهران، یوسف‌آباد، خیابان ۳۳", json.dumps(items), "delivered", pts, pts, sum(items.values())))
            con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (d + "T12:00:00", "pickup", str(i + 1), pts))
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", ((today - timedelta(days=30)).isoformat() + "T18:00:00", "redeem", "coffee", -450))
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", ((today - timedelta(days=15)).isoformat() + "T09:30:00", "mission", "pet", 40))
        con.execute("INSERT INTO missions_done VALUES('pet', ?)", (today.isoformat(),))


def estimate(items: dict) -> int:
    return round(sum(MATERIALS[m]["pts"] * kg for m, kg in items.items()))


app = FastAPI(title="SabzBank API")
init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/catalog")
def catalog():
    with closing(db()) as con:
        done = {r["id"] for r in con.execute("SELECT id FROM missions_done")}
    missions = [{k: v for k, v in m.items() if k != "ok"} | {"done": m["id"] in done} for m in MISSIONS]
    return {"materials": MATERIALS, "slots": SLOTS, "rewards": REWARDS, "missions": missions}


@app.get("/api/state")
def state():
    with closing(db()) as con:
        balance = con.execute("SELECT COALESCE(SUM(points),0) FROM txns").fetchone()[0]
        lifetime = con.execute("SELECT COALESCE(SUM(points),0) FROM txns WHERE points>0").fetchone()[0]
        kg, co2, paper = 0.0, 0.0, 0.0
        for r in con.execute("SELECT items FROM pickups WHERE status='delivered'"):
            for m, w in json.loads(r["items"]).items():
                kg += w
                co2 += w * MATERIALS[m]["co2"]
                paper += w if m == "paper" else 0
        upcoming = con.execute("SELECT * FROM pickups WHERE status='scheduled' ORDER BY day LIMIT 1").fetchone()
    tier = max((t for t in TIERS if lifetime >= t[1]), key=lambda t: t[1])
    nxt = next((t for t in TIERS if t[1] > lifetime), None)
    return {
        "name": {"fa": "نیلوفر", "en": "Niloufar"},
        "balance": balance, "lifetime": lifetime,
        "tier": tier[0], "tierFloor": tier[1], "next": nxt and {"tier": nxt[0], "at": nxt[1]},
        # ~17 trees per ton of paper; landfill volume ~ 1.8 L per kg of dry waste
        "impact": {"kg": round(kg, 1), "co2": round(co2, 1), "trees": round(paper * 0.017, 2), "landfill": round(kg * 1.8)},
        "upcoming": upcoming and pickup_row(upcoming),
    }


def pickup_row(r):
    return dict(r) | {"items": json.loads(r["items"])}


@app.get("/api/pickups")
def pickups():
    with closing(db()) as con:
        return [pickup_row(r) for r in con.execute("SELECT * FROM pickups ORDER BY day DESC, id DESC")]


class PickupIn(BaseModel):
    items: dict[Literal["paper", "plastic", "metal", "glass", "ewaste"], float] = Field(min_length=1)
    day: date
    slot: Literal["08-11", "11-14", "14-17", "17-20"]
    address: str = Field(min_length=3, max_length=200)


@app.post("/api/pickups", status_code=201)
def create_pickup(p: PickupIn):
    if not all(0.5 <= kg <= 100 for kg in p.items.values()):
        raise HTTPException(422, "each item must be 0.5–100 kg")
    if not date.today() <= p.day <= date.today() + timedelta(days=14):
        raise HTTPException(422, "day must be within the next 14 days")
    with closing(db()) as con, con:
        cur = con.execute("INSERT INTO pickups(created,day,slot,address,items,status,est) VALUES(?,?,?,?,?,?,?)",
                          (datetime.now().isoformat(timespec="seconds"), p.day.isoformat(), p.slot, p.address.strip(),
                           json.dumps(p.items), "scheduled", estimate(p.items)))
        return pickup_row(con.execute("SELECT * FROM pickups WHERE id=?", (cur.lastrowid,)).fetchone())


def scheduled(con, pid):
    r = con.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "pickup not found")
    if r["status"] != "scheduled":
        raise HTTPException(409, "pickup is not scheduled")
    return r


@app.post("/api/pickups/{pid}/complete")
def complete_pickup(pid: int):
    """Demo stand-in for the collector app: weighs (±10%) and awards points."""
    with closing(db()) as con, con:
        r = scheduled(con, pid)
        items = {m: round(kg * random.uniform(0.9, 1.1), 1) for m, kg in json.loads(r["items"]).items()}
        pts = estimate(items)
        con.execute("UPDATE pickups SET status='delivered', items=?, points=?, weight=? WHERE id=?",
                    (json.dumps(items), pts, sum(items.values()), pid))
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), "pickup", str(pid), pts))
        return pickup_row(con.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone())


@app.post("/api/pickups/{pid}/cancel")
def cancel_pickup(pid: int):
    with closing(db()) as con, con:
        scheduled(con, pid)
        con.execute("UPDATE pickups SET status='canceled' WHERE id=?", (pid,))
    return {"ok": True}


@app.post("/api/rewards/{rid}/redeem")
def redeem(rid: str):
    reward = next((r for r in REWARDS if r["id"] == rid), None)
    if not reward:
        raise HTTPException(404, "reward not found")
    with closing(db()) as con, con:
        # ponytail: single-user demo, so no race between balance check and insert
        if con.execute("SELECT COALESCE(SUM(points),0) FROM txns").fetchone()[0] < reward["cost"]:
            raise HTTPException(409, "insufficient points")
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), "redeem", rid, -reward["cost"]))
    return {"code": "SABZ-" + secrets.token_hex(3).upper()}


class Answer(BaseModel):
    choice: int


@app.post("/api/missions/{mid}/answer")
def answer(mid: str, a: Answer):
    m = next((m for m in MISSIONS if m["id"] == mid), None)
    if not m:
        raise HTTPException(404, "mission not found")
    with closing(db()) as con, con:
        if con.execute("SELECT 1 FROM missions_done WHERE id=?", (mid,)).fetchone():
            raise HTTPException(409, "mission already done")
        correct = a.choice == m["ok"]
        if correct:
            con.execute("INSERT INTO missions_done VALUES(?,?)", (mid, date.today().isoformat()))
            con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (datetime.now().isoformat(timespec="seconds"), "mission", mid, m["pts"]))
    return {"correct": correct, "answer": m["ok"], "points": m["pts"] if correct else 0}


@app.get("/api/transactions")
def transactions():
    with closing(db()) as con:
        return [dict(r) for r in con.execute("SELECT * FROM txns ORDER BY ts DESC, id DESC LIMIT 100")]


@app.get("/api/leaderboard")
def leaderboard():
    lifetime = state()["lifetime"]
    rows = [{"id": i, "fa": fa, "en": en, "points": p + (lifetime if i == USER_DISTRICT else 0), "mine": i == USER_DISTRICT}
            for i, fa, en, p in DISTRICTS]
    return sorted(rows, key=lambda r: -r["points"])


@app.get("/api/city")
def city():
    """Municipality panel. Pilot-scale synthetic baseline (business plan: ~4k t/year, 18k MAU) plus live user data."""
    rng = random.Random(26)
    months = [{"m": i, "tons": round(180 + i * 38 + rng.uniform(-15, 15)), "users": 4200 + i * 1250 + rng.randint(-200, 200)} for i in range(12)]
    s = state()
    tons = sum(m["tons"] for m in months) + s["impact"]["kg"] / 1000
    share = {"paper": 38, "plastic": 31, "glass": 14, "metal": 11, "ewaste": 6}
    return {
        "kpi": {"tons": round(tons), "mau": months[-1]["users"], "participation": 23.4, "landfillSaved": round(tons * 0.45),
                "co2": round(tons * 1.3), "partners": 80},
        "months": months,
        "materials": [{"id": k, "pct": v} for k, v in share.items()],
        "districts": leaderboard(),
    }
