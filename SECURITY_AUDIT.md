# SabzBank security, performance and UI/UX audit

Branches `audit/security-perf-ux` (pull request 1, against `main` at `1dfd7df`) and `audit/followups` (its follow-up pass, pull request 2). Work done 2026-10-02 to 2026-10-22.

## Summary

The MVP let any visitor mint unlimited points and spend points it did not have. The first took two unauthenticated calls; the second took a race between parallel redeems. Both are closed, together with every finding from the first code read except where the tables say otherwise, and 16 more found in this pass. The follow-up pass (2026-10-16 to 2026-10-22) acted on five role reviews, a visual QA and real Docker runs; its findings are in "Follow-up pass" below.

- **Fixed:** all 16 backend findings (B1 to B16; B1 for the collector action only, because real user authentication is a product decision), backend performance findings P1 to P3, infrastructure findings I1 and I2, all 4 frontend security findings (F1 to F4) and frontend performance findings FP1, FP2 and FP4. P4 and FP3 are mitigated: a page visited before renders from a client cache, but every page still refetches. I3 (digest pinning) is fixed: all three base images are pinned by digest.
- **New in this pass:** 16 further issues, from a spoofable rate-limit key to 6 known vulnerabilities in Starlette 0.48.0. All 16 are fixed (table N1 to N16; N16 in the follow-up pass).
- **Follow-up pass:** 10 groups of findings (FU1 to FU10: 1 High, 5 Medium, 4 Low), all fixed.
- **Verified by:**
  - A backend regression suite of 47 isolated sections (fake clock, seeded weighing jitter, a fresh database per section, also run shuffled), including 8-way concurrency checks. It runs in about 4 seconds on an idle machine. Planting 8 bugs one at a time was caught each time by its own section.
  - A clean TypeScript check and a clean production build (Next.js 16.3.8).
  - Live header and CSP nonce checks against the built app.
  - semgrep: 0 findings on pull request 1's final code, and 0 in the final re-check of the follow-up pass (see "Static analysis and dependencies").
  - pip-audit on the hash-locked dependency file, and the OSV query for the npm lockfile, with no known vulnerabilities.
  - Docker runs on 2026-10-22: both images build from the digest-pinned bases, the full stack runs under `docker compose up --build --wait`, and `scripts/smoke.sh full` passes 20 of 20 checks, twice (backend mode 6 of 6), including the Caddy edge replacing a forged `X-Forwarded-For`. The old-volume `chown` was checked on 2026-10-16.
  - A visual QA in Chrome: after the fixes, 60 captures with 0 CSP violations, console errors or failed requests.
  - In production mode the database starts empty at 0 points; the sample history is seeded only with `DEMO_MODE=1`.
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
│   │                   5 pickups/day under a write lock, 50 kg per pickup, rate limit,
│   │                   WARNING log lines (B1, B2, B5, B15, FU3)
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
│   ├── G4.1 oversized body                             closed by: 413 above 16 KiB in FastAPI; Next buffers at most 16 KiB (B10, N13)
│   ├── G4.2 unbounded creation and listing             closed by: rate limit, cap, bounded pagination (B5, B6, N9)
│   ├── G4.3 huge path or query id → 500                closed by: bounded Path and Query (B12, N9)
│   ├── G4.4 concurrent writes → "database is locked"   closed by: WAL + busy timeout (P1)
│   └── G4.5 dodge the rate limit by forging X-Forwarded-For or rotating IPv6 addresses
│            closed by: Caddy edge sets the header, rightmost entry, uvicorn proxy trust off,
│                       one bucket per IPv6 /64 (N1, N6, N8, N11)
├── OR G5  Reach the backend directly
│   ├── G5.1 public port 8026 and /docs                 closed by: loopback bind, docs off unless demo (B9)
│   └── G5.2 escape from the backend container          closed by: non-root user, read-only FS, no capabilities (I1)
└── OR G6  Hide or forge evidence
    └── G6.1 inject fake lines into the access log     closed by: URL-quoted path in log lines (N10)
