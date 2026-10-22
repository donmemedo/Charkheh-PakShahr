"""Backend regression suite, dependency-free: `python test_api.py` prints ok, or every failure, and exits 1.

Each @section starts from a fresh database and default settings (see fresh), so sections pass in any order;
TEST_SHUFFLE=<seed> runs them shuffled, TEST_ONLY=a,b runs only those. Rate limits run with refill off or on a fake clock, the weighing jitter is
seeded, and "today" is read when used, never at import.
"""
import hashlib
import logging
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

TMP = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(TMP, "import.db")
os.environ["DEMO_MODE"] = "1"
for name in ("COLLECTOR_KEY", "PARTNER_KEY", "TRUST_PROXY"):
    os.environ.pop(name, None)
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import ops  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CK = "collector-0123456789-abcdefghij-KLMNOP"  # test keys: 32+ chars, 10+ distinct
PK = "partner-0123456789-abcdefghij-QRSTUVW"
J = {"content-type": "application/json"}
c = TestClient(main.app)
for handler in logging.getLogger().handlers:  # a quiet console; sections capture main.log themselves
    handler.setLevel(logging.CRITICAL)
DEFAULTS = {k: getattr(main, k) for k in ("DEMO_MODE", "TRUST_PROXY", "COLLECTOR_KEYS", "PARTNER_KEYS", "BURST", "REFILL",
                                          "READ_BURST", "READ_REFILL", "PICKUPS_PER_DAY", "clock", "db", "today", "ts")}
SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh(demo=True):
    """A new database and default settings, with the rate limits and the daily cap lifted; a section re-tightens them."""
    for k, v in DEFAULTS.items():
        setattr(main, k, v)
    main.DEMO_MODE = demo
    main.BURST = main.READ_BURST = main.PICKUPS_PER_DAY = 10**6
    main._buckets.clear()
    main._swept = float("-inf")
    main.DB_PATH = ops.DB_PATH = os.path.join(tempfile.mkdtemp(dir=TMP), "t.db")
    random.seed(7)  # complete's weighing jitter
    main.init_db()


# ---- helpers ------------------------------------------------------------------------------------------------

def day(offset=0):
    return (main.today() + timedelta(days=offset)).isoformat()


def pk(**o):
    return {"items": {"plastic": 2}, "day": day(), "slot": "08-11", "address": "Tehran"} | o


def post(path, body=None, headers=J, **kw):
    return c.post(path, json={} if body is None else body, headers=headers, **kw)


def new_pickup(**o):
    r = post("/api/pickups", pk(**o))
    assert r.status_code == 201, r.text
    return r.json()


def balance():
    return c.get("/api/state").json()["balance"]


def sql(query, *args):
    with closing(sqlite3.connect(main.DB_PATH)) as con, con:
        return con.execute(query, args).fetchall()


def set_balance(n):
    """Balance exactly n, through an adjustment row: reward costs are multiples of 50 and the seed balance is not."""
    sql("INSERT INTO txns(ts,kind,ref,points) VALUES('2000-01-01T00:00:00','adjust','test',?)", n - balance())


def insert_pickup(day_, status="scheduled"):
    """A pickup the API refuses to create (a past day), straight into the table."""
    with closing(sqlite3.connect(main.DB_PATH)) as con, con:
        return con.execute("INSERT INTO pickups(created,day,slot,address,items,status,est) VALUES(?,?,'08-11','Tehran',"
                           "'{\"plastic\": 2}',?,240)", (day_, day_, status)).lastrowid


def status_of(pid):
    return sql("SELECT status FROM pickups WHERE id=?", pid)[0][0]


def fanout(fn, n=8):
    with ThreadPoolExecutor(n) as ex:
        return sorted(r.status_code for r in ex.map(lambda i: fn(i), range(n)))


def sha(s, n):
    return hashlib.sha256(s.encode()).hexdigest()[:n]


@contextmanager
def logs():
    """main's log lines as (level, message); ops logs under the same logger."""
    lines = []
    h = logging.Handler()
    h.emit = lambda r: lines.append((r.levelno, r.getMessage()))
    main.log.addHandler(h)
    try:
        yield lines
    finally:
        main.log.removeHandler(h)


def events(lines, name):
    return [m for _, m in lines if m.startswith(f"event={name} ")]


@contextmanager
def patched(obj, **attrs):
    old = {k: getattr(obj, k) for k in attrs}
    for k, v in attrs.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


# ---- pickups ------------------------------------------------------------------------------------------------

@section
def smoke_flow():
    bal = balance()
    p = new_pickup()
    assert p["est"] == 240 and p["status"] == "scheduled"
    done = post(f"/api/pickups/{p['id']}/complete").json()
    assert done["status"] == "delivered" and balance() == bal + done["points"]
    code = post("/api/rewards/cinema/redeem").json()["code"]
    assert code.startswith("SABZ-") and len(code) >= 16 and balance() == bal + done["points"] - 1200
    assert c.get("/api/city").json()["kpi"]["tons"] > 0
    assert c.get("/api/catalog").json()["demo"] is True and c.get("/docs").status_code == 200  # demo keeps the docs


