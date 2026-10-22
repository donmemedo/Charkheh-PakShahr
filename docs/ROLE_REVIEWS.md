# Role reviews

Five reviews of SabzBank ran on branch `audit/followups` before the follow-up pass: a product owner, a tech lead, a red team working at design level (no attack code, no traffic), a blue team and QA. Together they made 60 suggestions; their own triage marked 31 to do now, 27 to defer and 2 to reject. This document lists every item in one table per role, with what actually happened to it, checked against the code and the builder reports. The review texts themselves are not in the repository; the items below are paraphrased.

Disposition legend:

| Label | Meaning |
|---|---|
| **Done** | Done in this pass (backend, infrastructure, frontend or docs) on this branch |
| **Done, part** | The safe part is done; the rest is deferred, for the reason given |
| **Deferred** | Not started, with the reason and where it is planned |
| **Rejected** | Considered and not adopted, with the reason |

Phases A to E are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Product owner

The product owner's view: the demo is credible, but four things stand between it and a pilot: real weighing, real accounts, attributable partners, and a points economy whose value and success measures are defined.

| Id | Item | Priority | Disposition | Where, or why |
|---|---|---|---|---|
| PO-01 | Production `complete` still invents the weight; there is no real weighing path | P0 | Deferred | Phase A. Needs the tolerance and dispute rule (PM) and the collector identity choice (tech lead) |
| PO-02 | The pilot needs verified citizen identity and a per-user ledger | P0 | Deferred | Phase B. Founder decision on sign-in and SMS budget; a schema change across all tables |
| PO-03 | The city page and district league show synthetic numbers labelled live | P1 | Done | A static «داده نمایشی» / "Sample data" badge on the city page and the league card ([UI_UX.md](UI_UX.md), section 7) |
| PO-04 | A redeemed code cannot be recovered after the sheet closes | P1 | Done | A «کدهای من» list kept in this browser (newest 20); the server-side list comes with accounts (phase B). The suggested CSP check on the storage read does not apply: CSP does not govern `localStorage` |
| PO-05 | Nothing stops requests outside the pilot area or in a slot already past, and a missed pickup stays "next" forever | P1 | Done, part | The stale next pickup is fixed (`state()` filters `day >= today`; the sweep cancels after 7 days). Pilot districts and a booking lead time need the district list and an operations rule |
| PO-06 | The points economy has no value anchor against the pilot's assumptions | P1 | Deferred | Phase E. A commercial decision for the founder |
| PO-07 | One shared partner key, no partner identity on a spend, no partner screen, real brand names as placeholders | P1 | Deferred | Phase C. Needs partner terms (founder) and a key scheme (tech lead) |
| PO-08 | Pilot success cannot be measured: targets have no formula, data source or owner | P1 | Deferred | Phase E. Needs accounts first |
| PO-09 | Persian copy defects against the vocabulary reference, and missing empty states | P2 | Done | Theme and language names in Persian, «کد پاداش شما», the two address messages, the league wording, empty states on both History tabs, and a Persian separator next to digits |
| PO-10 | Retention mechanics are cosmetic: tiers grant nothing, missions run out in one sitting | P2 | Deferred | Perks cost points and thresholds need measured pilot volumes |
| PO-11 | No notifications: a citizen learns of a weighing only by opening the app | P2 | Deferred | Phase D. Needs verified phone numbers and a provider |
| PO-12 | Packaging order: PWA first, then collector and partner screens, then Android, iOS out of the pilot | P3 | Deferred | Adopted as the order in [ROADMAP.md](ROADMAP.md) |

## Tech lead

The tech lead's view: the money path is sound (atomic statements behind predicates, tested under concurrency). The debt was around it: no schema versioning, no CI, a health check that never touched the database, no backup, a mocked collector contract, and docs that drifted. Do not split the file and do not add heavy tools yet.

