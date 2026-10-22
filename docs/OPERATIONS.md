# Operations runbook

This runbook is for the person who runs SabzBank with `docker compose`: how to start and stop it, what the health check means, how to back up, restore and check the ledger, how to rotate the collector and partner keys, which log lines to alert on, how to upgrade a volume made by the old root image, and what to do when a key leaks, points inflate or the data volume is lost. All commands run from the repository root. Service names, profiles and variables are those in [docker-compose.yml](../docker-compose.yml); the backup and check commands are in [backend/ops.py](../backend/ops.py).

## Start and stop

```bash
# production: keys in the environment or in a .env file next to docker-compose.yml (.env is gitignored)
docker compose up -d --build --wait      # builds, starts backend -> frontend -> edge, waits until all are healthy
docker compose ps                        # STATUS shows (healthy)
docker compose logs -f backend           # follow the API log
docker compose restart backend           # restart one service
docker compose stop                      # stop, keep containers and data
docker compose down                      # remove containers and network, KEEP the sabz-data volume
```

Never run `docker compose down -v` on a production host: `-v` deletes the `sabz-data` volume, which is the ledger.

Startup order is enforced by healthchecks: the frontend starts after the backend is healthy, and the edge after the frontend is healthy. An environment change (a new key, `DEMO_MODE`) takes effect when the container is recreated: `docker compose up -d backend`.

The backend refuses to start, and the container restarts in a loop, when:

- a configured key is shorter than 32 characters or has fewer than 10 distinct characters (the log names the variable);
- a migration step fails, for example on a duplicate credit (see "Upgrading").

## Health and readiness

| Service | Healthcheck | Healthy means |
|---|---|---|
| backend | `python -c "…urlopen('http://localhost:8000/api/health')"` every 10 s | `GET /api/health` returned 200 |
| frontend | `wget -qO /dev/null http://127.0.0.1:3000/` | Next server-renders the home page (it calls `proxy.ts` and SSR) |
| edge | `wget -qO /dev/null http://127.0.0.1/icon.svg` | Caddy reaches Next and Next serves a static file; the backend is not touched |

`GET /api/health` is a readiness check, not a liveness ping. It returns 503 with a reason when the process is up but cannot do its job:

| `reason` | Meaning | First action |
|---|---|---|
| `db_busy` | The write lock was not free within 1 s | Look for a long-running writer (a manual `sqlite3` session, a stuck backup); retry |
| `db_unwritable` | The database file is missing, read-only, or its directory is not writable | Check the volume is mounted and owned by uid 10001 (see "Upgrading"); check the host filesystem is not read-only |
| `disk_low` | Under 50 MB free on the data volume | Free space; prune old images; move backups off the host |

```bash
curl -s http://127.0.0.1:8026/api/health      # direct, on the loopback port
docker inspect --format '{{json .State.Health}}' "$(docker compose ps -q backend)"
```

## Backups

`ops.py backup DIR` makes an online copy with SQLite's backup API (consistent mid-write, including pages still in the `-wal` file), runs `PRAGMA integrity_check` on the copy, renames it from `.part` to `sabz-YYYYmmdd-HHMMSS.db` (UTC), and keeps the newest 14 (`KEEP`). Any failure, including a missing database, logs `event=backup ok=0 reason=…` and exits 1. The backend may keep running.

One-time setup, then a daily cron entry:

```bash
mkdir -p backups && sudo chown 10001:10001 backups     # the job runs as uid 10001
docker compose --profile ops run --rm ops              # -> event=backup ok=1 bytes=... file=sabz-....db
```

```cron
15 2 * * *  cd <repo> && docker compose --profile ops run --rm ops >> backup.log 2>&1 && docker compose --profile ops run --rm ledger-check >> backup.log 2>&1 || <your alert command>
```

(Replace `<repo>` and `<your alert command>` for your host. Both jobs exit non-zero on failure.) Set `BACKUP_DIR` to write elsewhere. The `ops` job runs from the backend image the last `up` or `build` made (`pull_policy: never`), so build once before the first run.

Copy the backups off the host. Nothing in the repository does this: 14 copies on the same disk do not survive the loss of that disk.

## Restore

