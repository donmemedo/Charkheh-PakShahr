"""SabzBank API — points for separated dry waste. Single demo user, SQLite storage.

Environment:
  DB_PATH        SQLite file (default data/sabz.db).
  DEMO_MODE      "1" turns the demo conveniences on: the citizen client may call
                 POST /api/pickups/{id}/complete (stand-in for the collector app) for any day, /docs is served,
                 and an empty database gets a sample history. Off unless set, so a deploy that forgets it fails closed.
  COLLECTOR_KEY  shared secret the collector app sends as X-Collector-Key to complete a pickup when DEMO_MODE is off.
  PARTNER_KEY    shared secret a partner sends as X-Partner-Key to look up or spend a reward code.
                 Both take a comma list ("new,old") so a key rotates without downtime. Each key needs 32+ chars with
                 10+ distinct ones, or startup stops. Unset means every call gets the same 403 as a wrong key; the
                 log line (event=auth_fail reason=unconfigured) tells the operator why.
  TRUST_PROXY    "1" only behind an edge proxy (nginx, Caddy) that sets or appends X-Forwarded-For;
                 rate limits then key on its rightmost entry. Next.js passes a client-sent
                 X-Forwarded-For through unchanged, so never enable this without an edge proxy.
                 Run uvicorn with --no-proxy-headers: by default it trusts X-Forwarded-For from 127.0.0.1.
"""
import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import random
import re
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, closing, suppress
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator

DB_PATH = os.getenv("DB_PATH", "data/sabz.db")
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"  # fails closed


def env_keys(name: str) -> tuple[bytes, ...]:
    """Shared secrets from a comma list ("new,old" while rotating); empty when unset. Startup stops on a weak key."""
    keys = [k.strip() for k in os.getenv(name, "").split(",") if k.strip()]
    for k in keys:
        if len(k) < 32 or len(set(k)) < 10:
            raise SystemExit(f"{name}: every key needs 32+ chars and 10+ distinct chars. Make one with "
                             "python -c 'import secrets; print(secrets.token_urlsafe(32))'")
    return tuple(k.encode() for k in keys)


COLLECTOR_KEYS = env_keys("COLLECTOR_KEY")
PARTNER_KEYS = env_keys("PARTNER_KEY")
TRUST_PROXY = os.getenv("TRUST_PROXY") == "1"
TZ = timezone(timedelta(hours=3, minutes=30))  # Asia/Tehran: Iran has had no DST since 2022, so the fixed offset is exact
MAX_BODY = 16 * 1024          # bytes; the largest legitimate request is a few hundred bytes
BURST, REFILL = 10, 30 / 60   # rate limit per client for POSTs and the code lookup: burst 10, then 30 per minute
READ_BURST, READ_REFILL = 60, 2.0  # other GETs, own bucket: a page load is ~6 requests, a read flood still cannot pin the CPU
PICKUPS_PER_DAY = 5           # farming cap for the single demo user
MAX_PICKUP_KG = 50            # total declared kg per pickup: complete pays for the declared items (+-10%), so this caps one mint
OVERDUE_DAYS = 7              # a scheduled pickup more than this many days past its day is a missed collection: canceled
MIN_FREE_MB = 50              # /api/health turns red below this much free space on the data volume

log = logging.getLogger("sabz")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def fp(value: str | bytes, n: int) -> str:
    """Short sha256 fingerprint, so a log line can name a reward code or a key without holding it."""
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8", "replace")).hexdigest()[:n]


def audit(event: str, request: Request | None = None, level: int = logging.INFO, **fields):
    """One key=value line per business or security event, with the request id when there is a request. Values are
    URL-quoted, so none can forge a field or a line. Never pass a key, an address or a full reward code: use fp()."""
    rid = request.scope.get("rid", "-") if request else "-"
    log.log(level, "%s", " ".join([f"event={event}", f"rid={rid}"] + [f"{k}={quote(str(v), safe='/:,.#|')}" for k, v in fields.items()]))

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


def today() -> date:
    return datetime.now(TZ).date()


def ts() -> str:
    return datetime.now(TZ).replace(tzinfo=None).isoformat(timespec="seconds")