| Id | Item | Priority | Disposition | Where, or why |
|---|---|---|---|---|
| TL-01 | Overdue scheduled pickups never expire and mask the real next pickup | P1 | Done | `state()` (day, slot, id order from today), `expire_overdue()` and the lifespan task; sections `upcoming_pickup`, `overdue_expiry`, `lifespan_startup` |
| TL-02 | A busy database gives an opaque 500, health never touches the database, state is not one snapshot | P1 | Done | `db_unavailable()` 503, `health()` write probe and free space, `BEGIN` in `state()`; sections `db_busy_is_503`, `health_checks_writes_and_space`, `state_reads_one_snapshot` |
| TL-03 | No CI and no dependency-update automation | P1 | Done | `.github/workflows/ci.yml`, `.github/dependabot.yml` |
| TL-04 | No backup or restore path, `synchronous=NORMAL`, no log rotation | P1 | Done, part | `synchronous=FULL`, `ops.py backup`, the compose `ops` profile, json-file rotation. The off-host copy is an operator task ([OPERATIONS.md](OPERATIONS.md)) |
| TL-05 | No migration mechanism, no constraints, award-once only in app code | P1 | Done, part | `MIGRATIONS` ladder on `user_version` and the `txns_once` unique index. `CHECK`, `FOREIGN KEY` and `user_id` come with the accounts rebuild (phase B) |
| TL-06 | Production mode still runs mocked behaviour: random weights, a synthetic city panel labelled live, a hard-coded user | P2 | Deferred | Weights: phase A. User: phase B. The sample-data label is done (PO-03) |
| TL-07 | Route `/api` from Caddy straight to FastAPI; real healthchecks for frontend and edge | P2 | Done, part | Frontend and edge healthchecks with a `service_healthy` chain are done. The direct `/api` route was rejected for now: it changes the verified `X-Forwarded-For` trust chain |
| TL-08 | `SECURITY_AUDIT.md` is stale against the code | P2 | Done | Corrected to this branch, with a section for the follow-up pass of 2026-10-16 to 2026-10-22 |
| TL-09 | Uncovered endpoints, order-dependent tests, nothing runs them | P2 | Done | `test_api.py` rewritten: 47 isolated sections, shuffleable; CI runs it |
| TL-10 | Unversioned API, no response models, hand-copied TypeScript types, limits duplicated across tiers | P2 | Deferred | Settle with the first external client (phases A and C): `/api/v1` for collector and partner routes, limits served in the catalogue |
| TL-11 | When to split `main.py` | P3 | Deferred | Triggers and order in [BACKEND.md](BACKEND.md). `init_db()` stays at import on purpose (the suite and the benchmark depend on it) |
| TL-12 | Do not add Prometheus or OpenTelemetry, Alembic or SQLAlchemy, Redis, Celery or a pytest rewrite now | P3 | Rejected | Agreed; the trigger for each is in [BACKEND.md](BACKEND.md) |

## Red team (design level)

The red team's view: the settled findings hold. What remains is the trust model around the two shared secrets, the shape of the points economy, and observability. The worst case was a leaked collector key minting points from declared weights with nothing recording who did it.

