# Implementation plan: from demo to pilot

This plan turns the SabzBank MVP into something a pilot can run on: real weighing, real accounts, real partners, notifications, and a points economy with measurable outcomes. It follows the implementation-planner format: the objective, the current architecture the plan builds on, then one section per phase with its objective, the files to inspect and change, the steps, the risks and edge cases, and the verification. Phases run in order A to E; each lists the decisions it needs and who owns them. Nothing here is built yet.

## Objective

Replace the four stand-ins that make the MVP a demo, without giving up the properties the audit established (atomic money path, award-once, uniform key errors, safe logs, one-command operations):

1. Points come from a collector's measurement, not a random factor.
2. Each citizen has an account, a balance and limits of their own.
3. Each partner has its own credential and sees only its own codes.
4. Citizens hear about the events that matter to them.
5. Points have a defined value, and the pilot's success can be computed from the data.

## Assumptions

- One backend process and one SQLite file stay right for the pilot's scale. The phases keep that; [BACKEND.md](BACKEND.md) names the triggers for Redis, an ORM or a queue.
- The pilot runs in Iran: phone numbers are the identity, SMS goes through an Iranian provider, and the web app (later a PWA) is the main channel ([ROADMAP.md](ROADMAP.md)).
- The settled decisions are not reopened: Persian first, spring physics in the UI, `DEMO_MODE` off by default, demo flows kept working under `DEMO_MODE=1`.
- TLS terminates in front of the edge before any phase goes to real users.

## Decisions and owners

| Decision | Owner | Phase |
|---|---|---|
| Maximum deviation of the measured weight from the declared weight; what happens to a contaminated or rejected load; the dispute process and its deadline | Technical PM | A |
| Collector identity: one shared key now, per-collector credentials later, or per-collector from the start | Technical lead | A, C |
| Sign-in method and the budget for SMS one-time codes | Founder | B |
| Code length, expiry, resend cooldown and attempt limits for sign-in codes | Technical lead, with the PM for the copy | B |
| Whether reward codes are stored hashed (safer at rest) or retrievable by the citizen from the server (better recovery) | Technical lead | B |
| Retention window for addresses and logs | Founder (legal), technical lead | B |
| Partner terms, commission and the use of brand names in the catalogue | Founder | C |
| Partner credential scheme: static per-partner keys, short-lived tokens, or mTLS on a separate listener | Technical lead | C |
| SMS provider and cost per message; message triggers and wording | Founder; technical PM | D |
| Value of a point; reward prices; whether points expire or are held before they can be spent; a daily mint ceiling | Founder | E |
| Pilot metrics: formula, data source and owner for each target | Founder, technical PM | E |

## Current architecture relevant to the plan

- `backend/main.py` is one module. `POST /api/pickups/{pid}/complete` reads no body: it multiplies the declared kg by `random.uniform(0.9, 1.1)` in every mode, overwrites `items` with the result and credits `estimate(items)`.
- There are no users. `pickups`, `txns`, `missions_done` and `codes` have no owner column; balance is `SUM(points)` over all of `txns`; `missions_done` is keyed by mission id; `PICKUPS_PER_DAY` is global; the name and district are constants.
- The schema is versioned by `PRAGMA user_version` with an append-only `MIGRATIONS` list (version 2 today). Each step runs under `BEGIN IMMEDIATE` and commits with its version.
- The guards already in place for cookie sessions: POST needs `application/json`, `Sec-Fetch-Site: cross-site` is refused, both before the rate-limit charge.
- Keys: `COLLECTOR_KEY` and `PARTNER_KEY`, each a comma list for rotation, checked in constant time by `require_key()`, which returns the key's fingerprint for the audit line.
- Reward codes are stored in clear; the frontend keeps a citizen's codes in the browser (newest 20, `sabz:codes`) until the server can list them.
- `frontend/lib/api.ts` keeps a module-level GET cache keyed by path, cleared by `refresh()` after every mutation.
- Tests: `backend/test_api.py`, 47 isolated sections; `scripts/smoke.sh` against a running stack; CI runs both.