def db():
    # IMMEDIATE: a write transaction takes the lock on its first statement, so two writers queue instead of racing
    # (for up to connect()'s default timeout of 5 s, which is SQLite's busy timeout)
    con = sqlite3.connect(DB_PATH, isolation_level="IMMEDIATE")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA synchronous=FULL")  # with WAL: every commit (a redeem, a code_use) survives power loss; ~2.5 ms a write
    return con


# Schema ladder: PRAGMA user_version counts the steps applied. Append a step; never edit a shipped one.
# Table rebuilds for CHECK and FOREIGN KEY constraints (SQLite cannot ALTER them in) belong to the future user_id migration.
MIGRATIONS = [
    # V1: the schema from before versioning. IF NOT EXISTS lets an unversioned (version 0) database adopt it in place.
    """
        CREATE TABLE IF NOT EXISTS pickups(id INTEGER PRIMARY KEY, created TEXT, day TEXT, slot TEXT, address TEXT,
            items TEXT, status TEXT, est INTEGER, points INTEGER DEFAULT 0, weight REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS txns(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, ref TEXT, points INTEGER);
        CREATE TABLE IF NOT EXISTS missions_done(id TEXT PRIMARY KEY, ts TEXT);
        CREATE TABLE IF NOT EXISTS codes(code TEXT PRIMARY KEY, rid TEXT, ts TEXT, used TEXT);
        CREATE INDEX IF NOT EXISTS pickups_status_day ON pickups(status, day);
        CREATE INDEX IF NOT EXISTS pickups_day_id ON pickups(day, id);
        CREATE INDEX IF NOT EXISTS txns_ts_id ON txns(ts, id);
    """,
    # V2: award-once in the database, a backstop for the status and INSERT OR IGNORE predicates in the handlers
    "CREATE UNIQUE INDEX txns_once ON txns(kind, ref) WHERE kind IN ('pickup', 'mission');",
]


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    # autocommit=True: executescript then keeps our BEGIN open, so a step commits together with its version or not at all
    with closing(sqlite3.connect(DB_PATH, autocommit=True)) as con:
        con.execute("PRAGMA journal_mode=WAL")
        for version, script in enumerate(MIGRATIONS, 1):
            con.execute("BEGIN IMMEDIATE")  # the version is read under the write lock: two starting workers cannot both apply a step
            if con.execute("PRAGMA user_version").fetchone()[0] < version:
                con.executescript(f"{script}\nPRAGMA user_version={version};")
            con.execute("COMMIT")  # a failing step raises before this, and close() rolls it back
        if DEMO_MODE:
            con.execute("BEGIN IMMEDIATE")
            seed(con)
            con.execute("COMMIT")


def seed(con):
    """Demo only: a believable history, once, into an empty database. A production database starts empty, at zero points."""
    if con.execute("SELECT 1 FROM pickups LIMIT 1").fetchone():
        return
    now = today()
    for i, (ago, items) in enumerate([(62, {"paper": 6, "plastic": 3}), (41, {"plastic": 4, "metal": 1.5}),
                                      (23, {"paper": 8, "glass": 5}), (9, {"plastic": 5, "metal": 2, "paper": 4})]):
        d = (now - timedelta(days=ago)).isoformat()
        pts = estimate(items)
        cur = con.execute("INSERT INTO pickups(created,day,slot,address,items,status,est,points,weight) VALUES(?,?,?,?,?,?,?,?,?)",
                          (d, d, SLOTS[i % 4], "تهران، یوسف‌آباد، خیابان ۳۳", json.dumps(items), "delivered", pts, pts, sum(items.values())))
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (d + "T12:00:00", "pickup", str(cur.lastrowid), pts))
    con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", ((now - timedelta(days=30)).isoformat() + "T18:00:00", "redeem", "coffee", -450))
    con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", ((now - timedelta(days=15)).isoformat() + "T09:30:00", "mission", "pet", 40))
    con.execute("INSERT INTO missions_done VALUES('pet', ?)", (now.isoformat(),))


def estimate(items: dict) -> int:
    return round(sum(MATERIALS[m]["pts"] * kg for m, kg in items.items()))


