# Security model

This document puts the SabzBank security model in one place: the trust boundaries, a control map from each threat to the control that closes it, the code that implements it and the test that proves it, the risks that remain open or are accepted, and a design checklist for the real authentication that will replace the single demo user. The audit history (the original threat tree, findings B1 to B16, N1 to N16, I, F, P and FP) is in [../SECURITY_AUDIT.md](../SECURITY_AUDIT.md). That file is the original audit, corrected to this branch, with a section for the follow-up pass.

## Assets and attacker goals

| Asset | Why it matters |
|---|---|
| The points ledger (`txns`) | Points buy rewards with real value at partners |
| Reward codes (`codes`) | Bearer credentials: whoever holds one can have a partner spend it |
| `COLLECTOR_KEY` | Mints points: completes any scheduled pickup |
| `PARTNER_KEY` | Spends any code |
| Pickup addresses | Personal data, typed by citizens |
| Availability | Citizens and partners rely on the service |

The attacker wants rewards without earning points, to deny service, or to read personal data. The demo user model means there is no account to take over yet.

## Trust boundaries

```text
 Internet ──► edge (Caddy, :WEB_PORT) ──► frontend (Next.js, no published port) ──► backend (FastAPI) ──► SQLite volume
   untrusted     overwrites X-Forwarded-For    nonce CSP, /api rewrite                 guard, keys, ledger     uid 10001
                                                passes headers through                  trusts rightmost XFF
 Host ──► backend 127.0.0.1:API_PORT   (host-local processes are trusted; they can forge X-Forwarded-For)
 Collector and partner clients ──► edge ──► … ──► backend   (shared-secret headers, plain HTTP in compose)
```

Details per boundary are in [ARCHITECTURE.md](ARCHITECTURE.md), "Trust boundaries".

## Control map

Code locations are functions in `backend/main.py` unless another file is named. Tests are section names in `backend/test_api.py`, or checks in `scripts/smoke.sh`.