@section
def kg_bounds():
    """0.5 to MAX_PICKUP_KG kg per material and at most MAX_PICKUP_KG in total: the most one complete can pay for."""
    assert main.MAX_PICKUP_KG == 50

    def st(items):
        return post("/api/pickups", pk(items=items)).status_code

    assert post("/api/pickups", pk(items={"glass": 0.5})).json()["est"] == 25
    assert [st({"glass": 0.49}), st({"glass": 0}), st({}), st({"wood": 1})] == [422] * 4
    assert post("/api/pickups", pk(items={"ewaste": 50})).json()["est"] == 15000
    assert [st({"ewaste": 50.01}), st({"ewaste": 100}), st({"ewaste": 100.01})] == [422] * 3
    assert st({"paper": 25, "plastic": 25}) == 201 and st({"paper": 10.1, "plastic": 19.9, "metal": 20}) == 201
    r = post("/api/pickups", pk(items={"paper": 25, "plastic": 25.01}))
    assert r.status_code == 422 and "50 kg" in r.json()["detail"][0]["msg"], r.text
    for raw in (b'{"items": {"plastic": NaN}}', b'{"items": {"plastic": Infinity}}'):  # 422, not a 500 from echoing it
        assert c.post("/api/pickups", content=raw, headers=J).status_code == 422


@section
def day_window():
    def st(d):
        return post("/api/pickups", pk(day=d)).status_code

    assert [st(day(-1)), st(day(0)), st(day(14)), st(day(15)), st("2026-02-30")] == [422, 201, 201, 422, 422]


@section
def address_length():
    def st(a):
        return post("/api/pickups", pk(address=a)).status_code

    assert [st("ab"), st("  ab  "), st("   "), st("abc"), st("a" * 200), st("a" * 201)] == [422, 422, 422, 201, 201, 422]
    assert post("/api/pickups", pk(address="   abc   ")).json()["address"] == "abc"  # stripped before the length check


@section
def daily_cap():
    main.PICKUPS_PER_DAY = DEFAULTS["PICKUPS_PER_DAY"]
    for _ in range(main.PICKUPS_PER_DAY):
        new_pickup()
    assert post("/api/pickups", pk()).status_code == 409
    sql("UPDATE pickups SET created = '2000-01-01'")  # a fresh day's budget, without recycling ids
    codes = fanout(lambda _: post("/api/pickups", pk()))
    assert codes == [201] * main.PICKUPS_PER_DAY + [409] * (8 - main.PICKUPS_PER_DAY), codes


@section
def daily_cap_resets_at_tehran_midnight():
    fresh(demo=False)  # no sample rows to count
    main.PICKUPS_PER_DAY = DEFAULTS["PICKUPS_PER_DAY"]
    d = date(2026, 10, 16)
    main.today, main.ts = (lambda: d), (lambda: f"{d}T23:59:59")
    for _ in range(main.PICKUPS_PER_DAY):
        new_pickup()
    assert post("/api/pickups", pk()).status_code == 409
    main.today, main.ts = (lambda: d + timedelta(days=1)), (lambda: f"{d + timedelta(days=1)}T00:00:00")
    assert post("/api/pickups", pk()).status_code == 201
    assert post("/api/pickups", pk(day=d.isoformat())).status_code == 422  # yesterday is now in the past


@section
def complete_payout():
    """Points equal the estimate of the weighed items, and each item weighs within ±10% of its declaration."""
    for declared in ({"plastic": 1}, {"paper": 2.5, "metal": 0.5}, {"glass": 50}, {"ewaste": 12.3, "paper": 7}):
        p = new_pickup(items=declared)
        done = post(f"/api/pickups/{p['id']}/complete").json()
        assert done["points"] == main.estimate(done["items"]) and done["items"].keys() == declared.keys(), done
        for m, kg in declared.items():
            assert kg * 0.9 - 0.05 <= done["items"][m] <= kg * 1.1 + 0.05, (m, kg, done["items"])
        assert abs(done["weight"] - sum(done["items"].values())) < 1e-9
        assert sql("SELECT points FROM txns WHERE kind='pickup' AND ref=?", str(p["id"])) == [(done["points"],)]


@section
def status_action_matrix():
    """complete and cancel work only from scheduled; every other cell is 409, an unknown id 404, and nothing is paid."""
    a, b = new_pickup(), new_pickup()
    assert post(f"/api/pickups/{a['id']}/complete").status_code == 200
    assert post(f"/api/pickups/{b['id']}/cancel").status_code == 200
    bal, txns = balance(), sql("SELECT COUNT(*) FROM txns")
    for pid in (a["id"], b["id"]):
        assert [post(f"/api/pickups/{pid}/{action}").status_code for action in ("complete", "cancel")] == [409, 409]
    assert [post(f"/api/pickups/{2**62}/{action}").status_code for action in ("complete", "cancel")] == [404, 404]
    assert post("/api/pickups/99999999999999999999/complete").status_code == 422  # beyond int64: 422, not a 500
    assert balance() == bal and sql("SELECT COUNT(*) FROM txns") == txns
    assert (status_of(a["id"]), status_of(b["id"])) == ("delivered", "canceled")


@section
def complete_races():
    p = new_pickup()
    codes = fanout(lambda _: post(f"/api/pickups/{p['id']}/complete"))
    assert codes == [200] + [409] * 7, codes  # paid once
    assert len(sql("SELECT 1 FROM txns WHERE kind='pickup' AND ref=?", str(p["id"]))) == 1
    q, bal = new_pickup(), balance()
    codes = fanout(lambda i: post(f"/api/pickups/{q['id']}/{'complete' if i % 2 else 'cancel'}"))
    assert codes == [200] + [409] * 7, codes  # complete racing cancel: one winner, and the ledger matches it
    paid = sql("SELECT points FROM txns WHERE kind='pickup' AND ref=?", str(q["id"]))
    assert (status_of(q["id"]), len(paid)) in (("delivered", 1), ("canceled", 0))
    assert balance() == bal + sum(r[0] for r in paid)


