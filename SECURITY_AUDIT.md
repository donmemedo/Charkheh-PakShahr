# SabzBank security, performance and UI/UX audit

Branch `audit/security-perf-ux`, against `main` at `1dfd7df`. Work done 2026-10-02 to 2026-10-15.

## Summary

The MVP let any visitor mint unlimited points and spend points it did not have. The first took two unauthenticated calls; the second took a race between parallel redeems. Both are closed, together with every finding from the first code read and 15 more found in this pass.

- **Fixed:** all 16 backend findings (B1 to B16), all 4 backend performance findings (P1 to P4), infrastructure findings I1 and I2 (I3 partly), all 4 frontend security findings (F1 to F4) and all 4 frontend performance findings (FP1 to FP4).
- **New in this pass:** 15 further issues, from a spoofable rate-limit key to 12 known advisories in Starlette 0.48.0. All 15 are fixed (table N1 to N15).
- **Verified by:**
  - A backend regression suite of 55 assertions, including 8-way concurrency checks. It runs in about a minute.
  - A clean TypeScript check and a clean production build.
  - Live header and CSP nonce checks against the built app.
  - semgrep on the final code (293 rules, 0 findings).
  - pip-audit on the hash-locked dependency file, with no known vulnerabilities.
- **Not done:** see "Skipped and remaining" at the end. The main gap is real user authentication, which is a product decision.

## Method

| Lens | What it covered | Skill |
| --- | --- | --- |
| Threat model | Abuse tree of the ways to gain rewards or deny service, with the control that closes each leaf | attack-tree-construction |
| Code audit | Every endpoint, the container setup and the Next.js layer, against OWASP Top 10 | security-auditor, security-audit |
| Static analysis | semgrep packs p/python, p/typescript, p/react, p/nextjs, p/secrets, p/owasp-top-ten | security-scanning-security-sast |
| Dependency audit | pip-audit on the installed packages and on the final lock file | security-scanning-security-sast |
| Abuse-case testing (red team) | Concurrency races, rate limits and header spoofing, oversize and streamed bodies, cross-site posts, production-mode gates, log injection | regression suite in `backend/test_api.py` |
| Defensive review (blue team) | Independent review of every control added in this pass, then fixes for what it found | security-auditor |
| Performance | CPU time on 10,000 pickups and 10,000 transactions, before and after, plus per-request overhead | performance |
| UI/UX | Apple fluid-interface principles: motion, springs, materials, accessibility, feedback | apple-design |
| Simplicity | Review of the whole diff for code that does not need to exist | ponytail-review, ponytail |
| Code map | Knowledge graph of the final code in `graphify-out/` | graphify |

## Threat model

Attacker goal: obtain rewards or disrupt the service without earning points. Each leaf names the control that now closes it.

```
G0  Obtain rewards or disrupt the service without earning points
├── OR G1  Mint points for free
│   ├── AND G1.1 create a pickup + G1.2 call the collector "complete" action yourself
│   │        before: two curl calls, nothing logged
│   │        closed by: DEMO_MODE off unless set + X-Collector-Key (32+ chars, constant-time),
│   │                   5 pickups/day under a write lock, rate limit, WARNING log lines (B1, B2, B5, B15)
│   ├── G1.3 answer a mission twice in parallel         closed by: insert-or-ignore, 409 (B14)
│   └── G1.4 read the answer key from a wrong answer    closed by: answer only on success (B7)
├── OR G2  Spend points you do not have
│   ├── G2.1 race several redeems past one balance check
│   │        closed by: one atomic INSERT…SELECT…WHERE + IMMEDIATE transactions (B3)
│   ├── G2.2 race two completes to be paid twice        closed by: UPDATE … WHERE status='scheduled' (B4)
│   ├── G2.3 invent a reward code (24-bit, unverifiable)
│   │        closed by: 72-bit code stored with the debit, partner lookup endpoint (B8)
│   └── G2.4 spend one real code at partners many times
│            closed by: partner-authenticated, single-use consume endpoint (N7)
├── OR G3  Act as the user from another site (matters once cookie auth exists)
│   ├── G3.1 cross-site form POST                       closed by: JSON content type + Sec-Fetch-Site (B11)
│   └── G3.2 clickjack the redeem button                closed by: frame-ancestors 'none', X-Frame-Options (F1)
├── OR G4  Deny service
│   ├── G4.1 oversized body                             closed by: 16 KiB limit in Next and in FastAPI (B10, N13)
│   ├── G4.2 unbounded creation and listing             closed by: rate limit, cap, bounded pagination (B5, B6, N9)
│   ├── G4.3 huge path or query id → 500                closed by: bounded Path and Query (B12, N9)
│   ├── G4.4 concurrent writes → "database is locked"   closed by: WAL + busy timeout (P1)
│   └── G4.5 dodge the rate limit by forging X-Forwarded-For or rotating IPv6 addresses
│            closed by: Caddy edge sets the header, rightmost entry, uvicorn proxy trust off,
│                       one bucket per IPv6 /64 (N1, N4, N5, N11)
├── OR G5  Reach the backend directly
│   ├── G5.1 public port 8026 and /docs                 closed by: loopback bind, docs off unless demo (B9)
│   └── G5.2 escape from a root container               closed by: non-root user, read-only FS, no capabilities (I1)
└── OR G6  Hide or forge evidence
    └── G6.1 inject fake lines into the access log     closed by: URL-quoted path in log lines (N10)
```

