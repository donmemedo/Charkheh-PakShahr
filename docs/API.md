# API reference

This is the contract of the SabzBank HTTP API in [backend/main.py](../backend/main.py): every endpoint with its method, path, authentication, request, response, status codes and rate-limit bucket, the headers common to all calls, the error shapes, pagination, the collector and partner key headers, and curl examples for the demo and for the partner flow. It is written for client developers: the web frontend, a future collector app and partner integrations. The machine-readable OpenAPI document exists only with `DEMO_MODE=1`, at `/openapi.json` (and `/docs`, `/redoc`).

## Base URL and transport

- Browsers and external clients call the edge: `http://<host>:${WEB_PORT}` (default 3026). Next.js rewrites `/api/*` to the backend.
- Host-local tools may call the backend directly on `http://127.0.0.1:${API_PORT}` (default 8026). With compose's `TRUST_PROXY=1`, such calls have no `X-Forwarded-For`, so each logs a WARNING `event=edge_bypass` (except `/api/health`).
- Compose serves plain HTTP. The key headers below must not cross an untrusted network until TLS is in front ([SECURITY.md](SECURITY.md)).
- The API is unversioned: every route is under `/api/`.

## Common headers

| Direction | Header | When | Meaning |
|---|---|---|---|
| Request | `Content-Type: application/json` | Every POST, even with an empty or `{}` body | Without it: 415. A CSRF defense: a cross-site HTML form cannot send it |
| Request | `Sec-Fetch-Site` | Sent by browsers | `cross-site` on a POST: 403. `same-origin`, `same-site` and a missing header pass |
| Request | `X-Collector-Key` | `POST /api/pickups/{pid}/complete` outside demo mode | The collector shared secret |
| Request | `X-Partner-Key` | `GET /api/codes/{code}`, `POST /api/codes/{code}/use`, in every mode | The partner shared secret |
| Response | `x-request-id` | Every backend response except an unhandled 500 (Starlette's outer error handler answers it) | 12 hex characters; the same id is on the server's log lines for this request |
| Response | `x-content-type-options: nosniff`, `cache-control: no-store` | Every backend response except an unhandled 500 | Do not sniff; do not cache |
| Response | `Retry-After` | 429 and the database 503 | Seconds to wait: `2` for the write bucket, `1` for the read bucket and for 503 |

Request bodies are limited to 16384 bytes (`MAX_BODY`); larger ones get 413 before parsing.

## Error shapes

| Status | Body | Notes |
|---|---|---|
| 403 | `{"detail": "forbidden"}` | Unset, missing and wrong keys all look the same. Only the server log (`event=auth_fail reason=unconfigured\|missing\|mismatch`) says which |
| 403 | `{"detail": "cross-site request blocked"}` | POST with `Sec-Fetch-Site: cross-site` |
| 404 | `{"detail": "pickup not found"}` and similar | Unknown pickup, reward, code or mission. An unrouted path gives Starlette's `{"detail": "Not Found"}` |
| 409 | `{"detail": "<reason>"}` | A business rule refused the action; the reasons are listed per endpoint |
| 413 | `{"detail": "body too large"}` | Over 16384 bytes, by `Content-Length` or by counting a streamed body |
| 415 | `{"detail": "send application/json"}` | POST without a JSON content type |
| 422 | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` | Validation by the request model. The rejected input is never echoed, so a NaN, an Infinity or a lone surrogate cannot turn it into a 500 |
| 422 | `{"detail": "<message>"}` | A rule checked in the handler: the day window, and a mission choice outside the options |
| 429 | `{"detail": "too many requests"}` with `Retry-After` | The client's bucket is empty |
| 503 | `{"detail": "database unavailable, retry shortly"}` with `Retry-After: 1` | The write lock was held past the 5 s busy timeout, or the volume is read-only or full. Logged as `event=db_busy` or `event=db_error` |
| 503 | `{"ok": false, "reason": "db_busy\|db_unwritable\|disk_low"}` | Only from `GET /api/health` |

## Rate limits

Every routed request takes one token from a per-client token bucket. The client is the address seen by the edge (the rightmost `X-Forwarded-For` entry with `TRUST_PROXY=1`, else the TCP peer). IPv4 addresses get one bucket each; IPv6 clients get one bucket per /64; anything that is not an IP address is hashed.

| Bucket | Applies to | Burst | Refill | `Retry-After` |
|---|---|---|---|---|
| write | every POST, and `GET /api/codes/{code}` | 10 (`BURST`) | 0.5 per second, 30 per minute (`REFILL`) | `2` |
| read | every other GET | 60 (`READ_BURST`) | 2 per second (`READ_REFILL`) | `1` |

A POST with a malformed JSON body is CSRF-checked and charged like any other. The buckets live in the backend process; they reset on restart.

## Pagination

`GET /api/pickups` uses a keyset cursor, newest first by `(day, id)`.

- `limit`: 1 to 200, default 50. Out of range: 422.
- `before`: the `id` of the last row you already have, 1 to 2^63-1. The next page is the rows that sort strictly before it. An id that does not exist returns `[]`.

```bash
curl -s "$BASE/api/pickups?limit=2"
curl -s "$BASE/api/pickups?limit=2&before=<id of the second row>"
```

`GET /api/transactions` returns the newest 100 rows and has no cursor.

## Endpoints

| Method and path | Auth | Bucket | Success | Errors |
|---|---|---|---|---|
| `GET /api/health` | none | read | 200 `{"ok": true}` | 503 `{"ok": false, "reason": …}` |
| `GET /api/catalog` | none | read | 200 catalog | 429 |
| `GET /api/state` | none | read | 200 state | 429, 503 |
| `GET /api/pickups` | none | read | 200 list of pickups | 422, 429 |
| `POST /api/pickups` | none | write | 201 pickup | 409, 413, 415, 422, 429 |
| `POST /api/pickups/{pid}/complete` | `X-Collector-Key` unless demo | write | 200 pickup | 403, 404, 409, 422, 429 |
| `POST /api/pickups/{pid}/cancel` | none | write | 200 `{"ok": true}` | 404, 409, 422, 429 |
| `POST /api/rewards/{rid}/redeem` | none | write | 200 `{"code": "SABZ-…"}` | 404, 409, 429 |
| `GET /api/codes/{code}` | `X-Partner-Key` | write | 200 `{"rid", "ts", "used"}` | 403, 404, 422, 429 |
| `POST /api/codes/{code}/use` | `X-Partner-Key` | write | 200 `{"ok": true}` | 403, 404, 409, 422, 429 |
| `POST /api/missions/{mid}/answer` | none | write | 200 result | 404, 409, 422, 429 |
| `GET /api/transactions` | none | read | 200 list of txns | 429 |
| `GET /api/leaderboard` | none | read | 200 list of districts | 429 |
| `GET /api/city` | none | read | 200 city panel | 429 |

Any endpoint can also return 413, 415 (POST) and 503 (database unavailable).

### GET /api/health

Readiness. It opens the existing database (`mode=rw`, so it never creates one), takes the write lock, rewrites `user_version` to its own value, rolls back, and checks that the data volume has at least `MIN_FREE_MB` (50) MB free. The compose healthcheck calls it.

| Response | Meaning |
|---|---|
| 200 `{"ok": true}` | The database takes a write and there is room |
| 503 `{"ok": false, "reason": "db_busy"}` | The write lock was not free within 1 s |
| 503 `{"ok": false, "reason": "db_unwritable"}` | Missing file, read-only file or directory, or another SQLite error |
| 503 `{"ok": false, "reason": "disk_low"}` | Under 50 MB free |

### GET /api/catalog

```json
{"materials": {"plastic": {"fa": "پلاستیک و پت", "en": "Plastic & PET", "pts": 120, "co2": 1.5, "color": "#0ea5e9"}, "...": {}},
 "slots": ["08-11", "11-14", "14-17", "17-20"],
 "rewards": [{"id": "bike", "cat": "transport", "cost": 250, "fa": "…", "en": "2 h shared bike", "partner": {"fa": "…", "en": "Bidood"}}],
 "missions": [{"id": "pet", "pts": 40, "fa": {"q": "…", "a": ["…"]}, "en": {"q": "…", "a": ["…"]}, "done": true}],
 "demo": false}
```

The missions never include the answer index. `demo` tells the UI whether to show "Simulate delivery".

### GET /api/state

```json
{"name": {"fa": "…", "en": "…"}, "balance": 3420, "lifetime": 3870,
 "tier": "silver", "tierFloor": 2000, "next": {"tier": "gold", "at": 6000},
 "impact": {"kg": 38.5, "co2": 49.7, "trees": 0.31, "landfill": 69},
 "upcoming": null}
```

- `balance` is the sum of all ledger rows; `lifetime` the sum of positive rows. Tiers: bronze from 0, silver from 2000, gold from 6000 lifetime points. A redeem never lowers the tier. `next` is null at gold.
- `impact` comes from delivered pickups: kg, kg CO2 saved (per-material factors), trees (0.017 per kg of paper), landfill litres (1.8 per kg).
- `upcoming` is the earliest scheduled pickup with `day >= today`, by day, then slot, then id; null if none.
- All values come from one read snapshot.

The numbers above are the demo seed's.

### GET /api/pickups

Query: `limit`, `before` (see Pagination). Response: a list of pickups.

```json
[{"id": 5, "created": "2026-10-22T10:15:00", "day": "2026-10-23", "slot": "17-20", "address": "…",
  "items": {"plastic": 2.0}, "status": "scheduled", "est": 240, "points": 0, "weight": 0.0}]
```

Timestamps are Tehran local time without an offset. `items` holds the declared kg until completion, then the weighed kg.

### POST /api/pickups

```json
{"items": {"plastic": 2, "paper": 3.5}, "day": "2026-10-23", "slot": "17-20", "address": "Tehran, Yousefabad, 33rd St"}
```

| Field | Rule | Failure |
|---|---|---|
| `items` | At least one of `paper`, `plastic`, `metal`, `glass`, `ewaste`; each 0.5 to 50 kg; total at most 50 kg (rounded to 3 places) | 422 list |
| `day` | ISO date from today to today + 14 days, Tehran time | 422 `day must be within the next 14 days` |
| `slot` | `08-11`, `11-14`, `14-17` or `17-20` | 422 list |
| `address` | 3 to 200 characters after stripping whitespace | 422 list |

- 201 returns the stored pickup with `status: "scheduled"` and `est` (points per kg times kg, rounded).
- 409 `at most 5 pickups per day` when 5 pickups were already created today (Tehran date). Canceled pickups count.

### POST /api/pickups/{pid}/complete

The collector action. No request body is read. `pid` is 1 to 2^63-1 (else 422).

- Outside demo mode it needs `X-Collector-Key`, and the pickup's day must not be in the future.
- Each declared material is "weighed" as declared kg times a random factor from 0.9 to 1.1, rounded to 0.1 kg. Points are the estimate of the weighed items. This is a stand-in until phase A of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
- 200 returns the updated pickup (`status: "delivered"`, weighed `items`, `points`, `weight`).

| Status | Detail |
|---|---|
| 403 | `forbidden` (key unset, missing or wrong) |
| 404 | `pickup not found` |
| 409 | `pickup day is still ahead` (outside demo mode) |
| 409 | `pickup is not scheduled` (already delivered or canceled) |

### POST /api/pickups/{pid}/cancel

200 `{"ok": true}`. 404 `pickup not found`. 409 `pickup is not scheduled`. No authentication: the single demo user owns every pickup.

### POST /api/rewards/{rid}/redeem

`rid` is a reward id from the catalog. On success the wallet is debited by the reward's cost and a code is issued in the same transaction.

- 200 `{"code": "SABZ-xxxxxxxxxxxx"}`: `SABZ-` plus 12 URL-safe characters (72 random bits). The code is a bearer credential: whoever holds it can have a partner spend it. The response is the only time the API returns it.
- 404 `reward not found`. 409 `insufficient points` (nothing is written).
- There is no idempotency key: a retry after a lost response debits again.

### GET /api/codes/{code}

Partner lookup. Needs `X-Partner-Key`. `code` is at most 40 characters (else 422). 200 `{"rid": "bike", "ts": "2026-10-22T10:20:00", "used": null}`; `used` is the spend timestamp once spent. 403 `forbidden`, 404 `code not found`. Uses the write bucket, so a code sweep is slow and shows up as `auth_fail` warnings without a key.

### POST /api/codes/{code}/use

Partner spend. Needs `X-Partner-Key`. Single use: 200 `{"ok": true}` the first time, 409 `code already used` after. 404 `code not found`. Any configured partner key can spend any code; per-partner keys are phase C.

### POST /api/missions/{mid}/answer

```json
{"choice": 1}
```

`choice` is an integer 0 to 9 and must be an index of this mission's options (today every mission has 3), else 422.

| Case | Response |
|---|---|
| Correct, first time | 200 `{"correct": true, "answer": 1, "points": 40}`; the points are credited |
| Wrong, mission not yet done | 200 `{"correct": false, "points": 0}`; the answer is not revealed |
| Mission already done (right or wrong choice) | 409 `mission already done` |
| Unknown mission | 404 `mission not found` |

### GET /api/transactions

The newest 100 ledger rows, newest first: `[{"id": 7, "ts": "…", "kind": "redeem", "ref": "bike", "points": -250}]`. `kind` is `pickup`, `redeem` or `mission`.

### GET /api/leaderboard

Districts sorted by points, highest first: `[{"id": "d6", "fa": "منطقه ۶", "en": "District 6", "points": 52080, "mine": true}]`. The district totals are constants; the user's district adds the user's lifetime points.

### GET /api/city

The municipality panel: `kpi` (`tons`, `mau`, `participation`, `landfillSaved`, `co2`, `partners`), 12 `months` (`m`, `tons`, `users`), the `materials` mix (`id`, `pct`) and `districts` (as the leaderboard). The monthly series comes from a seeded generator and `participation`, `partners` and the material mix are constants; only `tons` (and what derives from it) adds the user's real delivered kg. Treat it as sample data.

## Examples

### Demo flow (`DEMO_MODE=1`)

```bash
DEMO_MODE=1 docker compose up -d --build --wait
BASE=http://127.0.0.1:3026          # the edge; through Next's /api rewrite
J='content-type: application/json'

curl -s $BASE/api/health
curl -s $BASE/api/state

# book a pickup for today (the server uses the Tehran date)
DAY=$(TZ=Asia/Tehran date +%F)
curl -s -X POST $BASE/api/pickups -H "$J" \
  -d '{"items":{"plastic":2,"paper":3.5},"day":"'"$DAY"'","slot":"17-20","address":"Tehran, Yousefabad, 33rd St"}'

# complete it as the demo collector (no key in demo mode), then check the wallet
curl -s -X POST $BASE/api/pickups/<id>/complete -H "$J" -d '{}'
curl -s $BASE/api/transactions

# a mission: a wrong answer, then the right one
curl -s -X POST $BASE/api/missions/pizza/answer -H "$J" -d '{"choice":0}'
curl -s -X POST $BASE/api/missions/pizza/answer -H "$J" -d '{"choice":1}'
```

### Partner flow

The partner endpoints need `PARTNER_KEY` even in demo mode.

```bash
export PARTNER_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
DEMO_MODE=1 docker compose up -d --build --wait     # demo: the seeded balance pays for a reward
BASE=http://127.0.0.1:3026
J='content-type: application/json'

# the citizen redeems a reward and gets a code
CODE=$(curl -s -X POST $BASE/api/rewards/bike/redeem -H "$J" -d '{}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["code"])')

# the partner looks it up, spends it, and a second spend is refused
curl -s $BASE/api/codes/$CODE -H "X-Partner-Key: $PARTNER_KEY"                  # {"rid":"bike",...,"used":null}
curl -s -X POST $BASE/api/codes/$CODE/use -H "X-Partner-Key: $PARTNER_KEY" -H "$J" -d '{}'   # {"ok":true}
curl -s -o /dev/null -w '%{http_code}\n' -X POST $BASE/api/codes/$CODE/use \
  -H "X-Partner-Key: $PARTNER_KEY" -H "$J" -d '{}'                              # 409
curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/codes/$CODE                 # 403 without the key
```

### Collector flow (production)

```bash
curl -s -X POST $BASE/api/pickups/<id>/complete \
  -H "X-Collector-Key: $COLLECTOR_KEY" -H 'content-type: application/json' -d '{}'
```

The response is 409 `pickup day is still ahead` before the pickup's day.