---

## Phase A: real collector weighing

**Objective.** A completed pickup pays for what the collector measured, within a rule the product owner set. The demo path keeps working.

**Files to inspect.** `backend/main.py` (`complete_pickup`, `PickupIn`, `estimate`, `MIGRATIONS`), `backend/ops.py` (`INVARIANTS`), `backend/test_api.py` (`complete_payout`, `complete_future_day`, `complete_races`, `status_action_matrix`, `production_mode`, `business_events`), `frontend/app/page.tsx` (the demo "Simulate delivery" call).

**Files to change.** `backend/main.py`, `backend/test_api.py`, `docs/API.md`; `backend/ops.py` only if a new column needs an invariant.

**Steps.**

1. Add a request model `CompleteIn` with `items` shaped like `PickupIn.items` (the five materials, each `0 <= kg <= MAX_PICKUP_KG`, total at most `MAX_PICKUP_KG`). Zero is allowed here: a material the collector rejected weighs 0.
2. Make the body required outside `DEMO_MODE` and optional in demo mode. In demo mode with no body, keep today's random draw, so the dashboard button and the screenshots work unchanged.
3. Validate the measurement against the booking: every measured material was declared, and each measured kg is at most declared kg times the tolerance (`MAX_OVER_DECLARED`, for example 1.1; the PM sets it). Above it: 422 with a message naming the material.
4. Keep the declared weights. Migration version 3: `ALTER TABLE pickups ADD COLUMN declared TEXT`, back-filled with `items` for scheduled rows; `create_pickup` writes both; `complete` overwrites only `items`. Disputes then have both numbers.
5. Credit `estimate(measured)` in the same transaction as today, behind the same `status='scheduled'` predicate and the `txns_once` index.
6. Extend the `complete` audit line with the measured total and the over-declared ratio, so the operator can watch for drift.
7. Decide what a load measured at 0 kg in total means (delivered with 0 points, or a fourth status). Until decided, refuse it with 422.

**Risks and edge cases.**

- The demo must not require a body, or the citizen-side button breaks. Test both modes.
- Rounding: measured kg arrive as floats; round the total to 3 places before the cap check, as `PickupIn` does.
- A measurement for a material that was not declared (the citizen added a bag at the door): refused by step 3 until the PM says otherwise.
- `ops.py`'s `pickup_txn_unmatched` and `pickup_sum` compare credits with `pickups.points`; they keep working because `points` is still set on completion.
- Collector identity is still the shared key; the audit line's key fingerprint is the only actor until phase C.

**Verification.**

- New sections: production complete with `{"items": {"plastic": 3.0}}` on a 3 kg booking pays exactly 360 points; a missing body outside demo is 422; above the tolerance is 422 with nothing written; an undeclared material is 422; demo with no body still pays within ±10%.
- Existing sections pass unchanged: `complete_races`, `status_action_matrix`, `award_once_index`, `complete_future_day`.
- `migration_upgrades_in_place` extended to version 3 with data intact.
- `ledger-check` passes after a run of the suite's flows; `scripts/smoke.sh full` passes.

---

## Phase B: accounts

**Objective.** A citizen signs up with a phone number and a one-time SMS code. Every row belongs to a user; balances, caps and missions are per user; a session cookie carries the identity safely.

**Files to inspect.** `backend/main.py` (every handler, `guard`, `require_key`, `throttle`, `log_path`, `MIGRATIONS`, `seed`), `backend/ops.py` (`INVARIANTS`), `backend/test_api.py` (all sections that create rows; `log_hygiene`), `frontend/lib/api.ts` (the cache), `frontend/lib/i18n.tsx`, `frontend/components/shell.tsx`, `frontend/app/rewards/page.tsx` (the browser-kept code list).