## Findings and status

Severity assumes deployment to real users. Every "fixed" row has at least one check in `backend/test_api.py`, except where the table says otherwise.

### Backend (`backend/main.py`)

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| B1 | Critical | No authentication. Anyone can act as the user. | Fixed for the collector action only: `DEMO_MODE` is off unless set, and in production the collector action needs `X-Collector-Key` (32+ characters, constant-time compare). Real user sign-in is a product decision; see remaining risks. |
| B2 | Critical | Citizens can call the collector action and credit themselves about 75,000 points per pickup. | Fixed: collector gate (B1), and at most 5 pickups per day, counted under `BEGIN IMMEDIATE`. Check: 8 parallel creates give exactly 5 successes. |
| B3 | High | Redeem race: balance check and debit were separate, so parallel redeems overspent. | Fixed: one `INSERT … SELECT … WHERE SUM(points) >= cost` statement, and `rowcount` decides. Check: 8 parallel redeems against a balance for one give 1 success and 7 rejections, and the balance never goes negative. |
| B4 | High | Complete race awarded points twice. | Fixed: `UPDATE … WHERE id=? AND status='scheduled'` plus `rowcount`, and the same for cancel. Check: 8 parallel completes award once. |
| B5 | Medium | No rate limit. | Fixed: in-process token bucket, burst 10 then 30 per minute, on every POST and the code lookup, with 429 and `Retry-After`. |
| B6 | Medium | `GET /api/pickups` was unbounded. | Fixed: `limit` from 1 to 200 (default 50), and a bounded keyset `before` cursor. |
| B7 | Medium | A wrong answer returned the answer key. | Fixed: the answer is returned only after a correct answer. |
| B8 | Medium | Reward codes were 24-bit, never stored and unverifiable. | Fixed: `SABZ-` plus a 72-bit `token_urlsafe(9)`, stored in the same transaction as the debit, with `GET /api/codes/{code}` for partners. |
| B9 | Medium | `/docs`, `/redoc` and `/openapi.json` were public, and the backend port was published on all interfaces. | Fixed: docs only in demo mode, and compose binds the API to 127.0.0.1. |
| B10 | Medium | No body size limit. | Fixed: a pure-ASGI middleware returns 413 above 16 KiB, judged by `Content-Length` or by counting a streamed body. |
| B11 | Low | Latent CSRF on bodyless POSTs. | Fixed: POSTs need `application/json`, and `Sec-Fetch-Site: cross-site` gets 403. |
| B12 | Low | A huge path id caused a 500. | Fixed: `Path(ge=1, le=2**63-1)`. |
| B13 | Low | A whitespace-only address passed validation. | Fixed: the address is stripped before validation. |
| B14 | Low | A double mission submit caused a 500. | Fixed: `INSERT OR IGNORE` plus `rowcount` returns 409. |
| B15 | Low | No security logging, and a `server: uvicorn` banner. | Fixed: request id header and one log line per request. Statuses 403, 409, 413, 415 and 429 log at WARNING and 5xx at ERROR. Uvicorn runs with `--no-server-header`. |
| B16 | Info | The server's "today" was UTC while users are in Tehran. | Fixed: Tehran time (UTC+03:30) for dates and timestamps. Iran has had no daylight saving since 2022. |

### New findings in this pass