1. Pick a backup and check it opens: `python3 -c "import sqlite3; print(sqlite3.connect('backups/sabz-YYYYmmdd-HHMMSS.db').execute('PRAGMA integrity_check').fetchone())"` prints `('ok',)`.
2. Stop the backend: `docker compose stop backend`. The frontend and edge keep serving pages; API calls fail until step 5.
3. Copy the backup over the database, delete the stale `-wal` and `-shm` files (they belong to the old database and would corrupt the restored one), and give the files to uid 10001:

   ```bash
   docker run --rm -v <project>_sabz-data:/data -v "$PWD/backups:/backups:ro" alpine sh -c \
     'cp /backups/sabz-YYYYmmdd-HHMMSS.db /data/sabz.db && rm -f /data/sabz.db-wal /data/sabz.db-shm && chown -R 10001:10001 /data'
   ```

   `<project>` is the compose project name (`docker volume ls` shows the volume as `<project>_sabz-data`).
4. Check the ledger before taking traffic: `docker compose --profile ops run --rm ledger-check`.
5. Start the backend: `docker compose start backend`, then `curl -s http://127.0.0.1:8026/api/health`.

Everything after the backup's timestamp is gone: pickups, credits, redeems and the reward codes issued since. A partner presenting such a code gets 404. Tell partners which window is affected.

## Ledger check

```bash
docker compose --profile ops run --rm ledger-check     # -> event=ledger_check ok=1 reason=-, exit 0
```

It reads one snapshot and tests five invariants; an `ok=0` line names each broken one and the job exits 1:

| Invariant | Broken when |
|---|---|
| `pickup_txn_unmatched` | A pickup credit has no delivered pickup with the same id and points |
| `pickup_sum` | Pickup credits and delivered pickups' points do not add up (a missing or doubled credit) |
| `negative_balance` | The total balance is below zero |
| `mission_unrecorded` | A mission credit has no `missions_done` row |
| `codes_exceed_redeems` | For some reward, there are more codes than redeem rows |

Run it daily after the backup, and after any restore or manual SQL. It cannot see inflation that looks legitimate (a fraudulent but well-formed complete); the log lines below cover that.

## Key rotation

Both keys accept a comma list, so clients move over without downtime.

1. Make a new key: `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
2. Set both, new first: `COLLECTOR_KEY="<new>,<old>"` in `.env` or the environment. Recreate: `docker compose up -d backend`.
3. Note the fingerprints: `python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:6])' <key>`.
4. Move every collector (or partner) client to the new key.
5. Watch the success lines until only the new fingerprint appears: `docker compose logs --since 24h backend | grep -E 'event=(complete|code_use) ' | grep -o 'key=[0-9a-f]*' | sort | uniq -c`.
6. Set the new key alone, `COLLECTOR_KEY="<new>"`, and recreate the backend. A client still on the old key now logs `event=auth_fail … reason=mismatch fp=<old fingerprint>`.

The same steps apply to `PARTNER_KEY`. There is one partner key for all partners, so a rotation touches every partner at once until per-partner keys exist (phase C of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)).

## What to watch in the logs

```bash
docker compose logs --no-color --since 1h backend | grep -E ' (WARNING|ERROR) '
```

| Signal | Pattern | Alert when | Likely cause |
|---|---|---|---|
| Key guessing or a stale client | `event=auth_fail` | Any `reason=mismatch` from an unknown `fp`; any `reason=unconfigured` in production | Probing, a client on a rotated key, or a key not set |
| Edge bypass | `event=edge_bypass` | Any, outside your own host-local tooling | Something reaches the backend without the edge (a widened `API_BIND`, a peer container). A single forged `X-Forwarded-For` entry does not trigger it |
| Database trouble | `event=db_busy`, `event=db_error`, 503 access lines | Any | Lock contention past 5 s, a read-only or full volume |
| Sweep failure | `event=expire_overdue_failed` | Any | Database locked or read-only during the hourly sweep |
| Demo in production | `event=startup` with `demo=1` | On a production host | `DEMO_MODE=1` left set: anyone can complete pickups |
| Missing key at startup | `event=startup` with `collector_key_set=0` or `partner_key_set=0` | On a production host | Key not passed to the container |
| Points minted | `event=complete … points=N` | One complete above a few thousand points, or a daily total far above normal | Collector key misuse, inflated declarations |
| Pickup volume | `event=create_pickup` | Daily count at the cap (5) day after day | Farming |
| Code spends | `event=code_use` | Spends by an unexpected `key` fingerprint, or a burst | Partner key misuse |
| Rate limiting | access lines with status 429 | A sustained stream from one ip | Flooding, or many users behind one carrier NAT |
| Backups | `event=backup ok=0`, `event=ledger_check ok=0` | Any; also a missing daily `ok=1` | Unwritable backup directory, broken invariant |