def expire_overdue() -> int:
    """Cancel scheduled pickups more than OVERDUE_DAYS past their day (missed collections). Pure DB work: the lifespan
    task runs it at startup and then hourly. Returns how many it canceled."""
    cutoff = (today() - timedelta(days=OVERDUE_DAYS)).isoformat()
    with closing(db()) as con, con:
        n = con.execute("UPDATE pickups SET status='canceled' WHERE status='scheduled' AND day < ?", (cutoff,)).rowcount
    audit("expire_overdue", count=n)
    return n


# ---- request guards -------------------------------------------------------------------------

def client_ip(request: Request) -> str:
    # rightmost entry = the address the trusted edge proxy saw; entries to its left are client-supplied
    if TRUST_PROXY and (xff := request.headers.get("x-forwarded-for")):
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "?"


_buckets: dict[str, tuple[float, float]] = {}  # bucket key -> (tokens, last seen)
_lock = threading.Lock()
_swept = float("-inf")
clock = time.monotonic  # throttle's time source; the tests swap in a fake clock


def bucket_key(ip: str) -> str:
    """IPv6 clients usually hold a whole /64, so one bucket per /64; IPv4 (and IPv4-mapped) per address.
    Anything else (a forged header) is hashed, so a caller cannot make keys of arbitrary size."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "h:" + fp(ip, 16)
    return ip if a.version == 4 or a.ipv4_mapped else str(ipaddress.ip_network((a, 64), strict=False))


def throttle(ip: str, read: bool = False) -> bool:
    """Token bucket per client, with reads in their own larger bucket. The idle sweep runs at most every 10 s,
    so a call stays O(1) amortized.
    ponytail: in-process dict; move to Redis if the API scales out."""
    global _swept
    burst, refill = (READ_BURST, READ_REFILL) if read else (BURST, REFILL)
    key, now = bucket_key(ip) + ("|r" if read else ""), clock()
    with _lock:
        if len(_buckets) > 10_000 and now - _swept > 10:
            _swept = now
            for k in [k for k, (_, last) in _buckets.items() if now - last > 120]:
                del _buckets[k]
        tokens, last = _buckets.get(key, (burst, now))
        tokens = min(burst, tokens + (now - last) * refill)
        ok = tokens >= 1
        _buckets[key] = (tokens - ok, now)
    return ok


def charge(request: Request) -> str | None:
    """Takes one token for this request; returns the Retry-After seconds when the client's bucket is empty.
    POSTs and the code lookup draw on the strict bucket, other GETs on the read bucket. It runs once per routed
    request (from guard, or from the 422 handler when FastAPI rejected the body first), so it also flags a request
    that skipped the edge proxy."""
    request.scope["throttled"] = True
    path = request.scope["path"]  # the routed path, not the Host-derived request.url
    if TRUST_PROXY and path != "/api/health":  # the compose healthcheck is the one legitimate caller that skips the edge
        xff = request.headers.get("x-forwarded-for", "")
        if not xff or "," in xff:  # the Caddy edge always sends exactly one entry
            audit("edge_bypass", request, logging.WARNING, xff_entries=xff.count(",") + 1 if xff else 0)
    read = request.method != "POST" and not path.startswith("/api/codes/")
    return None if throttle(client_ip(request), read) else ("1" if read else "2")  # seconds until one token refills


def guard(request: Request):
    """Every routed request is rate limited (see charge). The JSON content type and the Sec-Fetch-Site check are the
    CSRF defenses: a cross-site <form> cannot send either, so they already hold when cookie auth is added.
    SameSite=Strict on that cookie completes the set. They run before the charge, so a cross-site page cannot drain
    a visitor's bucket."""
    if request.method == "POST":
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "send application/json")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "cross-site request blocked")
    if retry := charge(request):
        raise HTTPException(429, "too many requests", headers={"Retry-After": retry})


def require_key(request: Request, header: str, keys: tuple[bytes, ...]) -> str:
    """Shared-secret check in constant time against every configured key, with no short-circuit, so the timing does not
    tell which key matched. Compares bytes: compare_digest raises on non-ASCII str (a 500). Unset, missing and wrong
    keys all get the same 403, so a scanner cannot tell a half-configured deploy; only the log line says which.
    Returns the presented key's fingerprint for the caller's audit line."""
    presented = request.headers.get(header, "").encode("latin-1")
    ok = False
    for key in keys:
        ok |= secrets.compare_digest(presented, key)
    if not ok:
        reason = "unconfigured" if not keys else "mismatch" if presented else "missing"
        audit("auth_fail", request, logging.WARNING, header=header, reason=reason, fp=fp(presented, 6) if presented else "-")
        raise HTTPException(403, "forbidden")
    return fp(presented, 6)