N1 to N4 came from my own review and the dependency audit. N5 to N15 came from the independent defensive review that ran after the first round of fixes.

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| N1 | Medium | Next.js sets `X-Forwarded-For` only when the client did not send one, and its rewrite proxy does not append. With `TRUST_PROXY=1` and the backend reading the first entry, any caller could rotate the header and never be rate limited. | The backend now keys on the rightmost entry. A Caddy edge service in compose replaces any client value with the real client address, and the frontend no longer publishes a port. |
| N2 | Medium | Starlette 0.48.0 had 12 known advisories, including CVE-2026-48710 and CVE-2026-54282 (`request.url` rebuilt from the Host header and path). | Upgraded to FastAPI 0.142.4 with Starlette 1.7.0, pinned. pip-audit now finds nothing. |
| N3 | Low | The rate-limit guard read `request.url.path`, which N2 shows can disagree with the routed path. | The guard now reads the routed `scope["path"]`. |
| N4 | Low | The new daily pickup cap counted outside the write lock, so parallel creates could overshoot it. | `BEGIN IMMEDIATE` runs before the count. |
| N5 | Medium | `DEMO_MODE` failed open. A production deploy that forgot the variable kept the self-crediting endpoint and the API docs. | The default is now off in both code and compose. The README shows `DEMO_MODE=1` for the demo. |
| N6 | Medium | Uvicorn trusts `X-Forwarded-For` from 127.0.0.1 by default, which overrode `TRUST_PROXY=0` whenever Next and FastAPI shared a host. | `--no-proxy-headers` in the Dockerfile and the documented dev command. |
| N7 | Medium | A redeemed code could be verified but never consumed, so one code could be spent at partners any number of times. | `POST /api/codes/{code}/use` with `X-Partner-Key`. It is single-use through an `UPDATE … WHERE used IS NULL` predicate. |
| N8 | Medium | In the shipped compose layout every request reached FastAPI from the frontend container, so the rate limit was one shared bucket for all users. | Same fix as N1: the Caddy edge sets the client address. |
| N9 | Low | The new pagination cursor had no upper bound, which brought back the B12 crash. | `le=2**63-1` on the cursor. |
| N10 | Low | Log injection. A percent-encoded newline in the path wrote a forged line into the log. | Log lines carry the URL-quoted path. |
| N11 | Low | The rate limit keyed on full IPv6 addresses, so one client could rotate through its /64. Past 10,000 keys, every request also scanned the whole table. | One bucket per IPv6 /64, and the idle sweep runs at most every 10 seconds. |
| N12 | Low | Non-ASCII bytes in a key header crashed the constant-time compare with a 500, and weak keys were accepted. | Keys compare as bytes, and startup refuses keys shorter than 32 characters. |
| N13 | Low | Next buffers up to 10 MB of every proxied body before FastAPI's 16 KiB limit applies. | `proxyClientMaxBodySize: "16kb"` in `next.config.ts`. |
| N14 | Low | Only top-level packages were pinned, and nothing was hash-verified. | Hash-locked `requirements.txt` and `requirements-dev.txt`, built from `.in` files. The Dockerfile installs with `--require-hashes`. |
| N15 | Low | Existing volumes created by the old root image are owned by root, so the new non-root image cannot open the database. | A one-time `chown` command next to the volume in `docker-compose.yml`, with a pointer in the README. Not tested here (no Docker builds on this machine). |

The review also raised five informational items that were not changed. Each has a recorded reason:

- **Error headers:** 500 responses come from Starlette's outer error handler, so they lack the request id header. The 5xx log level was fixed instead.
- **Single-user quotas:** the daily cap and quiz retries are global while the app has one demo user.
- **Route matching:** the code-lookup throttle matches a path string. That would only matter if a root path were configured.
- **Address characters:** the address field accepts control and bidirectional characters. Which ones to allow is a product decision, because the field is multi-line.
- **Frontend container:** it is not read-only and its image is not digest-pinned. Neither could be verified without a Docker build.

### Backend performance

CPU time per request (process CPU, best of 7) on 10,000 pickups and 10,000 transactions. Both versions ran back to back on the same framework version. Wall-clock numbers were dominated by a load average of 85 to 136 on this 4-core machine, so CPU time is the fair comparison.