| Threat | Control | Where | Test |
|---|---|---|---|
| Citizen completes their own pickup to mint points | `DEMO_MODE` off unless set; outside demo, `X-Collector-Key` required | `complete_pickup`, `require_key` | `production_mode`, `key_failures_are_uniform` |
| A collector key completes a pickup before its day | 409 when the day is ahead, outside demo | `complete_pickup` | `complete_future_day` |
| One complete mints a huge amount | 0.5 to 50 kg per material, 50 kg total; payout is the estimate of declared kg ±10% | `PickupIn`, `complete_pickup` | `kg_bounds`, `complete_payout` |
| Pickup farming | 5 pickups per Tehran day, counted under `BEGIN IMMEDIATE` | `create_pickup` | `daily_cap`, `daily_cap_resets_at_tehran_midnight` |
| Paid twice for one pickup or mission | Status-predicated `UPDATE`; `INSERT OR IGNORE`; unique index `txns_once` | `complete_pickup`, `answer`, `MIGRATIONS` | `complete_races`, `status_action_matrix`, `missions`, `award_once_index` |
| Overspend by racing redeems | Balance check and debit in one `INSERT … SELECT … WHERE` | `redeem` | `redeem_races`, `redeem_at_exact_balance` |
| Reading the answer key from a wrong answer | The answer index is returned only on success; the catalog drops it | `answer`, `catalog` | `missions`, `read_endpoints` |
| Guessing or reusing a reward code | 72-bit codes; lookup and spend need `X-Partner-Key`; single-use `UPDATE … WHERE used IS NULL`; lookups on the strict bucket | `redeem`, `code_lookup`, `code_use` | `code_lookup_and_use` |
| Key guessing, timing, deployment fingerprinting | Constant-time compare against every key; one 403 for unset, missing and wrong; weak keys stop startup | `require_key`, `env_keys` | `key_failures_are_uniform`, `weak_keys_stop_startup`, `key_rotation` |
| Cross-site request forgery (matters once cookies exist) | POST needs `application/json`; `Sec-Fetch-Site: cross-site` is 403; checked before the charge; malformed bodies too | `guard`, `invalid` | `csrf_guards`, `malformed_body_is_charged` |
| XSS and clickjacking | Nonce CSP with `'strict-dynamic'`, `object-src 'none'`, `frame-ancestors 'none'`; `X-Frame-Options: DENY`; nosniff | `frontend/proxy.ts`, `frontend/next.config.ts` | `scripts/smoke.sh full` (fresh nonce per request, nonce on the script tags, directives, headers) |
| Request flooding | Per-client token buckets, write and read; IPv6 per /64; non-IP keys hashed; bounded key table | `throttle`, `charge`, `bucket_key` | `rate_limit_burst`, `rate_limit_refill`, `read_bucket`, `bucket_keys` |
| Dodging the limiter with a forged `X-Forwarded-For` | The edge overwrites the header; the backend reads the rightmost entry; uvicorn `--no-proxy-headers`; `edge_bypass` warning | `docker-compose.yml` (`edge`), `client_ip`, `charge`, `backend/Dockerfile` | `trust_proxy_and_edge_bypass`; smoke "12 POSTs with forged X-Forwarded-For still hit 429" |
| Oversized bodies | 413 above 16 KiB by header or by streamed count; Next buffers at most 16 KB | `BodyLimit`, `frontend/next.config.ts` | `body_size_limit` |
| Huge ids and unbounded listings | Bounded `Path` and `Query`; `limit` at most 200; codes at most 40 characters | `Pid`, `pickups`, `code_lookup` | `pagination` |
| A 500 from echoing invalid input | 422 handler returns location, message and type only | `invalid` | `kg_bounds` (NaN and Infinity bodies) |
| Log forgery and secrets in logs | Paths URL-quoted and cut to 200 characters; codes as `code#<sha256[:8]>`; keys as fingerprints; audit values URL-quoted; ip quoted and capped | `log_path`, `audit`, `Observe` | `log_hygiene`, `business_events`, `access_log_and_headers` |
| Losing committed value on power loss | WAL with `synchronous=FULL` | `db`, `init_db` | `storage_settings` |
| Opaque failure under lock contention or a bad volume | 503 with `Retry-After`; readiness health with a real write and a free-space check | `db_unavailable`, `health` | `db_busy_is_503`, `health_checks_writes_and_space` |
| Ledger corruption going unnoticed | Five invariants checked from one snapshot | `backend/ops.py` `check` | `ops_check` |
| Data loss | Online, integrity-checked backups, 14 kept | `backend/ops.py` `backup`, compose profile `ops` | `ops_backup`, `ops_cli` |
| API docs exposing the surface | `/docs`, `/redoc`, `/openapi.json` only in demo mode | `app` (`openapi_url`) | `production_mode` |
| Container escape or tampering | Non-root users, read-only roots, all capabilities dropped, `no-new-privileges`, limits | `docker-compose.yml`, both Dockerfiles | `scripts/smoke.sh` (uid, read-only, non-root, healthy) |
| Supply-chain compromise | Hash-locked Python deps; `npm ci --ignore-scripts`; actions pinned by SHA, images by digest; Dependabot with a 7-day cooldown; scanners in CI | `backend/requirements*.txt`, `.github/` | CI jobs ([DEVSECOPS.md](DEVSECOPS.md)) |
| Secrets committed to git | `.gitignore` for `.env`, databases, backups and local notes; gitleaks over the full history | `.gitignore`, `.gitleaks.toml` | CI job `secrets` |

## Residual risks

Open, with the plan that addresses each:

| Risk | Why it is open | Plan |
|---|---|---|
| No user authentication. Any visitor acts as the one user: creates and cancels pickups, redeems the shared balance, sees every address | Settled MVP decision | Phase B ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)) |
| Weights are not measured: complete pays declared kg ±10% | No collector app yet | Phase A |
| One static collector key and one partner key, sent over plain HTTP through the public origin and the Next process | No TLS, hostname or listener topology decided | TLS and a privileged-route allowlist before any non-demo deploy; per-partner keys in phase C |
| Any partner key spends any partner's code; spends record no partner | One shared key | Phase C |
| Reward codes stored in clear in the database and in backups | Hashing conflicts with showing a citizen their codes from the server | Decision in phase B |
| No code expiry, no idempotent redeem (a retried redeem debits again), no stock or velocity limits | Product rules not set | Phases B and E |
| Rate limits key on the client IP only; many users behind one carrier NAT share a bucket | No account identity | Per-account buckets in phase B |
| Buckets are per process | One instance by design | A shared store when scaling out |
| Host-local processes can call the loopback backend with a forged `X-Forwarded-For`; widening `API_BIND` exposes that to the network | Compose sets `TRUST_PROXY=1`. `event=edge_bypass` catches a call with no header or with several entries; a single forged entry is not detected | Keep `API_BIND` on loopback; a trusted-proxy CIDR check if the topology changes |
| Keys live in environment variables, visible to anyone with access to the Docker daemon (`docker inspect`) | Compose has no secret store here | File-based secrets if the host is shared |
| No retention: addresses and access-log IPs are kept as long as the data and the log files | Window not decided | A purge job once the window is agreed |
| Backups are not copied off the host by anything in the repository | Operator task | [OPERATIONS.md](OPERATIONS.md) |
| The address field accepts control and bidirectional characters | Which to allow is a product decision (the field is multi-line) | Decide with the copy owner |
| 44 HIGH vulnerabilities in Debian base packages of the backend image, none with a fix | Upstream | The weekly CI run fails when a fix ships; Dependabot bumps the digest |

Accepted for this size, with the reason:

- **One SQLite file, one process.** Correct and fast enough for the pilot scale; migration paths are in [BACKEND.md](BACKEND.md).
- **413 responses and unrouted 404s are not charged** to a bucket: both are cheap rejections before routing, and a body read stops at 16 KiB.
- **`/api/health` reasons are public** through the rewrite: low-sensitivity operational information.
- **`Sec-Fetch-Site: same-site` and a missing header pass** the CSRF guard: correct while there are no cookies. Phase B tightens it.
- **Unknown fields in request bodies are ignored**, not rejected (Pydantic's default).
- **The district league and city panel are public**: they hold sample data and aggregates only.

## What real authentication must get right

A design checklist for phase B. Each item is a trap already visible in the single-user code; none is a defect while there is one user.

1. **Scope every row to its owner.** Add `user_id` to every table and every `WHERE`. Pickup ids are sequential and `cancel`, `complete` and the pagination cursor take a raw id; a cursor must not page into another user's rows. Consider non-sequential public ids.
2. **Remove global state.** Balance and redeem sum over all rows; `missions_done` is keyed by mission id alone; the daily cap is global; the district is a constant. Each becomes per user, with composite keys (`user_id, mission_id`) and per-account caps.
3. **Sessions.** A random token in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; store only its hash; expire it; delete it on logout. Keep the JSON content-type and `Sec-Fetch-Site` checks, and tighten them to require `same-origin` plus an `Origin` check. Never use cookie auth on the collector and partner APIs.
4. **The client cache.** `frontend/lib/api.ts` keeps a module-level cache keyed by path only. Clear it on login and logout, or key it by user, so a shared device never shows the previous user's balance or addresses.
5. **SMS one-time codes.** Cap sends per phone and per IP, enforce a resend cooldown, lock out after a few wrong attempts, answer the same way for known and unknown numbers, and keep phone numbers and codes out of URL paths (the access log records paths) and out of all logs. Store codes hashed with a short expiry.
6. **Rate limits by identity.** Key the buckets on the account first, keep the IP bucket as a coarser backstop, and give collector and partner credentials their own buckets.
7. **Personal data.** Return addresses only to their owner. Erase by blanking the field, not by deleting the row, so ledger references stay valid.
8. **Public aggregates.** Decide who may see `/api/city`, `/api/leaderboard` and `/api/transactions`, and set a minimum group size so a small district does not expose one household.
9. **Packaged apps.** A service worker must not cache `/api/*` (the backend already sends `no-store`); bundles carry no secrets and no plain-HTTP endpoints; app backups exclude session tokens.