**Files to change.** `backend/main.py` (probably the point to split out `security.py` and `db.py`, see [BACKEND.md](BACKEND.md)), `backend/ops.py`, `backend/test_api.py`, new frontend sign-in pages, `frontend/lib/api.ts`, `frontend/lib/i18n.tsx`.

**Steps.**

1. **Schema, migration version 4: new tables.** `users(id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL, created TEXT NOT NULL)`; `otp(phone TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0, window_start TEXT NOT NULL)`; `sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires TEXT NOT NULL)`.
2. **Schema, migration version 5: table rebuilds.** SQLite cannot add `CHECK` or `FOREIGN KEY` with `ALTER`, so rebuild `pickups`, `txns`, `missions_done` and `codes` inside the step's transaction: create `<table>_new` with `user_id INTEGER NOT NULL REFERENCES users(id)` and the constraints (`CHECK (status IN ('scheduled','delivered','canceled'))`, `CHECK (kind IN ('pickup','redeem','mission'))` plus any reversal kind phase E adds, `missions_done` primary key `(user_id, id)`), copy the rows with `user_id = 1` (a legacy user created in the same step), drop the old table, rename, recreate the indexes with `user_id` leading (`txns(user_id, ts, id)`, `pickups(user_id, status, day)`), recreate `txns_once` as `UNIQUE (user_id, kind, ref) WHERE kind IN ('pickup','mission')`, and run `PRAGMA foreign_key_check` before the commit. Set `PRAGMA foreign_keys=ON` in `db()` (it is per connection).
3. **Sign-up and sign-in.** `POST /api/auth/code {"phone": "…"}` sends a code; `POST /api/auth/verify {"phone": "…", "code": "…"}` creates the user on first use and a session. The phone is in the body, never in the path, because the access log records paths. Store the code as a keyed hash (HMAC with a server secret, since a 6-digit code is trivial to brute-force from a plain hash), with an expiry of minutes, at most a few attempts, a resend cooldown, and per-phone and per-IP send caps. Answer the same way whether or not the number is known.
4. **Sessions.** A 256-bit random token in a cookie with `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`; the server stores only its sha256. Expire it; `POST /api/auth/logout` deletes it. Keep the existing JSON content-type and `Sec-Fetch-Site` checks, and tighten the latter to require `same-origin` (and an `Origin` match) on cookie-authenticated POSTs. Collector and partner APIs never accept the cookie.
5. **Scope every query.** A dependency resolves the session to a `user_id`; every handler adds `WHERE user_id = ?`. Balance and the redeem statement sum only the caller's rows; the daily cap counts the caller's pickups; missions are once per user; the pagination cursor's subquery also filters by `user_id`. `complete` (collector) and the partner endpoints stay key-authenticated and act on any user's row by id.
6. **Per-account rate limits.** Key the write bucket on the user id when there is a session, keep the IP bucket as a coarser backstop, and give the sign-in endpoints their own stricter bucket.
7. **Reward codes.** Apply the decision: either store `sha256(code)` and look codes up by hash (the citizen keeps the plaintext, as the browser list does today), or keep the plaintext and add `GET /api/me/codes` for the owner. Either way, link the code to its debit (`codes.txn_id`).
8. **Frontend.** Sign-in and sign-up screens with the vocabulary of the Persian UX-writing reference: «ثبت‌نام»، «ورود»، «شماره موبایل»، «کد تایید»، «پیامک»، «حساب کاربری»; a wrong code reads «کد تایید نادرست است». Clear the `api.ts` cache and the browser code list on login and logout, or key them by user. A first-run screen shown once.
9. **Demo.** `DEMO_MODE=1` signs every visitor in as the legacy demo user, so the demo needs no SMS.
10. **ops.py.** Add a per-user `negative_balance` invariant (`SELECT user_id FROM txns GROUP BY user_id HAVING SUM(points) < 0`) and a `foreign_keys` check.

**Risks and edge cases.**