| Endpoint | Before | After | Why |
| --- | --- | --- | --- |
| GET /api/state | 102.1 ms | 47.0 ms | 2.2× faster: one SQL aggregate over `json_each` replaces a Python loop (P2) |
| GET /api/city | 198.9 ms | 46.9 ms | 4.2× faster: state is computed once instead of twice (P3) |
| GET /api/pickups | 931.2 ms | 11.4 ms | 80× faster, mostly because it returns a page of 50 instead of all 10,000 rows (B6) |
| GET /api/catalog | 6.0 ms | 7.5 ms | +1.5 ms: the security pipeline (below) |
| POST redeem | 7.3 ms | 9.6 ms | +2.3 ms: the pipeline, plus storing the code (B8) |

The security pipeline is the body limit, the guard, and the request-id and logging layer. It first cost about 1.2 ms of CPU per request, mostly because the logging layer used Starlette's `BaseHTTPMiddleware`. Rewritten as plain ASGI, it now costs about 0.8 ms (3.98 ms before against 4.76 ms after on a bare health check).

Other performance changes:

- WAL journal mode with `synchronous=NORMAL` (P1).
- Indexes on `pickups(status, day)`, `pickups(day, id)` and `txns(ts, id)` (P2).
- A client-side stale-while-revalidate cache, so pages stop refetching the catalog (P4, FP3).

### Infrastructure

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| I1 | Medium | The backend container ran as root. | Fixed: non-root user `sabz` (uid 10001). Compose adds `read_only`, a `/tmp` tmpfs, `cap_drop: [ALL]`, `no-new-privileges`, and memory and CPU limits for every service. |
| I2 | Medium | Dependencies were unpinned, and `httpx` shipped in production. | Fixed: hash-locked files (N14), with `httpx` moved to the dev requirements. |
| I3 | Low | Base images were not pinned by digest. | Partly fixed. Tags are pinned. Digests are left as a comment because they could not be verified from this machine. |

### Frontend

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| F1 | Medium | No security headers, and `X-Powered-By` was sent. | Fixed. Static headers in `next.config.ts`: nosniff, Referrer-Policy, X-Frame-Options DENY, Permissions-Policy and COOP. `poweredByHeader: false`. A per-request nonce CSP in `proxy.ts`, Next 16's renamed middleware. HSTS is sent only over HTTPS. |
| F2 | Low | 422 errors showed "[object Object]" or raw English text. | Fixed: errors carry the HTTP status, and pages map it to localized messages, including a new "details aren't valid" message. |
| F3 | Low | Unhandled promise rejections and silent failures. | Fixed: inline, localized error states on redeem, home actions and missions, and a busy guard against double-clicks on quiz answers. |
| F4 | Info | The `lang` cookie lacked `Secure`. | Fixed: `;secure` over HTTPS. |
| FP1 | Perf | Blur on every card over animated blobs, and animations that never stopped. | Fixed: blur only on navigation chrome and sheets, near-solid cards, and animations stop on low-power devices and under reduced motion. |
| FP2 | Perf | Counters re-rendered React on every frame. | Fixed: counters write text through a ref inside the animation frame. |
| FP3 | Perf | Every page waterfalled its data after hydration. | Fixed: stale-while-revalidate GET cache, cleared by a refresh after any change. |
| FP4 | Perf | Fonts loaded through CSS packages with no preload. | Fixed: `next/font/local` with preload and size-adjusted fallbacks. The unused font packages are removed. |

Production CSP, as served by the built app (the nonce changes on every request):

```
default-src 'self'; script-src 'self' 'nonce-…' 'strict-dynamic'; style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self';
form-action 'self'; frame-ancestors 'none'
```

`style-src` keeps `'unsafe-inline'` on purpose. React `style` attributes and Tailwind are used throughout, and a style nonce cannot cover attributes.

## Verification against the running app

The production build ran on the final code, with the backend in production mode. These checks passed:

- All six security headers are present on `/`, and `X-Powered-By` is absent on pages and on proxied API calls.
- The CSP nonce matches all 11 script tags, including the inline theme script, and differs on every request.
- `/docs`, `/redoc` and `/openapi.json` return 404, and the backend sends no server banner.
- The catalog reports `demo: false`, so the "simulate delivery" button is hidden.
- The backend refused to start with a 10-character collector key, which is the startup check working.

## Static analysis and dependencies

- **semgrep 1.179.0:** 293 rules on 18 files, including the Dockerfile and compose file, with 0 findings on the final code. An earlier scan before the review fixes also found nothing. Pattern rules cannot see authorization or race bugs, which is why the regression suite exists.
- **pip-audit:** 12 advisories in Starlette 0.48.0 before. None after the upgrade, on both the installed environment and the hash-locked file.
- **npm audit:** the registry's audit endpoint was unreachable from this machine on three attempts. Run `npm audit` before merging.