```

## Findings and status

Severity assumes deployment to real users. Every backend code fix (B and N rows) has at least one check in `backend/test_api.py`, except N3. Fixes that live in configuration (B9's loopback bind, B15's server banner, N2, N6, N8, N13 to N15, I1 to I3) and the frontend rows (F1 to F4, FP1 to FP4) are verified by the build, the live checks, pip-audit, the Docker runs and `scripts/smoke.sh`, and review instead.

### Backend (`backend/main.py`)

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| B1 | Critical | No authentication. Anyone can act as the user. | Fixed for the collector action only: `DEMO_MODE` is off unless set, and in production the collector action needs `X-Collector-Key` (32+ characters with 10+ distinct ones, a comma list for rotation, checked in constant time; an unset, missing or wrong key gets the same 403). Real user sign-in is a product decision; see remaining risks. |
| B2 | Critical | Citizens can call the collector action and credit themselves about 75,000 points per pickup. | Fixed: collector gate (B1), and at most 5 pickups per day, counted under `BEGIN IMMEDIATE`. Check: 8 parallel creates give exactly 5 successes. Since the follow-up pass a pickup is also capped at 50 kg in total, so one complete pays at most 15,000 points (16,500 with the ±10% weighing). |
| B3 | High | Redeem race: balance check and debit were separate, so parallel redeems overspent. | Fixed: one `INSERT … SELECT … WHERE SUM(points) >= cost` statement, and `rowcount` decides. Check: 8 parallel redeems against a balance for one give 1 success and 7 rejections, and the balance never goes negative. |
| B4 | High | Complete race awarded points twice. | Fixed: `UPDATE … WHERE id=? AND status='scheduled'` plus `rowcount`, and the same for cancel. Check: 8 parallel completes award once. |
| B5 | Medium | No rate limit. | Fixed: in-process token bucket per client. POSTs and the code lookup: burst 10, then 30 per minute. Every other GET has its own bucket: burst 60, then 2 per second. A POST with a malformed body is CSRF-checked and charged too. 429 with `Retry-After` (2 or 1 seconds). |
| B6 | Medium | `GET /api/pickups` was unbounded. | Fixed: `limit` from 1 to 200 (default 50), and a bounded keyset `before` cursor. |
| B7 | Medium | A wrong answer returned the answer key. | Fixed: the answer is returned only after a correct answer. |
| B8 | Medium | Reward codes were 24-bit, never stored and unverifiable. | Fixed: `SABZ-` plus a 72-bit `token_urlsafe(9)`, stored in the same transaction as the debit, with `GET /api/codes/{code}` for partners (it needs `X-Partner-Key`, like the spend endpoint). |
| B9 | Medium | `/docs`, `/redoc` and `/openapi.json` were public, and the backend port was published on all interfaces. | Fixed: docs only in demo mode, and compose binds the API to 127.0.0.1. |
| B10 | Medium | No body size limit. | Fixed: a pure-ASGI middleware returns 413 above 16 KiB, judged by `Content-Length` or by counting a streamed body. |
| B11 | Low | Latent CSRF on bodyless POSTs. | Fixed: POSTs need `application/json`, and `Sec-Fetch-Site: cross-site` gets 403. |
| B12 | Low | A huge path id caused a 500. | Fixed: `Path(ge=1, le=2**63-1)`. |
| B13 | Low | A whitespace-only address passed validation. | Fixed: the address is stripped before validation. |
| B14 | Low | A double mission submit caused a 500. | Fixed: `INSERT OR IGNORE` plus `rowcount` returns 409. |
| B15 | Low | No security logging, and a `server: uvicorn` banner. | Fixed: request id header and one log line per request. Statuses 403, 409, 413, 415 and 429 log at WARNING and 5xx at ERROR. Uvicorn runs with `--no-server-header`. Every value and security event also writes one `event=... rid=...` line (key and code fingerprints only), and uvicorn's own access log is off so each request is logged once. |
| B16 | Info | The server's "today" was UTC while users are in Tehran. | Fixed: Tehran time (UTC+03:30) for dates and timestamps. Iran has had no daylight saving since 2022. |

### New findings in this pass

N1 to N4 came from my own review and the dependency audit. N5 to N15 came from the independent defensive review that ran after the first round of fixes. N16 came from the review of the finished branch.

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| N1 | Medium | Next's `/api` rewrite proxy neither sets nor appends `X-Forwarded-For`: it passes a client-sent value through unchanged. With `TRUST_PROXY=1` and the backend reading the first entry, any caller could rotate the header and never be rate limited. | The backend now keys on the rightmost entry. A Caddy edge service in compose replaces any client value with the real client address, and the frontend no longer publishes a port. |
| N2 | Medium | Starlette 0.48.0 had 6 known vulnerabilities (pip-audit printed 12 rows, two per vulnerability), including CVE-2026-48710 and CVE-2026-54282 (`request.url` rebuilt from the Host header and path). | Upgraded to FastAPI 0.142.4 with Starlette 1.7.0, pinned. pip-audit now finds nothing. |
| N3 | Low | The rate-limit guard read `request.url.path`, which N2 shows can disagree with the routed path. | The guard now reads the routed `scope["path"]`. |
| N4 | Low | The new daily pickup cap counted outside the write lock, so parallel creates could overshoot it. | `BEGIN IMMEDIATE` runs before the count. |
| N5 | Medium | `DEMO_MODE` failed open. A production deploy that forgot the variable kept the self-crediting endpoint and the API docs. | The default is now off in both code and compose. The README shows `DEMO_MODE=1` for the demo. |
| N6 | Medium | Uvicorn trusts `X-Forwarded-For` from 127.0.0.1 by default, which overrode `TRUST_PROXY=0` whenever Next and FastAPI shared a host. | `--no-proxy-headers` in the Dockerfile and the documented dev command. |
| N7 | Medium | A redeemed code could be verified but never consumed, so one code could be spent at partners any number of times. | `POST /api/codes/{code}/use` with `X-Partner-Key`. It is single-use through an `UPDATE … WHERE used IS NULL` predicate. |
| N8 | Medium | In the shipped compose layout every request reached FastAPI from the frontend container, so the rate limit was one shared bucket for all users. | Same fix as N1: the Caddy edge sets the client address. |
| N9 | Low | The new pagination cursor had no upper bound, which brought back the B12 crash. | `le=2**63-1` on the cursor. |
| N10 | Low | Log injection. A percent-encoded newline in the path wrote a forged line into the log. | Log lines carry the URL-quoted path. |
| N11 | Low | The rate limit keyed on full IPv6 addresses, so one client could rotate through its /64. Past 10,000 keys, every request also scanned the whole table. | One bucket per IPv6 /64, and the idle sweep runs at most every 10 seconds. |
| N12 | Low | Non-ASCII bytes in a key header crashed the constant-time compare with a 500, and weak keys were accepted. | Keys compare as bytes; startup refuses keys under 32 characters or with fewer than 10 distinct ones; an unset, missing or wrong key all give the same 403 (an unset key used to give 503). |
| N13 | Low | With `proxy.ts` in use, Next buffers a copy of up to 10 MB of every request body before FastAPI's 16 KiB limit applies. | `experimental.proxyClientMaxBodySize: "16kb"` in `next.config.ts` caps that copy. Next does not reject a larger body (it logs a warning and carries on), so the 413 still comes from FastAPI. |
| N14 | Low | Only top-level packages were pinned, and nothing was hash-verified. | Hash-locked `requirements.txt` and `requirements-dev.txt`, built from `.in` files. The Dockerfile installs with `--require-hashes`. |
| N15 | Low | Existing volumes created by the old root image are owned by root, so the new non-root image cannot open the database. | A one-time `chown` command next to the volume in `docker-compose.yml`, with a pointer in the README. Checked on 2026-10-16: on a root-owned volume the new image fails with "attempt to write a readonly database", and after the documented `chown` it writes as uid 10001. |
| N16 | Low | A request that FastAPI rejected got a 500 instead of a 422 when the rejected value was NaN, Infinity or a lone surrogate: the default handler echoes the input and cannot JSON-encode it. For `POST /api/pickups` this was a regression from moving the weight bounds into the model. | Fixed in the follow-up pass: a 422 handler that returns each error's location, message and type, without the input. It also runs the guard (the JSON content-type and `Sec-Fetch-Site` checks, then the rate-limit charge) for a request FastAPI rejected before the dependency ran, so a malformed body is checked and costs a token like any other. |

The review also raised five informational items that were not changed. Each has a recorded reason:

- **Error headers:** 500 responses come from Starlette's outer error handler, so they lack the request id header. The 5xx log level was fixed instead.
- **Single-user quotas:** the daily cap and quiz retries are global while the app has one demo user.
- **Route matching:** the code-lookup throttle matches a path string. That would only matter if a root path were configured.
- **Address characters:** the address field accepts control and bidirectional characters. Which ones to allow is a product decision, because the field is multi-line.
- **Frontend container:** now read-only (tmpfs `/tmp` and `/app/.next/cache`), non-root (1000:1000) and digest-pinned; checked by `scripts/smoke.sh full` (FU4).

### Backend performance

CPU time per request (process CPU, best of 7) on 10,000 pickups and 10,000 transactions. Both versions ran back to back on the same framework version. Wall-clock numbers were dominated by a load average of 85 to 136 on this 4-core machine, so CPU time is the fair comparison.

| Endpoint | Before | After | Why |
| --- | --- | --- | --- |
| GET /api/state | 102.1 ms | 47.0 ms | 2.2× faster: one SQL aggregate over `json_each` replaces a Python loop (P2) |
| GET /api/city | 198.9 ms | 46.9 ms | 4.2× faster: state is computed once instead of twice (P3) |
| GET /api/pickups | 931.2 ms | 11.4 ms | 81× faster, mostly because it returns a page of 50 instead of all 10,000 rows (B6) |
| GET /api/catalog | 6.0 ms | 7.5 ms | +1.5 ms: the security pipeline (below) |
| POST redeem | 7.3 ms | 9.6 ms | +2.3 ms: the pipeline, plus storing the code (B8) |

The security pipeline is the body limit, the guard, and the request-id and logging layer. It first cost about 1.2 ms of CPU per request, mostly because the logging layer used Starlette's `BaseHTTPMiddleware`. Rewritten as plain ASGI, it now costs about 0.8 ms (3.98 ms before against 4.76 ms after on a bare health check, measured when `/api/health` returned a constant; it now probes a write and the disk, so it is no longer a bare baseline).

Other performance changes:

- WAL journal mode with `synchronous=FULL` (P1; the follow-up pass moved from NORMAL so a committed redeem survives power loss, about 2 to 2.5 ms per commit).
- Indexes on `pickups(status, day)`, `pickups(day, id)` and `txns(ts, id)` (P2).
- A client-side stale-while-revalidate cache, so a page visited before renders its data at once and revalidates in the background. The GET still runs on every mount and after every change, so P4 (catalog refetched on every page) and FP3 are mitigated, not fixed.

### Infrastructure

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| I1 | Medium | The backend container ran as root. | Fixed: the backend runs as non-root user `sabz` (uid 10001) on a read-only root with a `/tmp` tmpfs. Every service gets `cap_drop: [ALL]`, `no-new-privileges`, and memory, CPU and process limits. The edge runs as uid 65534 on a read-only root (tmpfs `/data` and `/config`) and keeps only `NET_BIND_SERVICE`; the frontend runs as uid 1000 on a read-only root (tmpfs `/tmp` and `/app/.next/cache`). |
| I2 | Medium | Dependencies were unpinned, and `httpx` shipped in production. | Fixed: hash-locked files (N14), with `httpx` moved to the dev requirements. |
| I3 | Low | Base images were not pinned by digest. | Fixed in the follow-up pass. All three base images are pinned by digest (`python:3.12-slim@sha256:05cda977…`, `node:22-alpine@sha256:0a7108bf…` in both stages, `caddy:2-alpine@sha256:d8542f48…`); Dependabot bumps them weekly. |

### Frontend

| ID | Sev | Finding | Fix |
| --- | --- | --- | --- |
| F1 | Medium | No security headers, and `X-Powered-By` was sent. | Fixed. Static headers in `next.config.ts`: nosniff, Referrer-Policy, X-Frame-Options DENY, Permissions-Policy and COOP. `poweredByHeader: false`. A per-request nonce CSP in `proxy.ts`, Next 16's renamed middleware. HSTS is sent only over HTTPS. |
| F2 | Low | 422 errors showed "[object Object]" or raw English text. | Fixed: errors carry the HTTP status, and pages map it to localized messages, including a new "details aren't valid" message. |
| F3 | Low | Unhandled promise rejections and silent failures. | Fixed: inline, localized error states on redeem, home actions and missions, and a busy guard against double-clicks on quiz answers. |
| F4 | Info | The `lang` cookie lacked `Secure`. | Fixed: `;secure` over HTTPS. |
| FP1 | Perf | Blur on every card over animated blobs, and animations that never stopped. | Fixed: blur only on the navigation bars, the sheet backdrop and the transient points toast; cards and sheets are solid or near-solid. CSS animations stop under reduced motion (there is no low-power detection). |
| FP2 | Perf | Counters re-rendered React on every frame. | Fixed: counters write text through a ref inside the animation frame. |
| FP3 | Perf | Every page waterfalled its data after hydration. | Mitigated: a stale-while-revalidate GET cache, cleared by a refresh after any change. A page visited before renders from it at once; the first visit to each page still fetches after hydration. |
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

- **semgrep:** on pull request 1's final code, 1.179.0 with 293 rules on 18 files, including the Dockerfile and compose file: 0 findings. In the follow-up pass the CI packs (p/python, p/typescript, p/react, p/nextjs, p/secrets, p/owasp-top-ten) first gave 6 findings: 5 were fixed (Dependabot cooldown) and 1 was a false positive on a permission-restoring `os.chmod` in the test suite, since rewritten. The final re-check over all 67 committable files gave 0. CI pins semgrep 1.182.0 and fails on any finding. Pattern rules cannot see authorization or race bugs, which is why the regression suite exists.
- **pip-audit:** 6 vulnerabilities in Starlette 0.48.0 before (12 rows, two per vulnerability). None after the upgrade, on both the installed environment and the hash-locked file.
- **npm advisories (2026-10-22):** none open. `next` is 16.3.8, `sharp` 0.35.5 and `source-map-js` 1.2.2 in the lockfile. That fixes what the 2026-10-16 check found: 6 `next` 16.3.6 advisories (including the high SSRF in Image Optimization), the `sharp` 0.35.4 librsvg advisory and the `source-map-js` 1.2.1 denial of service. The OSV query in `scripts/threat_intel.py` reports 0 advisories for 16 Python pins and 101 npm packages; CI runs `npm audit --audit-level=high`.

## UI/UX (apple-design)

- **Motion:** press feedback is critically damped and instant. Overshoot is kept for success moments only.
- **Sheets:** bottom sheets follow the finger 1:1 from where they were grabbed and resist when pulled upward. On release, the flick velocity is projected forward to decide whether the sheet closes. A small spring carries that velocity. It is critically damped after a slow release and slightly bouncy only after a flick. A new touch interrupts it mid-flight. Taps on buttons inside the sheet still work, because a drag starts only past 10 px or from the handle. Desktop keeps the centered card. Reduced motion uses a cross-fade.
- **Materials:** blur only on the navigation bars, the sheet backdrop and the transient points toast, and never glass on glass; cards and sheets are solid. Surfaces turn solid under reduced transparency, and solid with defined borders under increased contrast.
- **Feedback:** inline status, completion and error states, with localized messages for "not enough points", "slow down" and invalid input.
- **Accessibility:**
  - Quantity buttons carry names, and time slots expose `aria-pressed`.
  - The history page has a real tab list with arrow-key navigation.
  - Live regions stay mounted, so quiz results and the points toast are announced reliably.
  - The address field validates when it loses focus and is linked to its error message.
- **Localization:** the sample-data badge on the city page («داده نمایشی» / "Sample data"), tonnage unit and percent sign follow the language. Negative letter-spacing applies to Latin text only. Counters switch digit sets mid-animation when the language changes.
- **Demo gating:** the "simulate delivery" button appears only when the backend reports demo mode.
- **Follow-up pass:** the visual QA's 13 defects, the contrast tokens, right-to-left fixes and accessibility work are described in [docs/UI_UX.md](docs/UI_UX.md).

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
  - The pagination cursor stays, because without it API clients cannot reach pickups beyond the largest page of 200.
  - The `IMMEDIATE` transaction mode stays, because it backs the race fixes at no cost.
- **Superseded (1):** the unused `codes.used` column is now used by the partner consume endpoint (N7).

## Code map (graphify)

`graphify-out/` holds a knowledge graph of the code and docs. `GRAPH_REPORT.md` gives its node, edge and community counts, the commit it was built from and the most-connected nodes; open `graph.html` in a browser to explore it.

- **Cleanly separated:** the security controls form their own small clusters (body limit, logging, rate limiter, request guards).
- **Excluded:** local working notes, via `.graphifyignore`.

## Follow-up pass 2026-10-16 to 2026-10-22

Branch `audit/followups`. Five role reviews (product owner, tech lead, a red team at design level, blue team and QA; see [docs/ROLE_REVIEWS.md](docs/ROLE_REVIEWS.md)), a visual QA in Chrome, real Docker builds and runs, and a final re-check by three reviewers (code, docs, simplicity) drove these changes. Test names are sections of `backend/test_api.py`.

| ID | Sev | Finding | Fix | Proof |
| --- | --- | --- | --- | --- |
| FU1 | High | Frontend dependencies, checked 2026-10-16: `next` 16.3.6 had 6 advisories, including a high SSRF in Image Optimization; `sharp` 0.35.4 had a librsvg advisory and `source-map-js` 1.2.1 an event-loop denial of service. | `next` 16.3.8, `sharp` 0.35.5 and `source-map-js` 1.2.2 in the lockfile. | The OSV query in `scripts/threat_intel.py` on 2026-10-22: 0 advisories for 101 npm packages and 16 Python pins, no CISA KEV match. CI runs `npm audit --audit-level=high`. |
| FU2 | Low | N16: a rejected body with NaN, Infinity or a lone surrogate gave a 500 instead of a 422, and a body FastAPI rejected skipped the guard. | The 422 handler in N16: errors without the input, and the guard runs first. | `kg_bounds` (NaN and Infinity are never a 500), `malformed_body_is_charged`. |
| FU3 | Medium | Backend items from the role reviews. One complete could still pay up to 75,000 points (100 kg of each material), and the collector key could complete a pickup whose day was still ahead. A missed pickup stayed "next" forever. `synchronous=NORMAL` could lose a committed redeem on power loss. There was no backup and no ledger check. The schema had no versions, and award-once lived in code only. A production database got the demo history. | At most 50 kg per pickup in total, so one complete pays at most 15,000 points (16,500 with the ±10% weighing); a future-day complete is 409 outside demo mode. The next pickup is the first one due today or later, and a sweep at startup and every hour cancels a scheduled pickup 7 days past its day. `synchronous=FULL` (about 2 to 2.5 ms per commit). `ops.py backup` (online, integrity-checked, newest 14 kept) and `ops.py check` (ledger invariants), run as the compose `ops` and `ledger-check` profiles. A `user_version` migration ladder, one transaction per step, with a unique index that credits a pickup or a mission once. Only `DEMO_MODE=1` seeds the sample history. | `kg_bounds`, `complete_future_day`, `upcoming_pickup`, `overdue_expiry`, `lifespan_startup`, `storage_settings`, `ops_backup`, `ops_check`, `ops_cli`, `migration_upgrades_in_place`, `migration_step_is_atomic`, `award_once_index`, `tier_edges_and_empty_production_db`. Both ops profiles ran against the stack. |
| FU4 | Low | Docker: only the backend image had been built, base images floated on tags (I3), the edge ran as root, the frontend container was writable, and a clean clone could not build the frontend image (`frontend/public` has no tracked file). | All three base images pinned by digest. The edge runs as uid 65534 on a read-only root with only `NET_BIND_SERVICE`; the frontend as uid 1000 on a read-only root, with npm removed from its runtime image; every service has a process limit. The frontend Dockerfile creates `public/` before the build. | Both images built and the stack came up healthy under `docker compose up --build --wait`. `scripts/smoke.sh full`: 20 of 20, twice; backend mode 6 of 6. hadolint clean. trivy: both images pass the CI gate (HIGH and CRITICAL with a fix); the 44 unfixed HIGH findings in the backend's Debian base follow the no-fix policy in [docs/DOCKER_HARDENING.md](docs/DOCKER_HARDENING.md). |
| FU5 | Medium | No CI, no update bot and no secret scan. | `.github/workflows/ci.yml`: the backend suite, a lock check and pip-audit; `npm ci --ignore-scripts`, type check, build and `npm audit`; gitleaks over the full history; semgrep with six packs; hadolint, trivy and a CycloneDX SBOM; a compose smoke job; one gate. Actions are pinned by commit SHA and tool images by digest. Dependabot covers pip, npm, Docker, compose and Actions. A weekly dependency threat brief (`.github/workflows/threat-intel.yml`) checks the pins against OSV and the CISA KEV feed, with expiring accepted risks in `threat-intel/triage.json`. | actionlint 0 errors. Each job's commands ran locally. `scripts/test_threat_intel.py` prints `ok` and the live brief passes. The workflows have not run on GitHub yet. |
| FU6 | Medium | Log hygiene: the access log wrote full reward codes (bearer secrets) in `/api/codes/...` paths, and value events left no record of their own. | Reward codes and keys appear in logs only as sha256 fingerprints (`code#<8 hex>`). One `event=... rid=...` line per value and security event (redeem with the resulting balance, complete, code use, key failures, edge bypass, the overdue sweep), URL-quoted so no value can forge a field or a line. | `log_hygiene`, `business_events`, `access_log_and_headers`. |
| FU7 | Low | One key per role with no rotation; a key of 32 repeated characters passed; an unset key answered 503 "not configured", unlike a wrong key's 403. | `COLLECTOR_KEY` and `PARTNER_KEY` take a comma list (`new,old` while rotating), each compared in constant time. Startup refuses any key under 32 characters or with fewer than 10 distinct ones. Unset, missing and wrong keys all get the same 403. Audit lines name the key by fingerprint. | `key_rotation`, `key_failures_are_uniform`, `weak_keys_stop_startup`, `production_mode`. |
| FU8 | Medium | GET requests had no rate limit, so a read flood could pin the backend (`/api/city` took about 47 ms of CPU on 10,000 rows); a malformed POST body was rejected before the guard and cost nothing. | Every routed request is charged (B5): GETs other than the code lookup have their own bucket, burst 60, then 2 per second; malformed bodies are charged too (FU2). A call that reaches the backend without the edge (no `X-Forwarded-For`, or several entries) logs `event=edge_bypass`. | `read_bucket`, `malformed_body_is_charged`, `bucket_keys`, `trust_proxy_and_edge_bypass`; the burst check of `scripts/smoke.sh` through the edge. |
| FU9 | Low | `/api/health` returned a constant, so a read-only or full data volume stayed healthy while every write failed; a write lock held past the busy timeout gave a bare 500. | Health opens the database read-write, takes a write lock and rewrites the header in a rolled-back transaction, and needs 50 MB free; otherwise 503 with `db_busy`, `db_unwritable` or `disk_low`. Any request that hits a locked, read-only or full database gets 503 with `Retry-After: 1`. The compose healthchecks use it. | `health_checks_writes_and_space`, `db_busy_is_503`; the healthchecks by hand (the edge check fails with the frontend stopped). |
| FU10 | Medium | Frontend: the visual QA found 13 rendering defects (one high: the mobile Confirm bar was not pinned); the role reviews found sample data shown as live, a redeemed code lost once its sheet closed, contrast below AA, errors frozen in the old language and no error boundary; the final re-check found that a malformed saved-codes or theme value in browser storage broke the page. | All 13 defects fixed; a sample-data badge; the «کدهای من» list, validated on read and kept in step across tabs; AA colour tokens; errors stored as keys; `error.tsx` and `not-found.tsx`; a 15 s request timeout; only `light` and `dark` accepted from storage. Details in [docs/UI_UX.md](docs/UI_UX.md). | `npx tsc --noEmit` exit 0 and a production build. The capture script: 60 captures, 0 issues, before the re-check fixes; those were checked with `tsc` and a logic check of the code filter. |