@section
def complete_future_day():
    """The collector key cannot complete a pickup whose day is still ahead; the demo completes any day."""
    assert post(f"/api/pickups/{new_pickup(day=day(3))['id']}/complete").status_code == 200
    main.DEMO_MODE, main.COLLECTOR_KEYS = False, (CK.encode(),)
    key = J | {"x-collector-key": CK}
    ahead, now = new_pickup(day=day(3)), new_pickup()
    r = post(f"/api/pickups/{ahead['id']}/complete", headers=key)
    assert r.status_code == 409 and "ahead" in r.json()["detail"], r.text
    assert post(f"/api/pickups/{now['id']}/complete", headers=key).status_code == 200


@section
def upcoming_pickup():
    """The next pickup is the earliest from today on, by day and then slot; an overdue one never masks it."""
    def upcoming():
        return (c.get("/api/state").json()["upcoming"] or {}).get("id")

    assert upcoming() is None
    insert_pickup(day(-3))  # overdue, not expired yet
    late, early, tomorrow = new_pickup(slot="17-20"), new_pickup(slot="08-11"), new_pickup(day=day(1))
    for nxt in (early, late, tomorrow):
        assert upcoming() == nxt["id"]
        post(f"/api/pickups/{nxt['id']}/cancel")
    assert upcoming() is None


@section
def overdue_expiry():
    """Scheduled pickups more than OVERDUE_DAYS past their day are canceled; nothing else changes."""
    assert main.OVERDUE_DAYS == 7
    old, edge, recent = insert_pickup(day(-8)), insert_pickup(day(-7)), insert_pickup(day(-1))
    paid = insert_pickup(day(-30), status="delivered")
    with logs() as lines:
        assert (main.expire_overdue(), main.expire_overdue()) == (1, 0)
    assert [status_of(p) for p in (old, edge, recent, paid)] == ["canceled", "scheduled", "scheduled", "delivered"]
    assert [m.split()[-1] for m in events(lines, "expire_overdue")] == ["count=1", "count=0"], lines


@section
def lifespan_startup():
    """Startup logs the configuration (WARNING in demo) and runs the overdue sweep once; shutdown stops the loop."""
    old = insert_pickup(day(-9))
    with logs() as lines, TestClient(main.app) as tc:
        assert tc.get("/api/health").status_code == 200
        deadline = time.monotonic() + 60
        while status_of(old) != "canceled" and time.monotonic() < deadline:
            time.sleep(0.05)
    assert status_of(old) == "canceled"
    start = [(lvl, m) for lvl, m in lines if m.startswith("event=startup ")]
    assert len(start) == 1 and start[0][0] == logging.WARNING, start
    assert start[0][1].endswith("demo=1 trust_proxy=0 collector_key_set=0 partner_key_set=0"), start


# ---- points, rewards, codes, missions -----------------------------------------------------------------------

@section
def redeem_at_exact_balance():
    """The debit needs balance >= cost: at cost - 1 nothing is written, at cost the balance lands on 0."""
    set_balance(449)
    before = sql("SELECT (SELECT COUNT(*) FROM txns), (SELECT COUNT(*) FROM codes)")
    assert post("/api/rewards/coffee/redeem").status_code == 409
    assert balance() == 449 and sql("SELECT (SELECT COUNT(*) FROM txns), (SELECT COUNT(*) FROM codes)") == before
    set_balance(450)
    assert post("/api/rewards/coffee/redeem").status_code == 200 and balance() == 0
    set_balance(451)
    assert post("/api/rewards/coffee/redeem").status_code == 200 and balance() == 1
    assert post("/api/rewards/nope/redeem").status_code == 404


@section
def redeem_races():
    """Parallel redeems never overspend: a balance for one cinema ticket pays one, a balance for two pays two."""
    for tickets in (1, 2):
        set_balance(1200 * tickets + 100)
        codes = fanout(lambda _: post("/api/rewards/cinema/redeem"))
        assert codes == [200] * tickets + [409] * (8 - tickets), codes
        assert balance() == 100
    assert len({r[0] for r in sql("SELECT code FROM codes")}) == 3


@section
def tier_edges_and_empty_production_db():
    """A production database starts empty at 0 points. Tiers follow lifetime earnings (positive rows only):
    silver from 2000, gold from 6000, and a redeem never demotes."""
    fresh(demo=False)
    s = c.get("/api/state").json()
    assert (s["balance"], s["lifetime"], s["upcoming"], c.get("/api/pickups").json()) == (0, 0, None, [])

    def tier_at(lifetime):
        sql("DELETE FROM txns")
        sql("INSERT INTO txns(ts,kind,ref,points) VALUES('2000-01-01T00:00:00','adjust','test',?)", lifetime)
        s = c.get("/api/state").json()
        return s["tier"], s["tierFloor"], s["next"]

    assert tier_at(1999) == ("bronze", 0, {"tier": "silver", "at": 2000})
    assert tier_at(2000) == ("silver", 2000, {"tier": "gold", "at": 6000})
    assert tier_at(5999) == ("silver", 2000, {"tier": "gold", "at": 6000})
    assert tier_at(6000) == ("gold", 6000, None)
    assert post("/api/rewards/cinema/redeem").status_code == 200
    s = c.get("/api/state").json()
    assert (s["balance"], s["lifetime"], s["tier"]) == (4800, 6000, "gold")


@section
def demo_seed():
    """Demo mode seeds an empty database, once."""
    s = c.get("/api/state").json()
    assert (s["balance"], s["lifetime"], s["tier"]) == (3420, 3870, "silver"), s
    main.init_db()  # a restart does not seed again
    assert sql("SELECT COUNT(*) FROM pickups") == [(4,)] and balance() == 3420