class BodyLimit:
    """Pure ASGI: 413 when Content-Length or the streamed body exceeds MAX_BODY, before any parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length", b"0")
        if length.isdigit() and int(length) > MAX_BODY:
            return await JSONResponse({"detail": "body too large"}, 413)(scope, receive, send)
        seen = 0

        async def bounded():
            nonlocal seen
            msg = await receive()
            seen += len(msg.get("body", b""))
            if seen > MAX_BODY:
                raise HTTPException(413, "body too large")  # FastAPI re-raises HTTPException from body reads
            return msg

        await self.app(scope, bounded, send)


async def expire_hourly():
    while True:
        try:
            await asyncio.to_thread(expire_overdue)
        except Exception:  # a locked or read-only database must not end the loop; the next hour retries
            log.exception("event=expire_overdue_failed")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app):
    warn = DEMO_MODE or not (COLLECTOR_KEYS and PARTNER_KEYS)
    audit("startup", level=logging.WARNING if warn else logging.INFO, demo=int(DEMO_MODE), trust_proxy=int(TRUST_PROXY),
          collector_key_set=int(bool(COLLECTOR_KEYS)), partner_key_set=int(bool(PARTNER_KEYS)))
    # ponytail: an in-process loop. With several workers each runs it, which is harmless (one idempotent UPDATE).
    task = asyncio.create_task(expire_hourly())  # first run now, then hourly
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="SabzBank API", dependencies=[Depends(guard)], lifespan=lifespan,
              openapi_url="/openapi.json" if DEMO_MODE else None)  # None also drops /docs, /redoc
app.add_middleware(BodyLimit)
# At import, not in the lifespan: the tests and the CPU bench write rows right after import, through a TestClient that
# never enters the lifespan. The ladder and the seed take the write lock first, so several workers can run it at once.
init_db()


@app.exception_handler(RequestValidationError)
async def invalid(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 echoes the rejected input, and NaN, Infinity or a lone surrogate there cannot be
    JSON-encoded (a 500). Location, message and type are enough for the client.
    FastAPI parses a JSON body before it runs dependencies, so a malformed body never reached guard: run it here,
    so such a request is CSRF-checked and costs a token like any other."""
    if not request.scope.get("throttled"):
        try:
            guard(request)
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, e.status_code, headers=e.headers)
    return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]}, 422)


@app.exception_handler(sqlite3.OperationalError)
async def db_unavailable(request: Request, exc: sqlite3.OperationalError):
    """A write lock held past the busy timeout (5 s), or a read-only or full volume: 503 with Retry-After, not a bare 500."""
    msg = str(exc)
    audit("db_busy" if "locked" in msg or "busy" in msg else "db_error", request, logging.ERROR, error=msg[:80])
    return JSONResponse({"detail": "database unavailable, retry shortly"}, 503, headers={"Retry-After": "1"})


def log_path(path: str) -> str:
    """The routed path as logged. A reward code (a bearer secret) becomes code#<sha256[:8]>; the rest is URL-quoted,
    because it arrives percent-decoded and a %0a would forge a second line; the result is cut to 200 chars."""
    path = re.sub(r"^/api/codes/([^/]+)", lambda m: "/api/codes/code#" + fp(m[1], 8), path)
    return quote(path, safe="/#")[:200]


