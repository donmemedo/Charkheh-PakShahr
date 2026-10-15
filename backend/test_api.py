"""Smoke + regression check: python test_api.py"""
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["DEMO_MODE"] = "1"
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

main.BURST = 10**6  # this file fires dozens of POSTs; the rate limit gets its own check below
c = TestClient(main.app)
J = {"content-type": "application/json"}
post = lambda path, body=None, headers=J, **kw: c.post(path, json={} if body is None else body, headers=headers, **kw)  # noqa: E731
today = main.today().isoformat()
pk = lambda **o: {"items": {"plastic": 2}, "day": today, "slot": "08-11", "address": "Tehran"} | o  # noqa: E731
balance = lambda: c.get("/api/state").json()["balance"]  # noqa: E731


def fanout(fn, n=8):
    with ThreadPoolExecutor(n) as ex:
        return sorted(r.status_code for r in ex.map(lambda _: fn(), range(n)))


# ---- original smoke flow -------------------------------------------------------------------
bal = balance()
p = post("/api/pickups", pk()).json()
assert p["est"] == 240 and p["status"] == "scheduled"
assert post("/api/pickups", pk(items={"plastic": 200})).status_code == 422
done = post(f"/api/pickups/{p['id']}/complete").json()
assert done["status"] == "delivered" and balance() == bal + done["points"]
assert post(f"/api/pickups/{p['id']}/complete").status_code == 409
code = post("/api/rewards/cinema/redeem").json()["code"]
assert code.startswith("SABZ-")
assert post("/api/missions/pizza/answer", {"choice": 0}).json()["correct"] is False
assert post("/api/missions/pizza/answer", {"choice": 1}).json()["points"] == 40
assert post("/api/missions/pizza/answer", {"choice": 1}).status_code == 409
assert c.get("/api/city").json()["kpi"]["tons"] > 0

# ---- B7 answer key only on a correct answer; B8 codes are stored and verifiable ---------------
assert "answer" not in post("/api/missions/battery/answer", {"choice": 0}).json()
assert len(code) >= 16 and c.get(f"/api/codes/{code}").json()["rid"] == "cinema"
assert c.get("/api/codes/SABZ-nope").status_code == 404

# ---- B8 a partner spends a code once; keys compare as bytes (non-ASCII is a 403, not a 500) ----
main.PARTNER_KEY = "p" * 32
use = lambda c_, k: post(f"/api/codes/{c_}/use", headers=J | {"x-partner-key": k}).status_code  # noqa: E731
assert use(code, b"\xe9") == 403 and use(code, "nope") == 403 and use("SABZ-nope", "p" * 32) == 404
assert use(code, "p" * 32) == 200 and use(code, "p" * 32) == 409 and c.get(f"/api/codes/{code}").json()["used"]
os.environ["SHORT_KEY"] = "k-1"
try:
    main.env_key("SHORT_KEY")
except SystemExit:
    pass
else:
    raise AssertionError("a key under 32 chars must stop startup")

# ---- B12 huge pid, B13 whitespace address, B14 double submit is 409 not 500 -----------------
assert post("/api/pickups/99999999999999999999/complete").status_code == 422
assert post("/api/pickups", pk(address="   ")).status_code == 422
codes = fanout(lambda: post("/api/missions/battery/answer", {"choice": 1}))
assert codes == [200] + [409] * 7, codes

# ---- B3 concurrent redeem: balance covers exactly one cinema ticket --------------------------
while balance() >= 2400:
    assert post("/api/rewards/cinema/redeem").status_code == 200
assert 1200 <= balance() < 2400
codes = fanout(lambda: post("/api/rewards/cinema/redeem"))
assert codes == [200] + [409] * 7, codes
assert balance() >= 0

# ---- B4 concurrent complete awards points once --------------------------------------------
p2 = post("/api/pickups", pk()).json()
bal = balance()
codes = fanout(lambda: post(f"/api/pickups/{p2['id']}/complete"))
assert codes == [200] + [409] * 7, codes
assert bal < balance() <= bal + 264  # one award of 240 ±10%

# ---- B10 body limit (Content-Length and streamed), B11 CSRF guards -------------------------
assert c.post("/api/pickups", content=b"{" + b" " * 20_000 + b"}", headers=J).status_code == 413
assert c.post("/api/pickups", content=(b" " * 4096 for _ in range(8)), headers=J).status_code == 413
assert c.post("/api/rewards/bike/redeem").status_code == 415                       # no JSON content type
assert c.post("/api/rewards/bike/redeem", data={"x": "1"}).status_code == 415      # cross-site <form> shape
assert post("/api/rewards/bike/redeem", headers=J | {"sec-fetch-site": "cross-site"}).status_code == 403

# ---- B2 daily cap (two pickups created so far today) ----------------------------------------
for _ in range(main.PICKUPS_PER_DAY - 2):
    assert post("/api/pickups", pk()).status_code == 201
assert post("/api/pickups", pk()).status_code == 409