@section
def code_lookup_and_use():
    """Partners (X-Partner-Key) look a code up and spend it once. Keys compare as bytes: non-ASCII is a 403, not a 500."""
    main.PARTNER_KEYS = (PK.encode(),)
    code, key = post("/api/rewards/cinema/redeem").json()["code"], {"x-partner-key": PK}
    assert c.get(f"/api/codes/{code}").status_code == 403  # the lookup is partner-only too
    r = c.get(f"/api/codes/{code}", headers=key).json()
    assert r["rid"] == "cinema" and r["used"] is None

    def use(code_, k):
        return post(f"/api/codes/{code_}/use", headers=J | {"x-partner-key": k}).status_code

    assert use(code, b"\xe9") == 403 and use(code, "nope") == 403 and use("SABZ-nope", PK) == 404
    assert use(code, PK) == 200 and use(code, PK) == 409 and c.get(f"/api/codes/{code}", headers=key).json()["used"]
    assert c.get("/api/codes/SABZ-nope", headers=key).status_code == 404
    assert [c.get("/api/codes/" + "x" * n, headers=key).status_code for n in (40, 41)] == [404, 422]


@section
def missions():
    assert post("/api/missions/pizza/answer", {"choice": 0}).json() == {"correct": False, "points": 0}  # no answer key
    assert post("/api/missions/pizza/answer", {"choice": 1}).json() == {"correct": True, "answer": 1, "points": 40}
    assert [post("/api/missions/pizza/answer", {"choice": ch}).status_code for ch in (1, 0)] == [409, 409]
    codes = fanout(lambda _: post("/api/missions/battery/answer", {"choice": 1}))
    assert codes == [200] + [409] * 7, codes  # a double submit is a 409, not a 500
    assert post("/api/missions/nope/answer", {"choice": 0}).status_code == 404


@section
def mission_choice_bounds():
    """A choice must be one of the mission's options (glass has 3)."""
    def st(ch):
        return post("/api/missions/glass/answer", {"choice": ch}).status_code

    assert [st(-1), st(3), st(9), st(10), st("x")] == [422] * 5
    assert [st(0), st(2)] == [200, 200]


# ---- keys -----------------------------------------------------------------------------------------------------

@section
def key_failures_are_uniform():
    """Unset, missing and wrong keys all answer 403 {"detail": "forbidden"}; only the log line names the reason."""
    p = new_pickup()
    main.DEMO_MODE = False

    def attempt(headers):
        r = post(f"/api/pickups/{p['id']}/complete", headers=J | headers)
        return r.status_code, r.json()

    with logs() as lines:
        main.COLLECTOR_KEYS = ()
        unset = attempt({"x-collector-key": CK})
        main.COLLECTOR_KEYS = (CK.encode(),)
        missing, wrong = attempt({}), attempt({"x-collector-key": "guess"})
    assert unset == missing == wrong == (403, {"detail": "forbidden"}), (unset, missing, wrong)
    reasons = [m.split(" reason=")[1] for m in events(lines, "auth_fail")]
    assert reasons == [f"unconfigured fp={sha(CK, 6)}", "missing fp=-", f"mismatch fp={sha('guess', 6)}"], reasons
    assert not any(CK in m for _, m in lines)


@section
def key_rotation():
    """A comma list ("new,old") takes both keys, so the collector app rolls over without downtime."""
    new, old = CK, "old-" + CK[::-1]
    os.environ["TEST_ROTATED_KEY"] = f"{new}, {old}"
    try:
        main.COLLECTOR_KEYS = main.env_keys("TEST_ROTATED_KEY")
    finally:
        del os.environ["TEST_ROTATED_KEY"]
    main.DEMO_MODE = False

    def complete_with(k):
        return post(f"/api/pickups/{new_pickup()['id']}/complete", headers=J | {"x-collector-key": k}).status_code

    with logs() as lines:
        assert [complete_with(new), complete_with(old), complete_with(PK)] == [200, 200, 403]
    assert [m.rsplit(" key=", 1)[1] for m in events(lines, "complete")] == [sha(new, 6), sha(old, 6)]  # which key


@section
def weak_keys_stop_startup():
    for bad in ("k" * 32, "abcdefghi" * 4, "short-0123456789", f"{CK},{'k' * 40}"):
        os.environ["TEST_WEAK_KEY"] = bad
        try:
            main.env_keys("TEST_WEAK_KEY")
        except SystemExit as e:
            assert "32+ chars and 10+ distinct" in str(e), e
        else:
            raise AssertionError(f"{bad!r} must stop startup")
        finally:
            del os.environ["TEST_WEAK_KEY"]
    assert main.env_keys("TEST_UNSET_KEY") == ()


PROD = """
import os
from fastapi.testclient import TestClient
import main
c, J = TestClient(main.app), {"content-type": "application/json"}
assert c.get("/api/catalog").json()["demo"] is False  # DEMO_MODE unset fails closed
assert main.app.openapi_url is None and [c.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [404] * 3
s = c.get("/api/state").json()
assert (s["balance"], s["lifetime"], s["upcoming"]) == (0, 0, None), s  # no sample history in production
pickup = {"items": {"plastic": 2}, "day": main.today().isoformat(), "slot": "08-11", "address": "Tehran"}
pid = c.post("/api/pickups", json=pickup, headers=J).json()["id"]
done = lambda h: c.post(f"/api/pickups/{pid}/complete", json={}, headers=J | h).status_code
assert [done({}), done({"x-collector-key": "nope"}), done({"x-collector-key": os.environ["COLLECTOR_KEY"]})] == [403, 403, 200]
for r in (c.post("/api/codes/SABZ-x/use", json={}, headers=J | {"x-partner-key": os.environ["TEST_PK"]}), c.get("/api/codes/SABZ-x")):
    assert (r.status_code, r.json()) == (403, {"detail": "forbidden"}), r.text  # an unset key: the same 403 as a wrong one
print("prod ok")
"""


