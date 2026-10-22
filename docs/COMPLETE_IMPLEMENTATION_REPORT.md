# Complete implementation report

This is the report of SabzBank as implemented on FastAPI and Next.js on branch `audit/followups`: the scope and goals, the stack with the versions pinned in the repository, the feature list, a traceability table from each feature to its endpoint, page and tests, the status of every audit finding group and every role-review item, the verification evidence with what was and was not run, the open items and the decisions they need, and how to reproduce every check. It links to the other documents rather than repeating them. The narrative of how the work happened is in [../LAST_Report.md](../LAST_Report.md).

## Scope and goals

SabzBank lets citizens in Tehran turn separated dry waste into points: request a doorstep pickup, get points when it is weighed, spend them with partners, and learn sorting through short missions. A municipality dashboard presents city totals. The build has three goals:

1. A working MVP of the citizen journey, in Persian (right to left) and English, light and dark, on phone and desktop.
2. A backend whose money path is correct under concurrency and hardened against the abuse paths found in the audit.
3. An operable, reproducible deployment: locked-down containers, backups, a ledger check, CI with security gates.

Out of scope for this build, by decision: real user accounts (one demo user), real weighing (a random factor stands in), collector and partner screens (API only), and packaged apps. Each has a phase in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) or a step in [ROADMAP.md](ROADMAP.md).

## Stack

| Layer | Component | Version as pinned | Pinned in |
|---|---|---|---|
| Backend runtime | Python | 3.12, `python:3.12-slim@sha256:05cda977…` | `backend/Dockerfile` |
| | FastAPI / Starlette / Pydantic | 0.142.4 / 1.7.0 / 2.13.5 | `backend/requirements.txt` (hash lock) |
| | uvicorn / httptools / uvloop | 0.53.0 / 0.8.0 / 0.22.1 | `backend/requirements.txt` |
| | httpx (tests only) | 0.28.1 | `backend/requirements-dev.txt` |
| | SQLite | the library bundled with the image's Python; WAL, `synchronous=FULL` | not pinned separately |
| Frontend | Node.js | 22, `node:22-alpine@sha256:0a7108bf…` | `frontend/Dockerfile` |
| | Next.js | 16.3.8 (with `sharp` 0.35.5 and `source-map-js` 1.2.2 in the lockfile) | `frontend/package.json`, `package-lock.json` |
| | React / React DOM | 19.2.8 / 19.2.8 | `frontend/package.json` |
| | Tailwind CSS / TypeScript / lucide-react | 4.3.3 / 5.9.3 / 1.47.0 (ranges `^4`, `^5`, `^1.47.0`; exact in the lockfile) | `frontend/package-lock.json` |
| Edge | Caddy | 2, `caddy:2-alpine@sha256:d8542f48…` | `docker-compose.yml` |
| CI tools | semgrep / gitleaks / pip-audit | 1.182.0 / 8.30.1 / 2.10.1 | `.github/workflows/ci.yml` |
| | trivy-action / hadolint-action | v0.36.0 / v3.5.0, by commit SHA | `.github/workflows/ci.yml` |

## Features

**Citizen app** (six pages, `frontend/app/`):

| Page | Route | What it does |
|---|---|---|
| Dashboard (پیش‌خوان) | `/` | Wallet balance and tier progress, impact rings, the next pickup with cancel (and "Simulate delivery" in demo mode), quick actions |
| Pickup request | `/pickup` | Materials and kg, day, slot, address, estimated points, confirmation |
| Rewards (پاداش‌ها) | `/rewards` | Catalogue by category, redeem with confirmation, the code with Copy, «کدهای من» (the codes redeemed in this browser) |
| Missions (ماموریت‌ها) | `/missions` | Quiz cards, the district league |
| History (تاریخچه) | `/activity` | Requests and transactions tabs |
| City dashboard (پیش‌خوان شهرداری) | `/city` | KPIs, monthly chart, material mix, district ranking (sample data) |

Plus `error.tsx` and `not-found.tsx`, a shell with navigation, language and theme toggles. The design is described in [UI_UX.md](UI_UX.md).

**Collector and partner APIs** (key headers, no screens): `POST /api/pickups/{pid}/complete` with `X-Collector-Key`; `GET /api/codes/{code}` and `POST /api/codes/{code}/use` with `X-Partner-Key`. See [API.md](API.md).

