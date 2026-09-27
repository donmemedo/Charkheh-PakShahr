"""Smoke check: python test_api.py"""
import os
import tempfile
from datetime import date

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

c = TestClient(app)
today = date.today().isoformat()
bal = c.get("/api/state").json()["balance"]
p = c.post("/api/pickups", json={"items": {"plastic": 2}, "day": today, "slot": "08-11", "address": "Tehran"}).json()
assert p["est"] == 240 and p["status"] == "scheduled"
assert c.post("/api/pickups", json={"items": {"plastic": 200}, "day": today, "slot": "08-11", "address": "Tehran"}).status_code == 422
done = c.post(f"/api/pickups/{p['id']}/complete").json()
assert done["status"] == "delivered" and c.get("/api/state").json()["balance"] == bal + done["points"]
assert c.post(f"/api/pickups/{p['id']}/complete").status_code == 409
assert c.post("/api/rewards/cinema/redeem").json()["code"].startswith("SABZ-")
assert c.post("/api/missions/pizza/answer", json={"choice": 0}).json()["correct"] is False
assert c.post("/api/missions/pizza/answer", json={"choice": 1}).json()["points"] == 40
assert c.post("/api/missions/pizza/answer", json={"choice": 1}).status_code == 409
while c.get("/api/state").json()["balance"] >= 1200:
    c.post("/api/rewards/cinema/redeem")
assert c.post("/api/rewards/cinema/redeem").status_code == 409
assert c.get("/api/city").json()["kpi"]["tons"] > 0
print("ok")