Not run in this pass: the CI workflows (they run on GitHub), a restore drill, load tests and DAST. The red-team skills and attack-script replays were skipped on purpose (see below).

## Skipped and remaining

- **Blocked by the safety classifier.** Three pieces were skipped rather than retried on another model: loading the red-team-tools skill, loading the red-team-tactics skill, and a dedicated agent that replays attack scripts against the old and new code. The abuse cases they targeted are covered by the regression suite.
- **No real user authentication.** The app still has one demo user. Production needs real sign-in, per-user balances and quotas, and a collector role.
- **Rate limits are per process.** That is fine for one instance. Use a shared store such as Redis if the API scales out.
- **Docker:** both images were built and the full stack ran on 2026-10-22 (smoke 20 of 20). A restore drill on a real backup and docker-bench-security on a production host are not done.
- **Clean-clone frontend image:** fixed. The Dockerfile creates `frontend/public` before the build, so `COPY --from=build /app/public` works on a fresh clone.
- **Web history page:** it asks for the newest 200 pickups (`limit=200`, the API maximum) and has no load-more, so older pickups are reachable only through the API with the `before` cursor.
- **Host-local callers** can reach the loopback-bound backend directly with a forged `X-Forwarded-For`. Only processes on the host can do this. A call with no header or several entries logs `event=edge_bypass`; a single forged entry is not detected.
- **CI has not run on GitHub yet.** The first run on pull request 2 is the check of every job.
- **No frontend test runner.** The frontend is checked by the type checker, the build, the capture script and a manual checklist.

## How to verify

```bash
cd backend && python3 -m venv .venv && .venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python test_api.py                       # prints "ok"
cd ../frontend && npm ci --ignore-scripts && npx tsc --noEmit && npm run build && npm audit --audit-level=high   # clean since next 16.3.8
cd .. && export DEMO_MODE=1 && docker compose up -d --build --wait   # production: leave DEMO_MODE unset, set COLLECTOR_KEY and PARTNER_KEY (32+ chars, 10+ distinct)
scripts/smoke.sh full                              # 20 checks; expects the demo flag that DEMO_MODE says
python3 scripts/threat_intel.py                    # dependency advisories and CISA KEV matches
```