# ---- B2 cap holds under concurrency (fresh day budget: drop today's rows first) -----------------
sqlite3.connect(os.environ["DB_PATH"]).execute("DELETE FROM pickups WHERE created >= ?", (today,)).connection.commit()
codes = fanout(lambda: post("/api/pickups", pk()))
assert codes == [201] * main.PICKUPS_PER_DAY + [409] * (8 - main.PICKUPS_PER_DAY), codes
up = c.get("/api/state").json()["upcoming"]["id"]
assert [post(f"/api/pickups/{up}/cancel").status_code for _ in "ab"] == [200, 409]
assert post(f"/api/pickups/{2**62}/cancel").status_code == 404

# ---- B5 spoofed X-Forwarded-For: with TRUST_PROXY the key is the rightmost (edge-proxy) entry ----
main.TRUST_PROXY, main.BURST, main._buckets = True, 3, {}
codes = [post("/api/missions/nope/answer", {"choice": 0}, headers=J | {"x-forwarded-for": f"6.6.6.{i}, 10.0.0.9"}).status_code for i in range(4)]
assert codes == [404, 404, 404, 429], codes
main.TRUST_PROXY, main.BURST, main._buckets = False, 10**6, {}
# IPv6 buckets per /64 (IPv4 and IPv4-mapped per address); the idle sweep still clears stale keys
assert main.bucket_key("2001:db8::1") == main.bucket_key("2001:db8::ffff") != main.bucket_key("2001:db8:0:1::1")
assert main.bucket_key("6.6.6.6") == "6.6.6.6" and main.bucket_key("::ffff:6.6.6.6") == "::ffff:6.6.6.6"
main._buckets, main._swept = {str(i): (1.0, time.monotonic() - 200) for i in range(10_001)}, float("-inf")
assert main.throttle("x") and list(main._buckets) == ["x"]
main._buckets = {}
assert c.get("/api/catalog").json()["demo"] is True

# ---- B6 pagination ---------------------------------------------------------------------------
page = c.get("/api/pickups?limit=2").json()
assert len(page) == 2
rest = c.get(f"/api/pickups?limit=200&before={page[1]['id']}").json()
assert rest and {r["id"] for r in rest}.isdisjoint({page[0]["id"], page[1]["id"]})
assert len(page) + len(rest) == len(c.get("/api/pickups?limit=200").json())
assert c.get("/api/pickups?limit=0").status_code == 422 and c.get("/api/pickups?limit=500").status_code == 422
assert c.get(f"/api/pickups?before={2**63}").status_code == 422  # not an sqlite OverflowError 500

# ---- log lines quote the decoded path, so an encoded newline cannot forge a second line ---------
seen = []
h = logging.Handler()
h.emit = lambda r: seen.append(r.getMessage())
main.log.addHandler(h)
c.get("/api/x%0aforged")
main.log.removeHandler(h)
assert len(seen) == 1 and "\n" not in seen[0] and "/api/x%0Aforged" in seen[0], seen

# ---- B15 headers, P1 WAL ----------------------------------------------------------------------
h = c.get("/api/health").headers
assert len(h["x-request-id"]) == 12 and h["x-content-type-options"] == "nosniff" and h["cache-control"] == "no-store"
assert sqlite3.connect(os.environ["DB_PATH"]).execute("PRAGMA journal_mode").fetchone()[0] == "wal"

# ---- B5 rate limit: burst then 429, also on the code lookup ---------------------------------
main.BURST, main._buckets = 10, {}
codes = [post("/api/missions/nope/answer", {"choice": 0}).status_code for _ in range(11)]
assert codes[:10] == [404] * 10 and codes[10] == 429, codes
assert c.get("/api/codes/x").status_code == 429
main.BURST = 10**6

# ---- B1/B9 production mode: docs off, complete needs the collector key -----------------------
prod = subprocess.run([sys.executable, "-c", f"""
import os; os.environ.pop('DEMO_MODE'); os.environ.update(DB_PATH={os.path.join(tempfile.mkdtemp(), 'p.db')!r}, COLLECTOR_KEY='k' * 32)
from fastapi.testclient import TestClient; import main
c = TestClient(main.app); J={{'content-type':'application/json'}}
assert c.get('/api/catalog').json()['demo'] is False  # DEMO_MODE unset fails closed
assert main.app.openapi_url is None and c.get('/docs').status_code == 404 and c.get('/redoc').status_code == 404
p = c.post('/api/pickups', json={pk()!r}, headers=J).json()
assert c.post(f"/api/pickups/{{p['id']}}/complete", json={{}}, headers=J).status_code == 403
assert c.post(f"/api/pickups/{{p['id']}}/complete", json={{}}, headers=J | {{'x-collector-key': 'nope'}}).status_code == 403
assert c.post(f"/api/pickups/{{p['id']}}/complete", json={{}}, headers=J | {{'x-collector-key': 'k' * 32}}).status_code == 200
print('prod ok')
"""], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)), timeout=300)
assert prod.stdout.strip().endswith("prod ok"), prod.stderr[-2000:]
assert c.get("/docs").status_code == 200  # demo mode keeps the docs

print("ok")