**City dashboard**: `GET /api/city`, a seeded sample series plus the user's real delivered weight.

**Internationalization and theming**: a `fa`/`en` dictionary in `frontend/lib/i18n.tsx`, the locale from the `lang` cookie rendered server-side in `app/layout.tsx` (`lang` and `dir` on `<html>`), Persian digits and the Persian calendar for dates, an LTR isolate for signed numbers; theme preference (automatic, light, dark) in `localStorage` with an inline nonce'd script to avoid a flash.

**Operations**: readiness health check, online backups, ledger check, hourly overdue sweep ([OPERATIONS.md](OPERATIONS.md)).

## Traceability

| Feature | Backend endpoint | Frontend page | Tests (`backend/test_api.py` sections, unless noted) |
|---|---|---|---|
| Wallet, tier, impact, next pickup | `GET /api/state` | `/` | `state_reads_one_snapshot`, `upcoming_pickup`, `tier_edges_and_empty_production_db`, `demo_seed` |
| Catalogue (materials, slots, rewards, missions, demo flag) | `GET /api/catalog` | all pages | `read_endpoints`, `smoke_flow`; `smoke.sh` (demo flag) |
| Pickup request | `POST /api/pickups` | `/pickup` | `kg_bounds`, `day_window`, `address_length`, `daily_cap`, `daily_cap_resets_at_tehran_midnight` |
| Collector complete / Simulate delivery | `POST /api/pickups/{pid}/complete` | `/` (demo only) | `complete_payout`, `complete_races`, `complete_future_day`, `status_action_matrix`, `production_mode`, `key_rotation` |
| Cancel | `POST /api/pickups/{pid}/cancel` | `/` | `status_action_matrix` |
| Missed pickups | lifespan sweep | | `overdue_expiry`, `lifespan_startup` |
| Redeem | `POST /api/rewards/{rid}/redeem` | `/rewards` | `redeem_at_exact_balance`, `redeem_races`, `smoke_flow` |
| My codes | none (browser storage) | `/rewards` | manual ([QA_PLAN.md](QA_PLAN.md)); the `rewards-mycodes-*` capture of `scripts/screenshots.py` |
| Partner lookup and spend | `GET /api/codes/{code}`, `POST /api/codes/{code}/use` | none | `code_lookup_and_use`, `key_failures_are_uniform`, `log_hygiene` |
| Missions | `POST /api/missions/{mid}/answer` | `/missions` | `missions`, `mission_choice_bounds` |
| District league | `GET /api/leaderboard` | `/missions` | `read_endpoints` |
| History | `GET /api/pickups`, `GET /api/transactions` | `/activity` | `pagination`, `read_endpoints` |
| City dashboard | `GET /api/city` | `/city` | `read_endpoints`, `smoke_flow` |
| Health | `GET /api/health` | compose healthcheck | `health_checks_writes_and_space`, `db_busy_is_503` |
| Request pipeline (CSRF, limits, body, logs) | all | all | `csrf_guards`, `rate_limit_burst`, `rate_limit_refill`, `read_bucket`, `malformed_body_is_charged`, `trust_proxy_and_edge_bypass`, `bucket_keys`, `body_size_limit`, `log_hygiene`, `business_events`, `access_log_and_headers` |
| Storage and migrations | | | `storage_settings`, `migration_upgrades_in_place`, `migration_step_is_atomic`, `award_once_index` |
| Backup and ledger check | `ops.py` | | `ops_backup`, `ops_check`, `ops_cli` |
| Security headers and CSP | | `proxy.ts`, `next.config.ts` | `scripts/smoke.sh full` |
| Language and theme | | `layout.tsx`, `lib/i18n.tsx`, `components/shell.tsx` | manual ([QA_PLAN.md](QA_PLAN.md)) |

## Status of the audit findings

From [../SECURITY_AUDIT.md](../SECURITY_AUDIT.md), with the follow-up changes:

| Group | Status now |
|---|---|
| B1 to B16 (backend) | Fixed. B1 for the collector action only (no user accounts yet). Extended since: B5 now limits every routed request with a separate read bucket; B8's lookup is partner-only; B15 has audit events |
| N1 to N16 (found during the pass) | Fixed. N12 extended with 10 distinct characters, rotation and a uniform 403 |
| P1 to P3 (backend performance) | Fixed; P1 now uses `synchronous=FULL` |
| P4 (catalogue refetched on every page) | Mitigated by the client cache |
| I1, I2 (infrastructure) | Fixed. I1 extended: non-root read-only edge, read-only frontend |
| I3 (digest pins) | Fixed: all three base images are pinned by digest |
| F1 to F4 (frontend security) | Fixed |
| FP1, FP2, FP4 (frontend performance) | Fixed. FP1's "low-power devices" claim is stale: no such code exists |
| FP3 (data waterfall) | Mitigated by the stale-while-revalidate cache |
| npm advisories (`next` 16.3.6 and two transitive packages) | Fixed by `next` 16.3.8 (`sharp` 0.35.5, `source-map-js` 1.2.2); the OSV query reports 0 advisories |
| Informational items | Single-user quotas: phase B. Address characters: open, a product decision. 500s without a request id header: unchanged. Path-string throttle matching: unchanged. Frontend container read-only and pinned: done |
| Skipped and remaining | Real authentication: phase B. Per-process rate limits: accepted. Full compose run: done (20 of 20 smoke checks). Clean-clone frontend image: fixed (the Dockerfile creates `public/`). History page limit: fixed (asks for 200, no load-more). Host-local callers: accepted |

## Status of the role-review items

All 60 items, by disposition (details and reasons in [ROLE_REVIEWS.md](ROLE_REVIEWS.md)):

| Role | Done | Done, part | Deferred | Rejected |
|---|---|---|---|---|
| Product owner | PO-03, PO-04, PO-09 | PO-05 | PO-01, PO-02, PO-06, PO-07, PO-08, PO-10, PO-11, PO-12 | |
| Tech lead | TL-01, TL-02, TL-03, TL-08, TL-09 | TL-04, TL-05, TL-07 | TL-06, TL-10, TL-11 | TL-12 |
| Red team | RT-11, RT-12 | RT-02, RT-03, RT-06, RT-09 | RT-01, RT-04, RT-05, RT-07, RT-08, RT-10 | |
| Blue team | BT-03, BT-06, BT-07, BT-08, BT-09 | BT-01, BT-02, BT-11 | BT-04, BT-05, BT-10 | BT-12 |
| QA | QA-01, QA-02, QA-03, QA-08, QA-10, QA-12 | QA-04, QA-07, QA-09 | QA-05, QA-06, QA-11 | |
| **Total** | **21** | **14** | **23** | **2** |

## Verification evidence

What ran on this branch:

| Check | Result |
|---|---|
| Backend suite, `python test_api.py` | `ok`, 47 sections, on three full runs and one shuffled run (`TEST_SHUFFLE=31337`) |
| Mutation check | 8 of 8 planted bugs caught, each by its own section |
| CPU benchmark (10,000 pickups and transactions) | Within about 1 ms of the previous code on reads, +2.1 ms on redeem ([BACKEND.md](BACKEND.md)) |
| `synchronous=FULL` cost | +2.1 to 2.5 ms wall clock per commit (median of 40 rounds, twice) |
| pip-audit on `requirements.txt` | No known vulnerabilities |
| Lock consistency check | Consistent; a deliberately bumped copy fails it |
| `scripts/test_threat_intel.py`, then the live brief | `ok`; PASS with exit 0 (16 PyPI pins, 101 npm packages); the positive control gives exit 1 |
| hadolint 2.15.1 | Both Dockerfiles clean after the numeric-`USER` fix |
| trivy 0.76.1 | Both fresh images pass the CI gate; 44 unfixed HIGH in the backend's Debian base; frontend 0 HIGH or CRITICAL |
| gitleaks 8.30.1 | History and the checked-out files clean; the allowlist canary behaves |
| actionlint 1.7.12, shellcheck | 0 errors; clean |
| semgrep with the CI packs | First run (1.179.0): 6 findings, 5 fixed (Dependabot cooldown) and 1 false positive in a test-file `chmod` line, since rewritten. Re-check on all 67 committable files: 0 findings |
| `docker compose build`, `up --wait` | Both images built; all three services healthy in 30 s |
| `scripts/smoke.sh full` / backend mode | 20 of 20, twice / 6 of 6; both negative controls fail as designed |
| Healthchecks by hand | All three pass; the edge check fails with the frontend stopped |
| `ops` and `ledger-check` profiles | Backup `ok=1` with an integrity-checked copy; check `ok=1`; an unwritable target exits 1 |
| Visual QA in Chrome | 54 captures before the fixes: 0 CSP violations, 0 console errors, 13 rendering defects, all fixed ([UI_UX.md](UI_UX.md), section 9) |
| Frontend after the fixes | `npx tsc --noEmit` exit 0; `npm run build` passed three times; the capture script: 60 captures, 0 distinct issues in `issues.json` |
| Re-check by three reviewers (code, docs, ponytail) | Suite `ok` (also shuffled), `tsc` exit 0, semgrep 0 findings, compose config valid. Their verified findings were applied, then the suite (`ok`) and `tsc` (exit 0) ran again |

