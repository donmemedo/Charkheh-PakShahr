# Graph Report - Charkheh-PakShahr  (2026-10-22)

## Corpus Check
- 48 files · ~164,613 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: (none) 8, .in 2, .woff2 2)

## Summary
- 749 nodes · 1828 edges · 37 communities (32 shown, 5 thin omitted)
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 340 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3c8bc0da`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Security Audit and Deployment
- Frontend Pages
- Frontend Package Manifest
- Endpoints
- TypeScript Config
- Backend Config and Imports
- Validation rules and business constants
- logs
- threat_intel.py
- Module layout
- screenshots.py
- Body Size Limit Middleware
- Observe
- Operations runbook
- Next.js Agent Rules
- App Icon
- PostCSS Config
- Request
- Control map
- test_api.py
- post
- test_api.py
- LAST_Report: everything done on SabzBank, from the first step to now
- overdue_expiry
- ops.py
- smoke.sh
- docs/README.md
- Dependency threat intelligence
- DevSecOps pipeline
- Acceptance criteria
- Packaging roadmap
- charge
- UI and UX design
- Implementation plan: from demo to pilot
- Jobs
- test_threat_intel.py

## God Nodes (most connected - your core abstractions)
1. `SabzBank security, performance and UI/UX audit` - 68 edges
2. `Control map` - 62 edges
3. `section()` - 48 edges
4. `Traceability` - 47 edges
5. `post()` - 41 edges
6. `useI18n()` - 34 edges
7. `Attack-tree threat model (G0-G6)` - 26 edges
8. `Module layout` - 19 edges
9. `Validation rules and business constants` - 19 edges
10. `db()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `What to watch in the logs` --references--> `fp()`  [INFERRED]
  docs/OPERATIONS.md → backend/main.py
- `Migration ladder` --references--> `init_db()`  [INFERRED]
  docs/ARCHITECTURE.md → backend/main.py
- `GET /api/transactions` --references--> `redeem()`  [INFERRED]
  docs/API.md → backend/main.py
- `POST /api/pickups` --references--> `day()`  [INFERRED]
  docs/API.md → backend/test_api.py
- `6. Skills used` --references--> `errKey()`  [INFERRED]
  LAST_Report.md → frontend/components/ui.tsx

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **G1 Mint points for free (threat branch and controls)** — security_audit_b1, security_audit_b2, security_audit_b5, security_audit_b7, security_audit_b14, security_audit_b15, docker_compose_demo_mode, docker_compose_collector_key, security_audit_begin_immediate [EXTRACTED 1.00]
- **G2 Spend points you do not have (threat branch and controls)** — security_audit_b3, security_audit_b4, security_audit_b8, security_audit_n7, security_audit_atomic_conditional_writes, security_audit_begin_immediate, docker_compose_partner_key [EXTRACTED 1.00]
- **Per-client rate-limit identity chain (G4.5)** — security_audit_n1, security_audit_n6, security_audit_n8, security_audit_n11, docker_compose_edge, docker_compose_frontend, docker_compose_trust_proxy, security_audit_rate_limiter [EXTRACTED 1.00]

## Communities (37 total, 5 thin omitted)

### Community 0 - "Security Audit and Deployment"
Cohesion: 0.05
Nodes (86): requirements.txt (hash-locked runtime tree), requirements-dev.txt (hash-locked runtime + test tree), httpx 0.28.1 (test-only), fastapi 0.142.4, httptools 0.8.0, opentelemetry-api 1.45.1, pydantic 2.13.5, starlette 1.7.0 (+78 more)

### Community 1 - "Frontend Pages"
Cohesion: 0.07
Nodes (84): Automation pyramid, 1. Design principles, 6. Feedback states, Activity(), Empty(), STATUS, TX, Area() (+76 more)

