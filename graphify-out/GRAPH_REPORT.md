# Graph Report - Charkheh-PakShahr  (2026-10-15)

## Corpus Check
- Corpus is ~17,976 words - fits in a single context window. You may not need a graph.

## Summary
- 313 nodes · 693 edges · 18 communities (10 shown, 8 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.83)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Security Audit and Deployment
- Frontend Pages
- Frontend Package Manifest
- App Shell and Layout
- TypeScript Config
- Backend Config and Imports
- Pickup and Reward Mutations
- Pinned Backend Dependencies
- Read Endpoints and DB
- Request Guards and Keys
- Body Size Limit Middleware
- Observe Logging Middleware
- Rate Limiter
- Next.js Agent Rules
- App Icon
- PostCSS Config
- Frontend README Boilerplate

## God Nodes (most connected - your core abstractions)
1. `SabzBank security, performance and UI/UX audit` - 61 edges
2. `useI18n()` - 30 edges
3. `Attack-tree threat model (G0-G6)` - 26 edges
4. `compilerOptions` - 16 edges
5. `PickupPage()` - 15 edges
6. `ErrorBox()` - 14 edges
7. `useApi()` - 14 edges
8. `db()` - 13 edges
9. `Counter()` - 13 edges
10. `Loading()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Geist font via next/font` --conceptually_related_to--> `FP4 Fonts via CSS packages without preload`  [AMBIGUOUS]
  frontend/README.md → SECURITY_AUDIT.md
- `httpx 0.28.1 (test-only)` --conceptually_related_to--> `Backend regression suite (test_api.py, 55 assertions)`  [INFERRED]
  backend/requirements-dev.txt → SECURITY_AUDIT.md
- `SabzBank README` --references--> `requirements-dev.txt (hash-locked runtime + test tree)`  [EXTRACTED]
  README.md → backend/requirements-dev.txt
- `Single demo user with seeded history` --conceptually_related_to--> `B1 No authentication`  [INFERRED]
  README.md → SECURITY_AUDIT.md
- `uvicorn 0.53.0` --conceptually_related_to--> `B15 No security logging; server banner`  [EXTRACTED]
  backend/requirements.txt → SECURITY_AUDIT.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **G1 Mint points for free (threat branch and controls)** — security_audit_b1, security_audit_b2, security_audit_b5, security_audit_b7, security_audit_b14, security_audit_b15, docker_compose_demo_mode, docker_compose_collector_key, security_audit_begin_immediate [EXTRACTED 1.00]
- **G2 Spend points you do not have (threat branch and controls)** — security_audit_b3, security_audit_b4, security_audit_b8, security_audit_n7, security_audit_atomic_conditional_writes, security_audit_begin_immediate, docker_compose_partner_key [EXTRACTED 1.00]
- **Per-client rate-limit identity chain (G4.5)** — security_audit_n1, security_audit_n6, security_audit_n8, security_audit_n11, docker_compose_edge, docker_compose_frontend, docker_compose_trust_proxy, security_audit_rate_limiter [EXTRACTED 1.00]

## Communities (18 total, 8 thin omitted)

### Community 0 - "Security Audit and Deployment"
Cohesion: 0.06
Nodes (70): uvicorn 0.53.0, backend service, COLLECTOR_KEY env var, DEMO_MODE env var, edge service (Caddy reverse proxy), frontend service, PARTNER_KEY env var, sabz-data volume (+62 more)

### Community 1 - "Frontend Pages"
Cohesion: 0.13
Nodes (54): Activity(), STATUS, TX, Area(), CityPage(), Donut(), KPI, League() (+46 more)

### Community 2 - "Frontend Package Manifest"
Cohesion: 0.07
Nodes (26): dependencies, lucide-react, next, react, react-dom, devDependencies, tailwindcss, @tailwindcss/postcss (+18 more)

### Community 3 - "App Shell and Layout"
Cohesion: 0.11
Nodes (18): inter, metadata, RootLayout(), vazir, viewport, Logo(), NAV, Pref (+10 more)

### Community 4 - "TypeScript Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 6 - "Pickup and Reward Mutations"
Cohesion: 0.21
Nodes (10): Answer, cancel_pickup(), complete_pickup(), create_pickup(), estimate(), init_db(), PickupIn, redeem() (+2 more)

### Community 7 - "Pinned Backend Dependencies"
Cohesion: 0.23
Nodes (14): requirements.txt (hash-locked runtime tree), requirements-dev.txt (hash-locked runtime + test tree), httpx 0.28.1 (test-only), fastapi 0.142.4, httptools 0.8.0, opentelemetry-api 1.45.1, pydantic 2.13.5, starlette 1.7.0 (+6 more)

### Community 8 - "Read Endpoints and DB"
Cohesion: 0.24
Nodes (10): catalog(), city(), db(), health(), leaderboard(), pickup_row(), pickups(), ranking() (+2 more)

### Community 9 - "Request Guards and Keys"
Cohesion: 0.21
Nodes (5): client_ip(), code_lookup(), code_use(), guard(), require_key()

### Community 15 - "App Icon"
Cohesion: 0.67
Nodes (3): App Icon (icon.svg), Green-to-Teal Brand Gradient (#22c55e to #0d9488), Leaf Glyph with Stem and Veins

## Ambiguous Edges - Review These
- `FP4 Fonts via CSS packages without preload` → `Geist font via next/font`  [AMBIGUOUS]
  frontend/README.md · relation: conceptually_related_to

## Knowledge Gaps
- **19 isolated node(s):** `react-dom`, `@tailwindcss/postcss`, `@types/node`, `@types/react`, `@types/react-dom` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 114 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SabzBank security, performance and UI/UX audit` connect `Security Audit and Deployment` to `Pinned Backend Dependencies`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **What connects `react-dom`, `@tailwindcss/postcss`, `@types/node` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Security Audit and Deployment` be split into smaller, more focused modules?**
  _Cohesion score 0.06219918548685672 - nodes in this community are weakly interconnected._
- **Why does `next` connect `App Shell and Layout` to `Frontend Pages`, `Frontend Package Manifest`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Should `Frontend Pages` be split into smaller, more focused modules?**
  _Cohesion score 0.1300563236047107 - nodes in this community are weakly interconnected._
- **Why does `react` connect `Frontend Pages` to `Frontend Package Manifest`, `App Shell and Layout`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `FP4 Fonts via CSS packages without preload` and `Geist font via next/font`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._