@section
def production_mode():
    """A fresh process with DEMO_MODE and PARTNER_KEY unset: docs off, no sample history, the collector key gates complete."""
    env = {k: v for k, v in os.environ.items() if k not in ("DEMO_MODE", "PARTNER_KEY")}
    env |= {"DB_PATH": os.path.join(tempfile.mkdtemp(dir=TMP), "p.db"), "COLLECTOR_KEY": CK, "TEST_PK": PK}
    r = subprocess.run([sys.executable, "-c", PROD], capture_output=True, text=True, cwd=HERE, env=env, timeout=600)
    assert r.stdout.strip().endswith("prod ok"), r.stderr[-3000:]


# ---- storage --------------------------------------------------------------------------------------------------

@section
def storage_settings():
    with closing(main.db()) as con:
        assert con.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("PRAGMA user_version").fetchone()[0] == len(main.MIGRATIONS) == 2


@section
def state_reads_one_snapshot():
    seen = []

    def traced():
        con = DEFAULTS["db"]()
        con.set_trace_callback(seen.append)
        return con

    main.db = traced
    c.get("/api/state")
    assert seen[0] == "BEGIN" and [s.split()[0] for s in seen[1:4]] == ["SELECT"] * 3, seen


# The schema of every database created before the migration ladder (user_version 0), written out by hand.
LEGACY = """
CREATE TABLE pickups(id INTEGER PRIMARY KEY, created TEXT, day TEXT, slot TEXT, address TEXT,
    items TEXT, status TEXT, est INTEGER, points INTEGER DEFAULT 0, weight REAL DEFAULT 0);
CREATE TABLE txns(id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, ref TEXT, points INTEGER);
CREATE TABLE missions_done(id TEXT PRIMARY KEY, ts TEXT);
CREATE TABLE codes(code TEXT PRIMARY KEY, rid TEXT, ts TEXT, used TEXT);
CREATE INDEX pickups_status_day ON pickups(status, day);
CREATE INDEX pickups_day_id ON pickups(day, id);
CREATE INDEX txns_ts_id ON txns(ts, id);
INSERT INTO pickups(created,day,slot,address,items,status,est,points,weight)
    VALUES('2026-01-01','2026-01-01','08-11','x','{"paper": 1}','delivered',80,80,1);
INSERT INTO txns(ts,kind,ref,points) VALUES('2026-01-01T12:00:00','pickup','1',80);
"""


def legacy_db(extra="", version=0):
    path = os.path.join(tempfile.mkdtemp(dir=TMP), "legacy.db")
    with closing(sqlite3.connect(path)) as con:
        con.executescript(LEGACY + extra + f"PRAGMA user_version={version};")
    return path