## UI/UX (apple-design)

- **Motion:** press feedback is critically damped and instant. Overshoot is kept for success moments only.
- **Sheets:** bottom sheets follow the finger 1:1 from where they were grabbed and resist when pulled upward. On release, the flick velocity is projected forward to decide whether the sheet closes. A small spring carries that velocity. It is critically damped after a slow release and slightly bouncy only after a flick. A new touch interrupts it mid-flight. Taps on buttons inside the sheet still work, because a drag starts only past 10 px or from the handle. Desktop keeps the centered card. Reduced motion uses a cross-fade.
- **Materials:** blur only on navigation chrome and sheets, and never glass on glass. Surfaces turn solid under reduced transparency, and solid with defined borders under increased contrast.
- **Feedback:** inline status, completion and error states, with localized messages for "not enough points", "slow down" and invalid input.
- **Accessibility:**
  - Quantity buttons carry names, and time slots expose `aria-pressed`.
  - The history page has a real tab list with arrow-key navigation.
  - Live regions stay mounted, so quiz results and the points toast are announced reliably.
  - The address field validates when it loses focus and is linked to its error message.
- **Localization:** the LIVE badge, tonnage unit and percent sign follow the language. Negative letter-spacing applies to Latin text only. Counters switch digit sets mid-animation when the language changes.
- **Demo gating:** the "simulate delivery" button appears only when the backend reports demo mode.

## Simplicity review (ponytail)

The review proposed 15 cuts worth about 54 lines.

- **Applied (11):**
  - A fixed Tehran offset instead of a zone database.
  - The single-caller helper inlined.
  - The redundant hidden-tab animation pause removed. Browsers already pause animations in hidden tabs.
  - One `openapi_url` argument instead of three.
  - The default `busy_timeout` pragma, the duplicate compose timezone, the unused fetch options, a redundant CSS declaration and an unused error class all dropped.
  - `secrets.token_hex` instead of `uuid`.
  - The unused font packages removed.
- **Overridden (3):**
  - The sheet spring and momentum code stays, because Apple-style interruptible springs were requested.
  - The pagination cursor stays, because without it pickups beyond the first 200 are unreachable.
  - The `IMMEDIATE` transaction mode stays, because it backs the race fixes at no cost.
- **Superseded (1):** the unused `codes.used` column is now used by the partner consume endpoint (N7).

## Code map (graphify)

`graphify-out/` holds a knowledge graph of the final code and docs: 313 nodes, 693 edges and 18 communities. Open `graph.html` in a browser, or read `GRAPH_REPORT.md`.

- **Most connected:** the audit report itself, then the i18n hook, the threat model, the pickup page and the shared API hook.
- **Cleanly separated:** the security controls form their own small clusters (body limit, logging, rate limiter, request guards).
- **Health check:** 27 extracted edges point at nodes outside the graph, mostly package references, and were dropped. 7 duplicate edges were merged.
- **Excluded:** local working notes, via `.graphifyignore`.

## Skipped and remaining

- **Blocked by the safety classifier.** Three pieces were skipped rather than retried on another model: loading the red-team-tools skill, loading the red-team-tactics skill, and a dedicated agent that replays attack scripts against the old and new code. The abuse cases they targeted are covered by the regression suite.
- **No real user authentication.** The app still has one demo user. Production needs real sign-in, per-user balances and quotas, and a collector role.
- **Rate limits are per process.** That is fine for one instance. Use a shared store such as Redis if the API scales out.
- **Docker images were not built here** because of machine load. The hash-locked install, the Caddy edge and the volume `chown` note need one `docker compose up --build` before merging.
- **Host-local callers** can reach the loopback-bound backend directly with a forged `X-Forwarded-For`. Only processes on the host can do this.
- **Not pinned by digest:** `python:3.12-slim`, `node:22-alpine` and `caddy:2-alpine` (I3).
- **npm audit** could not reach the registry.

## How to verify

```bash
cd backend && python3 -m venv .venv && .venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python test_api.py                       # prints "ok"
cd ../frontend && npm ci && npx tsc --noEmit && npm run build && npm audit
cd .. && DEMO_MODE=1 docker compose up --build     # production: leave DEMO_MODE unset, set COLLECTOR_KEY and PARTNER_KEY (32+ chars)
```