| Id | Item | Priority | Disposition | Where, or why |
|---|---|---|---|---|
| RT-01 | Collector authority is one static key and payout is declared weight with jitter, not a measurement | P1 | Deferred | Phase A (measured weights), phase C (per-party credentials). RT-02 and RT-09 shrink the blast radius now |
| RT-02 | Cap what one complete can mint; complete ignored the pickup date | P1 | Done, part | `MAX_PICKUP_KG = 50` per material and in total (`PickupIn`); 409 for a future day outside demo. A daily mint ceiling waits for a product number (phase E) |
| RT-03 | Reward codes are bearer secrets: logged in clear, stored in clear, and the lookup was open | P1 | Done, part | Logs show `code#<sha256[:8]>`; the lookup needs `X-Partner-Key`. Hashing codes at rest is a phase B decision |
| RT-04 | One partner key for every partner; a spend never checks whose reward it is | P2 | Deferred | Phase C |
| RT-05 | Points and codes have no lifecycle: no expiry, hold, stock, velocity limit or idempotency | P2 | Deferred | Phases B and E; product and partner decisions |
| RT-06 | Reads unbounded, aggregates recomputed per call, logs and bucket keys unbounded | P2 | Done, part | A read bucket for GETs, hashed fixed-size non-IP bucket keys, log rotation. A short memo around `state()` was skipped until the read bucket proves too loose |
| RT-07 | Rate-limit identity is the IP alone (carrier NAT, CDN topology) | P2 | Deferred | Per-account keys need accounts (phase B); the topology needs a hosting decision |
| RT-08 | Key-guarded endpoints sit on the public origin over plain HTTP; `X-Forwarded-For` trusted from any peer | P2 | Deferred | Needs the hostname, the TLS owner and who calls the privileged APIs. Listed in [SECURITY.md](SECURITY.md) residual risks |
| RT-09 | No actor on value events, no database uniqueness, an unconditional seed, logs that hide the signal | P2 | Done, part | Audit event lines, the `txns_once` index, the seed only in demo mode. Actor columns come with phase A and C credentials; warnings for code-path 404s wait for an alerting pipeline |
| RT-10 | What real authentication must not get wrong | P2 | Deferred | The checklist in [SECURITY.md](SECURITY.md); built in phase B |
| RT-11 | Repo and supply-chain hygiene: untracked notes one `git add -A` from publication, install scripts, no CI | P3 | Done | `.gitignore` additions, `npm ci --ignore-scripts` (CI and the frontend Dockerfile), CI |
| RT-12 | Key-check errors fingerprinted the deployment | P3 | Done | One 403 `forbidden` for unset, missing and wrong keys; the reason only in the log and the startup line |

## Blue team

The blue team's view: a ledger with no recovery path was the worst gap, followed by the absence of the log lines that the incident runbooks need.

| Id | Item | Priority | Disposition | Where, or why |
|---|---|---|---|---|
| BT-01 | Online backup, off-host copy and a restore drill | P1 | Done, part | `ops.py backup`, the `ops` profile, restore steps in [OPERATIONS.md](OPERATIONS.md). The off-host copy and the drill are operator tasks |
| BT-02 | Business-event log lines so key misuse and points inflation are detectable | P1 | Done, part | `audit()` events for every value and security event, the startup line, `edge_bypass`. WARNING for code-path 404s and 422 bursts, and a points alarm threshold, wait for an alerting pipeline |
| BT-03 | Make the logs safe to keep: hash codes, bound line length, rotate | P1 | Done | `log_path()`, quoted and capped ip, json-file rotation; section `log_hygiene` |
| BT-04 | Addresses are visible to every visitor | P1 | Deferred | The real fix is per-user scoping (phase B) |
| BT-05 | Define retention and purge addresses of finished pickups | P2 | Deferred | The window is a product and legal decision; the purge needs backups first (now in place) |
| BT-06 | Ledger reconciliation and a health check that proves the database is writable | P2 | Done | `ops.py check` (five invariants), `health()`; sections `ops_check`, `health_checks_writes_and_space` |
| BT-07 | Rotatable keys without downtime; secrets out of git | P2 | Done | Comma-list keys, strength check at startup, `.env` in `.gitignore`; sections `key_rotation`, `weak_keys_stop_startup` |
| BT-08 | CI, an update bot, a secret scan, a refreshed audit doc | P2 | Done | CI, Dependabot, gitleaks, and `SECURITY_AUDIT.md` corrected to this branch |
| BT-09 | Close two rate-limit gaps: malformed-JSON POSTs and GETs | P2 | Done | The 422 handler charges and CSRF-checks; the read bucket; sections `malformed_body_is_charged`, `read_bucket` |
| BT-10 | Structural limits on minted points: measured weight, a per-pickup cap, partner-scoped keys | P2 | Deferred | The per-pickup cap landed through RT-02; measured weight is phase A, partner keys phase C |
| BT-11 | Harden the edge and the containers: TLS, a privileged-route allowlist, an edge log, healthchecks | P2 | Done, part | Healthchecks, a non-root read-only edge, a read-only frontend. TLS, the allowlist and the edge log need a hostname, partner addresses and a retention policy |
| BT-12 | Do not add a central log or metrics stack or a hash-chained ledger | P3 | Rejected | Agreed: grep rules over the container logs plus the scheduled ledger check cover the same signals for one instance |