### Community 2 - "Frontend Package Manifest"
Cohesion: 0.07
Nodes (26): dependencies, lucide-react, next, react, react-dom, devDependencies, tailwindcss, @tailwindcss/postcss (+18 more)

### Community 3 - "Endpoints"
Cohesion: 0.08
Nodes (26): upcoming(), API reference, Base URL and transport, Collector flow (production), Common headers, Demo flow (`DEMO_MODE=1`), Endpoints, Error shapes (+18 more)

### Community 4 - "TypeScript Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 5 - "Backend Config and Imports"
Cohesion: 0.12
Nodes (5): city(), leaderboard(), ranking(), Phase E: the points-economy anchor and pilot metrics, 9. Open items

### Community 6 - "Validation rules and business constants"
Cohesion: 0.12
Nodes (27): Answer, audit(), cancel_pickup(), catalog(), code_lookup(), code_use(), complete_pickup(), create_pickup() (+19 more)

### Community 7 - "logs"
Cohesion: 0.13
Nodes (14): access_log_and_headers(), line(), events(), key_failures_are_uniform(), attempt(), key_rotation(), complete_with(), log_hygiene() (+6 more)

### Community 8 - "threat_intel.py"
Cohesion: 0.15
Nodes (13): Workflow-wide settings (`ci.yml`), 2. Collection, apply_triage(), exit_code(), fixed_versions(), http_json(), main(), norm() (+5 more)

### Community 9 - "Module layout"
Cohesion: 0.21
Nodes (11): bucket_key(), estimate(), fp(), log_path(), require_key(), seed(), throttle(), Keys (+3 more)

### Community 10 - "screenshots.py"
Cohesion: 0.11
Nodes (5): send_with_headers(), Cdp, problems(), run(), note()

### Community 12 - "Observe"
Cohesion: 0.20
Nodes (8): Observe, Architecture, Components, Configuration, Data model, Migration ladder, Observability, Request flow

### Community 13 - "Operations runbook"
Cohesion: 0.12
Nodes (16): A volume created by the old root image, Backups, Data volume loss, Health and readiness, Incident runbooks, Key rotation, Leaked collector key, Leaked partner key (+8 more)