What was not run:

- **CI on GitHub.** The workflows have not run there yet. Dependabot's configuration cannot be validated offline.
- **Firefox, Safari and real phones with screen readers** ([UI_UX.md](UI_UX.md), known limits).
- **A restore drill** on a real backup, and **docker-bench-security** on a production host.
- **Load or soak tests**, and **DAST** against a running stack.
- **The red-team tool skills and attack-script replays**, skipped on purpose; the abuse cases are covered defensively by the suite.
- **The final documentation pass** ran the backend suite, the type checker and the threat-intel test, and no builds or containers.

## Open items and decisions

1. **Let CI run** on pull request 2: the workflows have not run on GitHub yet, so the first run is the check of every job.
2. **The semgrep false positive** in a test-file `chmod` line no longer shows locally (the line restores saved modes, `os.chmod(p, mode)`); if the `sast` job on CI (semgrep 1.182.0) still flags it, add a `nosemgrep` comment with the rule id.
3. **Product constants to confirm** (product owner): 50 kg per pickup, 7 days before a missed pickup is canceled, 5 pickups a day, the 60-request read burst, and the rest flagged "product rule, confirm" in [BACKEND.md](BACKEND.md).
4. **Founder decisions:** sign-in method and SMS budget, partner terms, the value of a point, pilot metrics ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), "Decisions and owners").
5. **Before the first production upgrade** of an existing database, run the duplicate-credit check ([OPERATIONS.md](OPERATIONS.md)).
6. **Before real traffic:** TLS in front of the edge, an off-host backup copy, and the decision on where the collector and partner APIs are reachable from.

## How to reproduce

| Check | Command | Details |
|---|---|---|
| Backend suite | `cd backend && .venv/bin/python test_api.py` | [BACKEND.md](BACKEND.md) |
| One section, shuffled run | `TEST_ONLY=<name> …`, `TEST_SHUFFLE=<seed> …` | [BACKEND.md](BACKEND.md) |
| pip-audit, lock check | `pipx run --spec pip-audit==2.10.1 pip-audit --require-hashes --disable-pip -r requirements.txt` | [DEVSECOPS.md](DEVSECOPS.md) |
| Frontend | `cd frontend && npm ci --ignore-scripts && npx tsc --noEmit && npm run build && npm audit --audit-level=high` | [DEVSECOPS.md](DEVSECOPS.md) |
| Secrets, SAST, Dockerfile lint, image scan, SBOM | the pinned `docker run` lines | [DEVSECOPS.md](DEVSECOPS.md) |
| Threat brief | `python3 scripts/threat_intel.py` | [THREAT_INTEL.md](THREAT_INTEL.md) |
| Stack and smoke | `export DEMO_MODE=1; docker compose up -d --build --wait && scripts/smoke.sh full` | [QA_PLAN.md](QA_PLAN.md) |
| Container settings | the `docker inspect` loop | [DOCKER_HARDENING.md](DOCKER_HARDENING.md) |
| Backup and ledger check | `docker compose --profile ops run --rm ops`, `… ledger-check` | [OPERATIONS.md](OPERATIONS.md) |
| Screenshots | `backend/.venv/bin/python scripts/screenshots.py <base url> <out dir>` | [UI_UX.md](UI_UX.md), [QA_PLAN.md](QA_PLAN.md) |
