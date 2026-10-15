# SabzBank · سبزبانک

Iranian take on [Recyclebank](https://www.recyclebank.com/) (see `26_Recyclebank_Business_Plan_Toolkit_Iran_filled.pdf`):
citizens hand in separated dry waste, earn points, and spend them with partners; the municipality gets a live dashboard.

- `frontend/` Next.js 16 (App Router, Tailwind v4) — fa/en with RTL, light/dark/system theme, fully responsive
- `backend/` FastAPI + SQLite — single demo user, seeded history

## Run with Docker

```bash
DEMO_MODE=1 docker compose up --build   # demo: API docs and "Simulate delivery" on
```

Web: http://localhost:3026 · API docs (demo only): http://localhost:8026/docs (override with `WEB_PORT` / `API_PORT`).
In production leave `DEMO_MODE` unset and set `COLLECTOR_KEY` and `PARTNER_KEY`, 32+ characters each
(`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`). Upgrading a volume made by the old root image: see `docker-compose.yml`.

## Run locally

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
DEMO_MODE=1 .venv/bin/uvicorn main:app --port 8026 --no-proxy-headers   # smoke test: .venv/bin/python test_api.py

cd frontend && npm install
BACKEND_URL=http://localhost:8026 npm run dev -- -p 3026
```

On the dashboard, **Simulate delivery** (demo mode only) stands in for the collector app: it weighs the bags (±10%) and credits the points.