## QA

QA's view: the backend suite was strong on races but flaky on a loaded host, pinned no exact boundary, and the frontend had no tests. Reading the frontend found real defects: dark-mode contrast, a code lost when the sheet closes, a wrong next-pickup tie-break, a Copy button that claimed success, and a stale mission card.

| Id | Item | Priority | Disposition | Where, or why |
|---|---|---|---|---|
| QA-01 | Rate-limit tests depended on wall-clock refill; "today" was pinned at import | P1 | Done | `REFILL = 0` for bursts, the fake `clock` for refill, "today" read at use |
| QA-02 | Boundary values were not pinned | P1 | Done | The boundary sections listed in [QA_PLAN.md](QA_PLAN.md) |
| QA-03 | Branches, transitions and endpoints no assertion touched | P1 | Done | `status_action_matrix`, `complete_payout`, `complete_races`, `read_endpoints`, `db_busy_is_503` and more |
| QA-04 | Primary button and small coloured text fail WCAG AA contrast | P1 | Done, part | Token-level colour fixes; every changed pair passes AA (ratios in [UI_UX.md](UI_UX.md), section 2). The suggested token contrast test waits for a frontend test runner |
| QA-05 | A redeemed code is shown once and lost on dismissal or a dropped response; no idempotency | P1 | Deferred | The browser-kept list is done (PO-04); a server-side list and an idempotency key are phases B and E |
| QA-06 | Register of requirements that cannot be tested today, and sample-data gaps | P1 | Deferred | Carried in [QA_PLAN.md](QA_PLAN.md) and the phases; the sample-data label is done (PO-03) |
| QA-07 | An automation pyramid and CI sized for the project | P1 | Done, part | CI and the compose smoke are done. Frontend unit and end-to-end tests are the next layers in [QA_PLAN.md](QA_PLAN.md) |
| QA-08 | Four small defects: next-pickup tie-break, false "Copied", mission choice range, a stale mission card after 409 | P2 | Done | Backend: the `day, slot, id` order and the choice range (422). Frontend: Copy says «کپی شد» only after a copy happened, and a 409 flips the mission card to «انجام شد» |
| QA-09 | Failure handling: errors frozen in the old language, cache replaced by an error offline, non-JSON 200s, hung requests, no error boundary | P2 | Done, part | Errors stored as keys and translated at render, cached data kept on a failed refresh, non-JSON 200s rejected, a 15 s timeout, `error.tsx` and `not-found.tsx`. The offline notice over cached data is deferred |
| QA-10 | Accessibility: an unnamed dialog, lost focus, no skip link, English tokens in Persian labels, a theme flash, the 320 px tab bar | P2 | Done | Named dialogs, focus return, a skip link, Persian control names, no theme flash, the 320 px tab bar ([UI_UX.md](UI_UX.md), section 8) |
| QA-11 | Pickup rules without acceptance criteria: past slots, cap semantics, duplicates, stale rows, the weight ceiling, clock skew | P2 | Deferred | Product decisions. Stale rows and the weight ceiling are now settled (TL-01, the 50 kg cap); the current behaviour is the baseline in [QA_PLAN.md](QA_PLAN.md) |
| QA-12 | A manual regression checklist | P2 | Done | [QA_PLAN.md](QA_PLAN.md), "Manual regression checklist" |