- The table rebuild runs on the live ledger. Back up first; the step must be one transaction; test it on a copy of a real database, including a version-2 database with a duplicate credit (it must fail before the rebuild).
- SMS pumping (toll fraud): attackers trigger codes to premium numbers. Per-phone, per-IP and global daily caps, and number-format validation for Iranian mobiles.
- Enumeration through different responses or timings for known and unknown numbers.
- `INTEGER PRIMARY KEY` ids are guessable; with `user_id` in every `WHERE`, a guessed id of another user's pickup gives 404, not someone else's data.
- The client cache and the browser code list leaking between users on a shared device.
- Address personal data: return it only to its owner; erase by blanking the field (ledger references must stay valid).
- Two tabs, one signed out: the cookie is shared, so the stale tab's next call gets 401; the UI must handle it.

**Verification.**

- Two accounts have independent balances, caps, missions and pickup lists; every GET returns only the caller's rows.
- The race sections (`redeem_races`, `complete_races`, `daily_cap`) pass per user, and across two users at once.
- Sign-in: wrong code 5 times locks out; an expired code is refused; the response for an unknown number equals that for a known one; no phone number or code appears in any log line (extend `log_hygiene`).
- Cross-site POST with the cookie is refused (403); a POST without `application/json` is 415.
- The migration test upgrades a version-2 database to 5 with every row owned by the legacy user, and `foreign_key_check` is empty.
- `ledger-check` passes per user.

---

## Phase C: partner onboarding

**Objective.** Each partner has its own credential, can spend only codes for its own rewards, and has a screen to do it. Spends are attributable.

**Files to inspect.** `backend/main.py` (`REWARDS`, `require_key`, `code_lookup`, `code_use`, `env_keys`), `backend/test_api.py` (`code_lookup_and_use`, `key_rotation`, `key_failures_are_uniform`), `docker-compose.yml` (the edge), the frontend app directory.

**Files to change.** `backend/main.py`, `backend/test_api.py`, `docs/API.md`, `docs/OPERATIONS.md`, a new `frontend/app/partner/page.tsx`.

**Steps.**