def schema_state(path):
    with closing(sqlite3.connect(path)) as con:
        return (con.execute("PRAGMA user_version").fetchone()[0],
                bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='txns_once'").fetchone()))


@section
def migration_upgrades_in_place():
    """Unversioned and V1 databases upgrade in place without losing a row; a re-run is a no-op; demo mode leaves a
    non-empty database unseeded."""
    for version in (0, 1):
        main.DB_PATH = legacy_db(version=version)
        main.init_db()
        main.init_db()
        assert schema_state(main.DB_PATH) == (2, True)
        assert sql("SELECT COUNT(*) FROM pickups") == [(1,)] and balance() == 80


@section
def migration_step_is_atomic():
    """A legacy double credit stops the V2 step: it rolls back whole (no index, still version 1) and startup fails loudly."""
    main.DB_PATH = legacy_db(extra="INSERT INTO txns(ts,kind,ref,points) VALUES('2026-01-02T12:00:00','pickup','1',80);")
    try:
        main.init_db()
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("a double credit must stop the V2 step")
    assert schema_state(main.DB_PATH) == (1, False)


@section
def award_once_index():
    """The database refuses a second credit for one pickup or mission (V2); redeems repeat freely."""
    for kind, ref in (("pickup", "1"), ("mission", "pet")):  # both credited by the demo seed
        try:
            sql("INSERT INTO txns(ts,kind,ref,points) VALUES('t',?,?,1)", kind, ref)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError(f"a second {kind} credit for {ref} was accepted")
    sql("INSERT INTO txns(ts,kind,ref,points) VALUES('t','redeem','coffee',-450)")


@section
def health_checks_writes_and_space():
    assert c.get("/api/health").json() == {"ok": True}
    with patched(main.shutil, disk_usage=lambda _: SimpleNamespace(free=(main.MIN_FREE_MB - 1) * 2**20)):
        r = c.get("/api/health")
    assert (r.status_code, r.json()) == (503, {"ok": False, "reason": "disk_low"})
    real = main.DB_PATH
    main.DB_PATH = os.path.join(os.path.dirname(real), "missing", "x.db")
    assert c.get("/api/health").json() == {"ok": False, "reason": "db_unwritable"} and not os.path.exists(main.DB_PATH)
    main.DB_PATH = real
    if os.geteuid() != 0:  # root ignores permission bits
        folder = os.path.dirname(real)
        modes = {p: os.stat(p).st_mode for p in (real, folder)}  # restored exactly afterwards
        with closing(sqlite3.connect(real)) as reader:  # an open connection keeps the WAL in place, as the running app does
            reader.execute("SELECT 1 FROM txns").fetchall()
            os.chmod(real, 0o444)
            os.chmod(folder, 0o555)
            try:
                r = c.get("/api/health")
            finally:
                for p, mode in modes.items():
                    os.chmod(p, mode)
        assert (r.status_code, r.json()) == (503, {"ok": False, "reason": "db_unwritable"}), r.text
    assert c.get("/api/health").status_code == 200


@section
def db_busy_is_503():
    def quick():
        con = DEFAULTS["db"]()
        con.execute("PRAGMA busy_timeout=50")  # the real wait is 5 s; the outcome is the same
        return con

    main.db = quick
    with closing(sqlite3.connect(main.DB_PATH, isolation_level=None)) as holder, logs() as lines:
        holder.execute("BEGIN IMMEDIATE")
        r = post("/api/rewards/bike/redeem")
        holder.execute("ROLLBACK")
    assert (r.status_code, r.headers.get("retry-after")) == (503, "1"), r.text
    busy = [lvl for lvl, m in lines if m.startswith("event=db_busy ")]
    assert busy == [logging.ERROR], lines
    assert post("/api/rewards/bike/redeem").status_code == 200  # the lock is gone, the retry passes


# ---- ops.py ---------------------------------------------------------------------------------------------------

@section
def ops_backup():
    """An online, integrity-checked copy that matches the source; the newest 14 stay; a missing database fails."""
    post(f"/api/pickups/{new_pickup()['id']}/complete")
    code = post("/api/rewards/bike/redeem").json()["code"]
    dst = tempfile.mkdtemp(dir=TMP)
    stale = [f"sabz-20000101-{i:06d}.db" for i in range(15)]
    for name in stale:
        open(os.path.join(dst, name), "w").close()
    with logs() as lines:
        assert ops.backup(dst) == 0
    kept = sorted(os.listdir(dst))
    assert len(kept) == 14 and kept[:-1] == stale[-13:], kept
    copy = os.path.join(dst, kept[-1])
    with closing(sqlite3.connect(copy)) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone()
        assert con.execute("SELECT COUNT(*) FROM txns").fetchall() == sql("SELECT COUNT(*) FROM txns")
    assert events(lines, "backup") == [f"event=backup ok=1 bytes={os.path.getsize(copy)} file={kept[-1]}"], lines
    ops.DB_PATH = os.path.join(dst, "missing.db")
    with logs() as lines:
        assert ops.backup(dst) == 1
    assert events(lines, "backup") == ["event=backup ok=0 reason=FileNotFoundError"] and not os.path.exists(ops.DB_PATH)


@section
def ops_check():
    """The ledger invariants hold after normal use, and each deliberate corruption is caught by name."""
    post(f"/api/pickups/{new_pickup()['id']}/complete")
    post("/api/rewards/bike/redeem")
    post("/api/missions/pizza/answer", {"choice": 1})
    assert ops.check() == 0

    def reason_after(statement):
        path = os.path.join(tempfile.mkdtemp(dir=TMP), "c.db")
        with closing(sqlite3.connect(main.DB_PATH)) as src, closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
            dst.executescript(statement)
        ops.DB_PATH = path
        with logs() as lines:
            assert ops.check() == 1
        return events(lines, "ledger_check")[0].split("reason=")[1]

    assert reason_after("UPDATE txns SET points = points + 1000 WHERE kind='pickup' AND ref='1'") == "pickup_txn_unmatched,pickup_sum"
    assert reason_after("DELETE FROM txns WHERE kind='pickup' AND ref='1'") == "pickup_sum"  # delivered, never credited
    assert reason_after("DROP INDEX txns_once; INSERT INTO txns(ts,kind,ref,points) VALUES('t','pickup','1',"
                        "(SELECT points FROM pickups WHERE id=1))") == "pickup_sum"  # a double credit
    assert reason_after("INSERT INTO txns(ts,kind,ref,points) VALUES('t','adjust','x',-1000000)") == "negative_balance"
    assert reason_after("DELETE FROM missions_done WHERE id='pizza'") == "mission_unrecorded"
    assert reason_after("INSERT INTO codes VALUES('SABZ-forged','cinema','t',NULL)") == "codes_exceed_redeems"


@section
def ops_cli():
    """The compose contract: python ops.py backup DIR | check, DB_PATH from the environment, exit 1 on failure."""
    def run(*args, db=main.DB_PATH):
        return subprocess.run([sys.executable, "ops.py", *args], cwd=HERE, capture_output=True, text=True, timeout=300,
                              env=os.environ | {"DB_PATH": db})

    dst = tempfile.mkdtemp(dir=TMP)
    r = run("backup", dst)
    assert r.returncode == 0 and "event=backup ok=1" in r.stderr and len(os.listdir(dst)) == 1, r.stderr
    assert run("check").returncode == 0
    sql("INSERT INTO txns(ts,kind,ref,points) VALUES('t','adjust','x',-1000000)")
    r = run("check")
    assert r.returncode == 1 and "event=ledger_check ok=0 reason=negative_balance" in r.stderr, r.stderr
    assert [run().returncode, run("backup").returncode, run("check", db=os.path.join(dst, "none.db")).returncode] == [1, 1, 1]


# ---- request pipeline -----------------------------------------------------------------------------------------

@section
def body_size_limit():
    """16384 bytes pass the limiter and 16385 get a 413: by Content-Length, by a streamed body, or by the header alone."""
    assert main.MAX_BODY == 16384

    def body(n):
        return b'{"choice": 0' + b" " * (n - 13) + b"}"

    def st(content, **headers):
        return c.post("/api/missions/glass/answer", content=content, headers=J | headers).status_code

    assert len(body(16384)) == 16384 and [st(body(16384)), st(body(16385))] == [200, 413]
    assert [st(body(n)[i:i + 4096] for i in range(0, n, 4096)) for n in (16384, 16385)] == [200, 413]
    assert st(b"{}", **{"content-length": "20000"}) == 413


@section
def csrf_guards():
    assert c.post("/api/rewards/bike/redeem").status_code == 415  # no JSON content type
    assert c.post("/api/rewards/bike/redeem", data={"x": "1"}).status_code == 415  # the shape of a cross-site <form>
    assert post("/api/rewards/bike/redeem", headers=J | {"sec-fetch-site": "cross-site"}).status_code == 403
    assert post("/api/rewards/bike/redeem", headers=J | {"sec-fetch-site": "same-origin"}).status_code == 200


@section
def pagination():
    for _ in range(3):
        new_pickup()
    page = c.get("/api/pickups?limit=2").json()
    rest = c.get(f"/api/pickups?limit=200&before={page[1]['id']}").json()
    assert len(page) == 2 and rest and {r["id"] for r in rest}.isdisjoint({page[0]["id"], page[1]["id"]})
    assert len(page) + len(rest) == len(c.get("/api/pickups?limit=200").json()) == 7
    assert c.get(f"/api/pickups?before={2**62}").json() == [] == c.get(f"/api/pickups?before={2**63 - 1}").json()
    assert [c.get(f"/api/pickups?{q}").status_code for q in ("limit=0", "limit=201", f"before={2**63}", "before=0")] == [422] * 4


@section
def read_endpoints():
    """/api/transactions, /api/leaderboard, /api/city and /api/catalog: the shapes and formulas the frontend relies on."""
    with closing(sqlite3.connect(main.DB_PATH)) as con, con:
        con.executemany("INSERT INTO txns(ts,kind,ref,points) VALUES(?,'adjust','test',1)",
                        [(f"2001-01-01T00:00:{i % 60:02d}",) for i in range(101)])
    tx = c.get("/api/transactions").json()
    assert len(tx) == 100 and set(tx[0]) == {"id", "ts", "kind", "ref", "points"}
    assert [(t["ts"], t["id"]) for t in tx] == sorted(((t["ts"], t["id"]) for t in tx), reverse=True)  # newest first
    assert any(t["kind"] == "redeem" for t in tx) and all(t["points"] < 0 for t in tx if t["kind"] == "redeem")
    lifetime = c.get("/api/state").json()["lifetime"]
    board = c.get("/api/leaderboard").json()
    assert [r["points"] for r in board] == sorted((r["points"] for r in board), reverse=True)
    assert [(r["id"], r["points"]) for r in board if r["mine"]] == [("d6", 48210 + lifetime)]
    city = c.get("/api/city").json()
    assert set(city["kpi"]) == {"tons", "mau", "participation", "landfillSaved", "co2", "partners"} and len(city["months"]) == 12
    assert sum(m["pct"] for m in city["materials"]) == 100 and city["districts"] == board
    missions = c.get("/api/catalog").json()["missions"]
    assert all("ok" not in m for m in missions) and [m["id"] for m in missions if m["done"]] == ["pet"]  # no answer key


@section
def rate_limit_burst():
    """Exactly BURST, then 429 with an honest Retry-After: one token refills in 1 / REFILL = 2 s."""
    main.BURST, main.REFILL = 3, 0  # no refill, so the result cannot depend on how fast this host runs
    rs = [post("/api/missions/nope/answer", {"choice": 0}) for _ in range(4)]
    assert [r.status_code for r in rs] == [404, 404, 404, 429] and rs[3].headers["retry-after"] == "2"
    assert DEFAULTS["REFILL"] * int(rs[3].headers["retry-after"]) >= 1
    assert c.get("/api/codes/x").status_code == 429  # the code lookup shares the strict bucket
    assert c.get("/api/state").status_code == 200  # reads have their own


@section
def rate_limit_refill():
    """Refill on a fake clock at 0.5 token/s: 1.5 s idle gives no token, 2 s gives exactly one."""
    now = [1000.0]
    main.clock, main.BURST = (lambda: now[0]), DEFAULTS["BURST"]

    def st():
        return post("/api/missions/nope/answer", {"choice": 0}).status_code

    assert [st() for _ in range(11)] == [404] * 10 + [429]
    now[0] += 1.5
    assert st() == 429
    now[0] += 0.5
    assert [st(), st()] == [404, 429]


@section
def read_bucket():
    """GETs have their own bucket (READ_BURST, then READ_REFILL/s): a page load passes, a read flood gets 429."""
    assert (DEFAULTS["READ_BURST"], DEFAULTS["READ_REFILL"]) == (60, 2.0)
    main.READ_BURST = DEFAULTS["READ_BURST"]
    page = ("/api/catalog", "/api/state", "/api/pickups?limit=1", "/api/transactions", "/api/leaderboard", "/api/city")
    assert [c.get(p).status_code for p in page] == [200] * 6
    main.READ_BURST, main.READ_REFILL = 3, 0
    main._buckets.clear()
    rs = [c.get("/api/state") for _ in range(4)]
    assert [r.status_code for r in rs] == [200, 200, 200, 429] and rs[3].headers["retry-after"] == "1"
    assert post("/api/rewards/bike/redeem").status_code == 200  # writes draw on their own bucket


@section
def malformed_body_is_charged():
    """FastAPI rejects a malformed JSON body before guard runs; the 422 handler charges it and CSRF-checks it."""
    main.BURST, main.REFILL = 3, 0
    assert [c.post("/api/pickups", content=b"{bad", headers=J).status_code for _ in range(4)] == [422, 422, 422, 429]
    assert post("/api/pickups", pk()).status_code == 429  # the same bucket
    main._buckets.clear()
    assert c.post("/api/pickups", content=b"{bad").status_code == 415  # no JSON content type


@section
def trust_proxy_and_edge_bypass():
    """TRUST_PROXY keys on the rightmost X-Forwarded-For entry (the edge's). A missing or multi-entry header is logged
    as an edge bypass, except on /api/health, which the compose healthcheck calls directly."""
    main.TRUST_PROXY, main.BURST, main.REFILL = True, 3, 0

    def st(xff):
        return post("/api/missions/nope/answer", {"choice": 0}, headers=J | {"x-forwarded-for": xff}).status_code

    with logs() as lines:
        assert [st(f"6.6.6.{i}, 10.0.0.9") for i in range(4)] == [404, 404, 404, 429]  # forged left entries: one bucket
        assert st("6.6.6.1, 10.0.0.10") == 404  # another edge-seen client has its own
        c.get("/api/state")
        c.get("/api/state", headers={"x-forwarded-for": "10.0.0.11"})
        c.get("/api/health")
    bypass = [m.rsplit(" ", 1)[1] for m in events(lines, "edge_bypass")]
    assert bypass == ["xff_entries=2"] * 5 + ["xff_entries=0"], bypass


@section
def bucket_keys():
    k = main.bucket_key
    assert k("2001:db8::1") == k("2001:db8::ffff") != k("2001:db8:0:1::1")  # one bucket per IPv6 /64
    assert k("6.6.6.6") == "6.6.6.6" and k("::ffff:6.6.6.6") == "::ffff:6.6.6.6"
    assert len(k("x" * 10_000)) == len(k("y")) == 18 and k("x" * 10_000) != k("y")  # not an address: hashed, fixed size
    main._buckets.update({str(i): (1.0, main.clock() - 200) for i in range(10_001)})
    assert main.throttle("6.6.6.7") and list(main._buckets) == ["6.6.6.7"]  # the idle sweep clears stale keys


@section
def log_hygiene():
    """No full reward code, key or newline reaches a log line; paths are quoted and cut to 200 chars."""
    main.PARTNER_KEYS = (PK.encode(),)
    with logs() as lines:
        code = post("/api/rewards/bike/redeem").json()["code"]
        c.get(f"/api/codes/{code}", headers={"x-partner-key": PK})
        post(f"/api/codes/{code}/use", headers=J | {"x-partner-key": PK})
        c.get("/api/x%0aforged")
        c.get("/api/" + "a" * 8000)
    text = [m for _, m in lines]
    assert not any(code in m or PK in m or "\n" in m for m in text), text
    assert sum(f"/api/codes/code#{sha(code, 8)}" in m for m in text) == 2  # lookup and use, by hash
    assert f"code={sha(code, 8)}" in events(lines, "redeem")[0]
    assert any("/api/x%0Aforged" in m for m in text) and max(len(m) for m in text) < 400


@section
def business_events():
    """Each value event logs one key=value line that carries the request id of its access line."""
    main.PARTNER_KEYS = (PK.encode(),)
    with logs() as lines:
        created = post("/api/pickups", pk())
        pid = created.json()["id"]
        completed = post(f"/api/pickups/{pid}/complete")
        canceled = post(f"/api/pickups/{new_pickup()['id']}/cancel")
        redeemed = post("/api/rewards/bike/redeem")
        code, after_redeem = redeemed.json()["code"], balance()
        used = post(f"/api/codes/{code}/use", headers=J | {"x-partner-key": PK})
        answered = post("/api/missions/pizza/answer", {"choice": 1})

    def line(name, resp):
        found = [m for m in events(lines, name) if f" rid={resp.headers['x-request-id']} " in m]
        assert len(found) == 1, (name, events(lines, name))
        return found[0]

    assert line("create_pickup", created).endswith(f"pid={pid} kg=2.0 est=240")
    assert line("complete", completed).endswith(f"pid={pid} points={completed.json()['points']} kg="
                                                f"{round(completed.json()['weight'], 1)} key=-")
    assert " pid=" in line("cancel", canceled)
    assert line("redeem", redeemed).endswith(f"reward=bike code={sha(code, 8)} balance={after_redeem}")
    assert line("code_use", used).endswith(f"code={sha(code, 8)} key={sha(PK, 6)}")
    assert line("mission_correct", answered).endswith("mission=pizza points=40")


@section
def access_log_and_headers():
    with logs() as lines:
        c.post("/api/rewards/bike/redeem")  # 415
        c.get("/api/state")
    assert [lvl for lvl, _ in lines] == [logging.WARNING, logging.INFO], lines  # security-relevant statuses warn
    h = c.get("/api/health").headers
    assert len(h["x-request-id"]) == 12 and h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store"
    tehran = datetime.now(timezone(timedelta(hours=3, minutes=30))).replace(tzinfo=None)
    assert abs(datetime.fromisoformat(main.ts()) - tehran) < timedelta(seconds=5)  # Tehran time, whatever the host zone


if __name__ == "__main__":
    order = SECTIONS[:]
    if seed := os.getenv("TEST_SHUFFLE"):
        random.Random(seed).shuffle(order)
    if only := os.getenv("TEST_ONLY"):  # comma list of section names
        order = [fn for fn in order if fn.__name__ in only.split(",")]
    failed = []
    for fn in order:
        try:
            fresh()
            fn()
        except Exception:
            failed.append(fn.__name__)
            print(f"FAIL {fn.__name__}\n{traceback.format_exc()}", file=sys.stderr)
    if failed:
        print(f"{len(failed)} of {len(order)} sections failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)  # TMP stays for a look at the databases
    shutil.rmtree(TMP, ignore_errors=True)
    print("ok")