### Community 15 - "App Icon"
Cohesion: 0.67
Nodes (3): App Icon (icon.svg), Green-to-Teal Brand Gradient (#22c55e to #0d9488), Leaf Glyph with Stem and Veins

### Community 17 - "Request"
Cohesion: 0.29
Nodes (3): db_unavailable(), invalid(), Error handling

### Community 18 - "Control map"
Cohesion: 0.23
Nodes (7): env_keys(), db_busy_is_503(), ops_cli(), production_mode(), weak_keys_stop_startup(), Testing, Control map

### Community 19 - "test_api.py"
Cohesion: 0.18
Nodes (9): init_db(), daily_cap_resets_at_tehran_midnight(), fresh(), legacy_db(), migration_step_is_atomic(), migration_upgrades_in_place(), schema_state(), tier_edges_and_empty_production_db() (+1 more)

### Community 20 - "post"
Cohesion: 0.11
Nodes (18): address_length(), st(), body_size_limit(), code_lookup_and_use(), use(), csrf_guards(), kg_bounds(), st() (+10 more)

### Community 21 - "test_api.py"
Cohesion: 0.12
Nodes (31): award_once_index(), balance(), bucket_keys(), business_events(), complete_future_day(), complete_payout(), complete_races(), daily_cap() (+23 more)

### Community 22 - "LAST_Report: everything done on SabzBank, from the first step to now"
Cohesion: 0.14
Nodes (14): 10. How to run and verify, 1. Short version, 2. Timeline, 3. What the app is now, 4. What was fixed and verified, 5. Role reviews: what each role said and what I did, 6. Skills used, 7. Safeguards, usage limits and what was skipped (+6 more)

### Community 23 - "overdue_expiry"
Cohesion: 0.22
Nodes (7): day(), day_window(), st(), insert_pickup(), lifespan_startup(), overdue_expiry(), upcoming_pickup()

### Community 24 - "ops.py"
Cohesion: 0.24
Nodes (4): backup(), check(), connect(), smoke

### Community 25 - "smoke.sh"
Cohesion: 0.29
Nodes (7): burst(), check(), csp_has(), csp_strict(), fetch(), nonce(), smoke.sh script

### Community 26 - "docs/README.md"
Cohesion: 0.07
Nodes (36): body(), Complete implementation report, Features, How to reproduce, Open items and decisions, Scope and goals, Stack, Status of the audit findings (+28 more)

### Community 27 - "Dependency threat intelligence"
Cohesion: 0.18
Nodes (12): 1. Direction: priority intelligence requirements, 3. Processing, 4. Analysis, 5. Dissemination, 6. Feedback, Dependency threat intelligence, Limits, Metrics worth tracking (+4 more)

### Community 28 - "DevSecOps pipeline"
Cohesion: 0.18
Nodes (11): Adding a suppression safely, Before commit (suggested), Dependabot, DevSecOps pipeline, Gates and exit codes, Known state on this branch, Not run by CI, Pinning and updates (+3 more)

### Community 29 - "Acceptance criteria"
Cohesion: 0.18
Nodes (11): Acceptance criteria, Cancel, City dashboard, Complete (collector), History, Language and theme, Missions, My reward codes (+3 more)

### Community 30 - "Packaging roadmap"
Cohesion: 0.18
Nodes (11): CSP and the service worker, Order of work, Packaging roadmap, Risks, Step 1: PWA, Step 4: Android, Step 5: iOS, Steps 2 and 3: collector and partner screens (+3 more)

### Community 31 - "charge"
Cohesion: 0.27
Nodes (8): charge(), client_ip(), guard(), Trust boundaries, Backend, Not adopted, and when to adopt, Performance, Request guards

### Community 32 - "UI and UX design"
Cohesion: 0.20
Nodes (10): 10. Screenshots, 11. Known limits, 2. Tokens, 3. Light, dark and automatic, 4. Right to left and left to right, 5. The six pages, 7. Sample data and "my codes", 8. Accessibility (+2 more)

### Community 33 - "Implementation plan: from demo to pilot"
Cohesion: 0.25
Nodes (9): expire_hourly(), lifespan(), Background sweep, Assumptions, Current architecture relevant to the plan, Decisions and owners, Implementation plan: from demo to pilot, Objective (+1 more)

### Community 34 - "Jobs"
Cohesion: 0.29
Nodes (7): backend, docker, frontend, gate, Jobs, sast, secrets

## Ambiguous Edges - Review These
- `Geist font via next/font` → `FP4 Fonts via CSS packages without preload`  [AMBIGUOUS]
  frontend/README.md · relation: conceptually_related_to

## Knowledge Gaps
- **19 isolated node(s):** `react-dom`, `@tailwindcss/postcss`, `@types/node`, `@types/react`, `@types/react-dom` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 304 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SabzBank security, performance and UI/UX audit` connect `Security Audit and Deployment` to `docs/README.md`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Are the 61 inferred relationships involving `Control map` (e.g. with `audit()` and `BodyLimit`) actually correct?**
  _`Control map` has 61 INFERRED edges - model-reasoned connections that need verification._
- **What connects `react-dom`, `@tailwindcss/postcss`, `@types/node` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Security Audit and Deployment` be split into smaller, more focused modules?**
  _Cohesion score 0.050187265917602995 - nodes in this community are weakly interconnected._
- **Why does `Automation pyramid` connect `Frontend Pages` to `docs/README.md`, `test_api.py`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Are the 46 inferred relationships involving `Traceability` (e.g. with `access_log_and_headers()` and `address_length()`) actually correct?**
  _`Traceability` has 46 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Geist font via next/font` and `FP4 Fonts via CSS packages without preload`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._