Every line of one request carries the same request id (also returned to the client as `x-request-id`): the access line starts with it and each audit line has `rid=<id>`, so `grep <id>` reconstructs the request. Container logs rotate at 5 files of 10 MB per service; ship them elsewhere if you need a longer history.

## Upgrading

### A volume created by the old root image

The image now runs as uid 10001. A `sabz-data` volume created when the backend ran as root is owned by root, and the new backend fails with "attempt to write a readonly database". Give it to uid 10001 once:

```bash
docker compose stop backend
docker run --rm -v <project>_sabz-data:/data alpine chown -R 10001:10001 /data
docker compose up -d --wait
```

### The award-once migration (schema version 2) on an existing database

Version 2 adds a unique index that allows one credit per pickup and one per mission. A database that already holds a duplicate pickup or mission credit cannot take it: the step rolls back whole, the version stays at 1, and the backend refuses to start. Check before upgrading, on a copy or with the backend stopped:

```bash
docker compose build backend
docker compose --profile ops run --rm ops python -c "import sqlite3; print(sqlite3.connect('/data/sabz.db').execute(\"SELECT kind, ref, COUNT(*) FROM txns WHERE kind IN ('pickup','mission') GROUP BY kind, ref HAVING COUNT(*) > 1\").fetchall())"
```

`[]` means the upgrade is safe. Any row is a double credit: decide with the product owner which row is wrong, back up, delete that row by its `id`, and run the check again. Do the `chown` above first if the volume is still root-owned.

## Incident runbooks

### Leaked collector key

The collector key mints points: whoever holds it can complete any scheduled pickup.

1. Contain: set a new `COLLECTOR_KEY` alone (no `new,old`), recreate the backend. Collector clients stop working until they get the new key; that is the price of containment.
2. Scope: find what the old key did. `docker compose logs --since <leak time> backend | grep 'event=complete ' | grep 'key=<old fingerprint>'` lists `pid`, `points`, `kg` and `rid` per credit.
3. Watch: `event=auth_fail reason=mismatch fp=<old fingerprint>` shows someone still trying the leaked key, with their `ip` on the matching access line.
4. Check: run `ledger-check`. It will pass (fraudulent completes are well-formed); the scope list from step 2 is the evidence.
5. Correct: there is no reversal entry type yet. Any correction to the ledger is a manual decision for the founder and the technical lead, made on a backup copy first and recorded.

### Leaked partner key

The partner key spends codes (and looks them up).

1. Contain: set a new `PARTNER_KEY` alone, recreate the backend, re-issue the key to every partner (there is one key for all).
2. Scope: `grep 'event=code_use ' | grep 'key=<old fingerprint>'` lists the spent codes by `code=<sha256[:8]>`. To match a code a customer reports, compute `sha256(code)[:8]`.
3. Watch: `event=auth_fail` lines with the old fingerprint, and 404 access lines under `/api/codes/code#…` (lookups of codes that do not exist).
4. Affected citizens: a code spent by the attacker shows `used` set in `GET /api/codes/{code}`. Restoring a code means `UPDATE codes SET used = NULL WHERE code = ?` on the live database; treat it as a manual, recorded decision.

### Points inflation

Signs: a jump in `event=complete` points, many `event=create_pickup` lines at the daily cap, rewards redeemed faster than usual, or an `ok=0` from `ledger-check`.

1. Measure: sum the day's mints, `docker compose logs --since 24h backend | grep 'event=complete ' | grep -o ' points=[0-9]*' | cut -d= -f2 | awk '{s+=$1} END {print s}'`.
2. Attribute: group the `complete` lines by `key` fingerprint and look at the `ip` of their access lines (same `rid`).
3. Run `ledger-check`. A broken invariant (`pickup_sum`, `pickup_txn_unmatched`) means a bug or manual SQL, not abuse through the API.
4. If a key is involved, follow the leaked-key runbook.
5. Structural fixes are phase A (measured weights) and phase E (a mint ceiling) of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

### Data volume loss

Signs: `GET /api/health` returns `db_unwritable`, the backend log shows `event=db_error`, or the volume is gone.

1. Do not start a backend on an empty volume and let it take traffic: production starts empty at 0 points and every citizen balance would read 0.
2. Restore the newest good backup (see "Restore"), then run `ledger-check`.
3. Tell partners the window since the backup: codes issued in it no longer exist (404).
4. Find the cause (disk, host, an accidental `down -v`) before reopening.
5. If no backup exists, the ledger is lost. This is why the off-host copy matters.