1. Give every reward a stable `partner` id (today `REWARDS[].partner` holds localized names only).
2. Replace `PARTNER_KEY` with a per-partner map, for example `PARTNER_KEYS="cafe=<key>|<old key>,metro=<key>"`, parsed by an extension of `env_keys()` with the same strength rules. `require_key()` returns the partner id along with the fingerprint.
3. `code_use` refuses (403, the same uniform body) when the code's reward belongs to another partner, and writes `codes.used_by` (migration: `ALTER TABLE codes ADD COLUMN used_by TEXT`). `code_lookup` likewise shows only the partner's own codes.
4. Audit lines carry `partner=<id>`.
5. A partner screen as a PWA route: paste or scan a code, see the reward, press spend. The partner key never goes into a citizen bundle; the screen asks for it and keeps it in memory, or (better, the tech lead's choice) the partner signs in and gets a short-lived token.
6. The edge: serve `/api/codes/*` and `/api/pickups/*/complete` on a separate listener or behind an IP allowlist or mTLS, so a leaked key is useless from elsewhere (this needs the hostname and partner addresses).
7. One SQL report: used codes and points per partner per month.
8. Until agreements exist, mark brand names in the demo catalogue as examples.

**Risks and edge cases.** A partner rotating its key must not take others down (the per-partner list handles it). A code redeemed before the migration has no partner check data beyond its reward id; the reward-to-partner map covers it. Disputes (customer says refused, partner says never presented) need `used_by` and the audit line. Partner credentials get their own rate-limit bucket, not the shop's IP.

**Verification.** Partner A spending partner B's code gets 403 and nothing changes; A's own code works once, then 409; `used_by` is set; rotation of A's key leaves B working; the monthly report query returns the expected counts; `key_failures_are_uniform` still holds.

---

## Phase D: notifications

**Objective.** A citizen learns that a pickup was weighed and is reminded the evening before a pickup, by SMS («پیامک»). Nothing else in the first version: no push, no e-mail, no marketing.

**Depends on** phase B (verified phone numbers) and phase A (the weighed event).

**Files to inspect.** `backend/main.py` (`complete_pickup`, `lifespan`, `expire_hourly`), `backend/ops.py`.

**Files to change.** `backend/main.py` (an outbox and a sender loop), `backend/test_api.py`, `frontend/lib/i18n.tsx` (an opt-out setting; any later in-app list is «اعلان‌ها»).

**Steps.**

1. An `outbox(id, user_id, kind, body, created, sent, attempts, last_error)` table, written in the same transaction as the event (the complete credit), so a message is never lost and never sent for a rolled-back credit.
2. A lifespan loop, like `expire_hourly`, that sends pending messages through the provider with retries and backoff, and marks them sent. A send failure never touches the ledger.
3. The evening reminder: the hourly sweep enqueues one message per pickup scheduled for the next day, once (a unique index on `(kind, ref)` in the outbox).
4. Opt-out per user; count messages per user per month for the cost report.
5. Message text from the PM, in Persian, following the vocabulary reference.

**Risks and edge cases.** Duplicate sends after a crash between send and mark (make the provider call idempotent if it supports a client id, else accept rare duplicates). Provider outages (the outbox absorbs them). Night-time sends (respect quiet hours). Cost runaway (a daily global cap). Several workers would each run the loop: claim rows with an `UPDATE … WHERE sent IS NULL AND claimed IS NULL` predicate.

**Verification.** A completed pickup produces exactly one outbox row in the same transaction; a rolled-back complete produces none; a failing provider leaves the credit intact and retries; an opted-out user gets nothing; no phone number appears in log lines.

---

## Phase E: the points-economy anchor and pilot metrics

**Objective.** A point has a defined value, the reward prices follow from it, value leaves the system only under rules the founder set, and every pilot target can be computed from the data.

**Files to inspect.** `backend/main.py` (`MATERIALS`, `REWARDS`, `MISSIONS`, `TIERS`, `city`, `redeem`), `backend/ops.py`, the reviews in [ROLE_REVIEWS.md](ROLE_REVIEWS.md) (PO-06, PO-08, PO-10, RT-05).

**Files to change.** `backend/main.py`, `backend/ops.py`, `backend/test_api.py`, `docs/BACKEND.md` (the constants table).

**Steps.**

1. **Anchor.** Today the reward catalogue implies a value per kilogram of waste that nobody has checked against the pilot's cost and revenue assumptions. The founder sets the value of a point; points per kg per material and every reward cost are derived from it and written down with the reason.
2. **Lifecycle rules**, as decided: points from a complete held for a period before they can be spent; a reversal entry kind (`txns.kind = 'reversal'`) so fraud can be clawed back in the ledger rather than by editing rows; code expiry (`codes.expires`) enforced in lookup and spend; per-reward stock and per-account limits; an idempotency key on redeem so a retried request returns the same code.
3. **Mint ceiling.** A daily ceiling on points minted per collector and in total, with an audit WARNING when it is reached.
4. **Metrics.** For each pilot target: a formula, the SQL that computes it, its owner and its review cadence. Candidates: active households, pickups per household per month, repeat rate, kg per material, contamination rate (from phase A's rejected loads), points minted versus redeemed, partner spends.
5. **City dashboard.** Decide which KPIs become live and from which source. Add a `synthetic` flag to `/api/city` for the rest, so the UI labels each figure correctly.

**Risks and edge cases.** Changing prices after launch breaks citizen trust: version the catalogue and announce changes. A hold period confuses users unless the wallet shows "pending" separately. Expiry needs a notice (phase D). Metrics computed from logs are fragile; compute from the ledger.

**Verification.** A held credit is not spendable until the hold ends (fake clock); a reversal restores the balance and the ledger invariants still hold; an expired code is refused by lookup and spend; a retried redeem with the same idempotency key returns the same code and debits once; each metric query has a test with a fixture of known answer.
