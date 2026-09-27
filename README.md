# SabzBank · سبزبانک

Iranian take on [Recyclebank](https://www.recyclebank.com/) (see `26_Recyclebank_Business_Plan_Toolkit_Iran_filled.pdf`):
citizens hand in separated dry waste, earn points, and spend them with partners; the municipality gets a live dashboard.

- `frontend/` Next.js 16 (App Router, Tailwind v4) — fa/en with RTL, light/dark/system theme, fully responsive
- `backend/` FastAPI + SQLite — single demo user, seeded history

## Run with Docker

```bash
docker compose up --build
```

Web: http://localhost:3026 · API docs: http://localhost:8026/docs (override with `WEB_PORT` / `API_PORT`).

## Run locally

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --port 8026          # smoke test: .venv/bin/python test_api.py

cd frontend && npm install
BACKEND_URL=http://localhost:8026 npm run dev -- -p 3026
```

On the dashboard, **Simulate delivery** stands in for the collector app: it weighs the bags (±10%) and credits the points.