class Observe:
    """Pure ASGI (about 1 ms/request cheaper than @app.middleware): request id, nosniff and no-store
    headers, one access-log line, and a WARNING line for security-relevant statuses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        rid, t0, status = secrets.token_hex(6), time.perf_counter(), 500
        scope["rid"] = rid  # handlers put it on their audit lines

        async def send_with_headers(msg):
            nonlocal status
            if msg["type"] == "http.response.start":
                status = msg["status"]
                msg["headers"] = [*msg.get("headers", []), (b"x-request-id", rid.encode()),
                                  (b"x-content-type-options", b"nosniff"), (b"cache-control", b"no-store")]
            await send(msg)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            # scope["path"] is the routed path (request.url is rebuilt from the Host header and can disagree)
            level = log.error if status >= 500 else log.warning if status in (403, 409, 413, 415, 429) else log.info
            level("%s %s %s %d %.1fms ip=%s", rid, scope["method"], log_path(scope["path"]), status,
                  (time.perf_counter() - t0) * 1000, quote(client_ip(Request(scope)), safe=":.")[:64])


app.add_middleware(Observe)  # added last = outermost, so BodyLimit's 413s are logged too


# ---- routes ---------------------------------------------------------------------------------

Pid = Annotated[int, Path(ge=1, le=2**63 - 1)]  # out-of-range ids are a 422, not an sqlite OverflowError


@app.get("/api/health")
def health():
    """Readiness, kept cheap: the database takes a write (rolled back) and the data volume has room; 503 otherwise, so
    the compose healthcheck turns red on a read-only or full volume. mode=rw never creates a missing database."""
    try:
        with closing(sqlite3.connect(f"file:{quote(DB_PATH)}?mode=rw", uri=True, timeout=1, isolation_level=None)) as con:
            con.execute("BEGIN IMMEDIATE")
            # BEGIN IMMEDIATE alone passes on a read-only file whose WAL is open; rewriting the header proves the write
            con.execute(f"PRAGMA user_version={con.execute('PRAGMA user_version').fetchone()[0]:d}")
            con.execute("ROLLBACK")
    except sqlite3.Error as e:
        return JSONResponse({"ok": False, "reason": "db_busy" if "locked" in str(e) else "db_unwritable"}, 503)
    if shutil.disk_usage(os.path.dirname(os.path.abspath(DB_PATH))).free < MIN_FREE_MB * 2**20:
        return JSONResponse({"ok": False, "reason": "disk_low"}, 503)
    return {"ok": True}


@app.get("/api/catalog")
def catalog():
    # ponytail: one tiny SELECT; the static part is cached client-side, so no server cache
    with closing(db()) as con:
        done = {r["id"] for r in con.execute("SELECT id FROM missions_done")}
    missions = [{k: v for k, v in m.items() if k != "ok"} | {"done": m["id"] in done} for m in MISSIONS]
    return {"materials": MATERIALS, "slots": SLOTS, "rewards": REWARDS, "missions": missions, "demo": DEMO_MODE}


@app.get("/api/state")
def state():
    with closing(db()) as con:
        con.execute("BEGIN")  # one read snapshot: balance, impact and upcoming agree even while a complete commits
        balance, lifetime = con.execute(
            "SELECT COALESCE(SUM(points),0), COALESCE(SUM(CASE WHEN points>0 THEN points END),0) FROM txns").fetchone()
        kg, co2, paper = 0.0, 0.0, 0.0
        for m, w in con.execute("SELECT key, SUM(value) FROM pickups, json_each(pickups.items) WHERE status='delivered' GROUP BY key"):
            kg += w
            co2 += w * MATERIALS[m]["co2"]
            paper += w if m == "paper" else 0
        # overdue ones (day < today) wait for expire_overdue and must not hide the real next pickup
        upcoming = con.execute("SELECT * FROM pickups WHERE status='scheduled' AND day >= ? ORDER BY day, slot, id LIMIT 1",
                               (today().isoformat(),)).fetchone()
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
def pickups(limit: int = Query(50, ge=1, le=200), before: int | None = Query(None, ge=1, le=2**63 - 1)):
    """Newest first. `before` is the id of the last row you have (keyset cursor on day, id)."""
    with closing(db()) as con:
        rows = con.execute("SELECT * FROM pickups WHERE ? IS NULL OR (day, id) < (SELECT day, id FROM pickups WHERE id=?) "
                           "ORDER BY day DESC, id DESC LIMIT ?", (before, before, limit))
        return [pickup_row(r) for r in rows]


class PickupIn(BaseModel):
    items: dict[Literal["paper", "plastic", "metal", "glass", "ewaste"], Annotated[float, Field(ge=0.5, le=MAX_PICKUP_KG)]] = Field(min_length=1)
    day: date
    slot: Literal["08-11", "11-14", "14-17", "17-20"]
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]

    @field_validator("items")
    @classmethod
    def total_cap(cls, items: dict) -> dict:
        if round(sum(items.values()), 3) > MAX_PICKUP_KG:  # rounded: 10.1 + 19.9 + 20 must not fail on float error
            raise ValueError(f"at most {MAX_PICKUP_KG} kg per pickup")
        return items


@app.post("/api/pickups", status_code=201)
def create_pickup(p: PickupIn, request: Request):
    if not today() <= p.day <= today() + timedelta(days=14):
        raise HTTPException(422, "day must be within the next 14 days")
    with closing(db()) as con, con:
        con.execute("BEGIN IMMEDIATE")  # take the write lock before counting, so concurrent creates cannot overshoot the cap
        if con.execute("SELECT COUNT(*) FROM pickups WHERE created >= ?", (today().isoformat(),)).fetchone()[0] >= PICKUPS_PER_DAY:
            raise HTTPException(409, f"at most {PICKUPS_PER_DAY} pickups per day")
        cur = con.execute("INSERT INTO pickups(created,day,slot,address,items,status,est) VALUES(?,?,?,?,?,?,?)",
                          (ts(), p.day.isoformat(), p.slot, p.address, json.dumps(p.items), "scheduled", estimate(p.items)))
        row = con.execute("SELECT * FROM pickups WHERE id=?", (cur.lastrowid,)).fetchone()
    audit("create_pickup", request, pid=row["id"], kg=round(sum(p.items.values()), 1), est=row["est"])
    return pickup_row(row)


@app.post("/api/pickups/{pid}/complete")
def complete_pickup(pid: Pid, request: Request):
    """Collector action: weighs (±10%) and awards points. The citizen client may call it only in DEMO_MODE, which also
    allows any day; the collector key cannot complete a pickup whose day is still ahead."""
    key = "-" if DEMO_MODE else require_key(request, "x-collector-key", COLLECTOR_KEYS)
    with closing(db()) as con, con:
        r = con.execute("SELECT items, day FROM pickups WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "pickup not found")
        if not DEMO_MODE and r["day"] > today().isoformat():
            raise HTTPException(409, "pickup day is still ahead")
        items = {m: round(kg * random.uniform(0.9, 1.1), 1) for m, kg in json.loads(r["items"]).items()}
        pts = estimate(items)
        # the status predicate makes the transition atomic: a concurrent second call updates 0 rows
        if not con.execute("UPDATE pickups SET status='delivered', items=?, points=?, weight=? WHERE id=? AND status='scheduled'",
                           (json.dumps(items), pts, sum(items.values()), pid)).rowcount:
            raise HTTPException(409, "pickup is not scheduled")
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (ts(), "pickup", str(pid), pts))
        row = con.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone()
    audit("complete", request, pid=pid, points=pts, kg=round(row["weight"], 1), key=key)
    return pickup_row(row)


@app.post("/api/pickups/{pid}/cancel")
def cancel_pickup(pid: Pid, request: Request):
    with closing(db()) as con, con:
        if not con.execute("UPDATE pickups SET status='canceled' WHERE id=? AND status='scheduled'", (pid,)).rowcount:
            raise HTTPException(409, "pickup is not scheduled") if con.execute("SELECT 1 FROM pickups WHERE id=?", (pid,)).fetchone() \
                else HTTPException(404, "pickup not found")
    audit("cancel", request, pid=pid)
    return {"ok": True}


@app.post("/api/rewards/{rid}/redeem")
def redeem(rid: str, request: Request):
    reward = next((r for r in REWARDS if r["id"] == rid), None)
    if not reward:
        raise HTTPException(404, "reward not found")
    code = "SABZ-" + secrets.token_urlsafe(9)
    with closing(db()) as con, con:
        # balance check and debit in ONE statement, so concurrent redeems cannot both pass the check
        if not con.execute("INSERT INTO txns(ts,kind,ref,points) SELECT ?,?,?,? WHERE (SELECT COALESCE(SUM(points),0) FROM txns) >= ?",
                           (ts(), "redeem", rid, -reward["cost"], reward["cost"])).rowcount:
            raise HTTPException(409, "insufficient points")
        con.execute("INSERT INTO codes(code,rid,ts) VALUES(?,?,?)", (code, rid, ts()))
        # ponytail: a second SUM, only for the audit line (~1.5 ms at 10k txns). Fold it into one SUM under an explicit
        # BEGIN IMMEDIATE if redeem volume ever matters.
        balance = con.execute("SELECT COALESCE(SUM(points),0) FROM txns").fetchone()[0]
    audit("redeem", request, reward=rid, code=fp(code, 8), balance=balance)
    return {"code": code}


@app.get("/api/codes/{code}")
def code_lookup(code: Annotated[str, Path(max_length=40)], request: Request):
    """Partner-side check (X-Partner-Key) of a redeemed code. `used` is set once a partner spends it via POST .../use."""
    require_key(request, "x-partner-key", PARTNER_KEYS)
    with closing(db()) as con:
        r = con.execute("SELECT rid, ts, used FROM codes WHERE code=?", (code,)).fetchone()
    if not r:
        raise HTTPException(404, "code not found")
    return dict(r)


@app.post("/api/codes/{code}/use")
def code_use(code: Annotated[str, Path(max_length=40)], request: Request):
    """Partner action (X-Partner-Key): spends a redeemed code. The used-is-null predicate makes it single-use."""
    key = require_key(request, "x-partner-key", PARTNER_KEYS)
    with closing(db()) as con, con:
        if not con.execute("UPDATE codes SET used=? WHERE code=? AND used IS NULL", (ts(), code)).rowcount:
            raise HTTPException(409, "code already used") if con.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone() \
                else HTTPException(404, "code not found")
    audit("code_use", request, code=fp(code, 8), key=key)
    return {"ok": True}


class Answer(BaseModel):
    choice: int = Field(ge=0, le=9)


@app.post("/api/missions/{mid}/answer")
def answer(mid: str, a: Answer, request: Request):
    m = next((m for m in MISSIONS if m["id"] == mid), None)
    if not m:
        raise HTTPException(404, "mission not found")
    if a.choice >= len(m["en"]["a"]):
        raise HTTPException(422, "choice is not an option of this mission")
    with closing(db()) as con, con:
        if a.choice != m["ok"]:
            if con.execute("SELECT 1 FROM missions_done WHERE id=?", (mid,)).fetchone():
                raise HTTPException(409, "mission already done")
            return {"correct": False, "points": 0}  # no answer key on a miss
        # INSERT OR IGNORE + rowcount: the losing side of a double submit gets 409, not a 500
        if not con.execute("INSERT OR IGNORE INTO missions_done VALUES(?,?)", (mid, today().isoformat())).rowcount:
            raise HTTPException(409, "mission already done")
        con.execute("INSERT INTO txns(ts,kind,ref,points) VALUES(?,?,?,?)", (ts(), "mission", mid, m["pts"]))
    audit("mission_correct", request, mission=mid, points=m["pts"])
    return {"correct": True, "answer": m["ok"], "points": m["pts"]}


@app.get("/api/transactions")
def transactions():
    with closing(db()) as con:
        return [dict(r) for r in con.execute("SELECT * FROM txns ORDER BY ts DESC, id DESC LIMIT 100")]


def ranking(lifetime: int):
    rows = [{"id": i, "fa": fa, "en": en, "points": p + (lifetime if i == USER_DISTRICT else 0), "mine": i == USER_DISTRICT}
            for i, fa, en, p in DISTRICTS]
    return sorted(rows, key=lambda r: -r["points"])


@app.get("/api/leaderboard")
def leaderboard():
    return ranking(state()["lifetime"])


@app.get("/api/city")
def city():
    """Municipality panel. Synthetic pilot-scale sample data plus the live user's delivered weight."""
    rng = random.Random(26)
    months = [{"m": i, "tons": round(180 + i * 38 + rng.uniform(-15, 15)), "users": 4200 + i * 1250 + rng.randint(-200, 200)} for i in range(12)]
    s = state()  # computed once; ranking() reuses it
    tons = sum(m["tons"] for m in months) + s["impact"]["kg"] / 1000
    share = {"paper": 38, "plastic": 31, "glass": 14, "metal": 11, "ewaste": 6}
    return {
        "kpi": {"tons": round(tons), "mau": months[-1]["users"], "participation": 23.4, "landfillSaved": round(tons * 0.45),
                "co2": round(tons * 1.3), "partners": 80},
        "months": months,
        "materials": [{"id": k, "pct": v} for k, v in share.items()],
        "districts": ranking(s["lifetime"]),
    }
