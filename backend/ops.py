"""Operator commands for the SabzBank ledger. Stdlib only; DB_PATH comes from the environment, as in main.py.

  python ops.py backup DIR   online copy to DIR/sabz-YYYYmmdd-HHMMSS.db (UTC), integrity-checked; keeps the newest 14
  python ops.py check        ledger invariants; an ERROR line names each one that fails

Each run logs one event=... line and exits 1 on any failure, so cron or a compose job can alert on the exit code.
Restore: stop the backend, copy a backup over DB_PATH, delete the stale -wal and -shm files next to it, chown 10001:10001.
"""
import logging
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "data/sabz.db")
KEEP = 14
log = logging.getLogger("sabz.ops")

# name -> a query that returns a truthy first column when the invariant is broken
INVARIANTS = {
    # every pickup credit matches a delivered pickup with the same points...
    "pickup_txn_unmatched": "SELECT COUNT(*) FROM txns t LEFT JOIN pickups p ON p.id = CAST(t.ref AS INTEGER) "
                            "AND p.status = 'delivered' AND p.points = t.points WHERE t.kind = 'pickup' AND p.id IS NULL",
    # ...and they add up, which also catches a delivered pickup without a credit or a double credit
    "pickup_sum": "SELECT (SELECT COALESCE(SUM(points), 0) FROM txns WHERE kind = 'pickup') "
                  "!= (SELECT COALESCE(SUM(points), 0) FROM pickups WHERE status = 'delivered')",
    "negative_balance": "SELECT COALESCE(SUM(points), 0) < 0 FROM txns",
    "mission_unrecorded": "SELECT COUNT(*) FROM txns t WHERE t.kind = 'mission' "
                          "AND NOT EXISTS (SELECT 1 FROM missions_done m WHERE m.id = t.ref)",
    # <= rather than ==: the demo seed has a redeem without a code row
    "codes_exceed_redeems": "SELECT COUNT(*) FROM (SELECT rid, COUNT(*) AS n FROM codes GROUP BY rid) c "
                            "WHERE c.n > (SELECT COUNT(*) FROM txns t WHERE t.kind = 'redeem' AND t.ref = c.rid)",
}


def connect() -> sqlite3.Connection:
    """The existing ledger. Never creates an empty one: a missing volume must fail, not back up nothing."""
    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(DB_PATH)
    return sqlite3.connect(DB_PATH, timeout=10)


def backup(dst_dir: str) -> int:
    dst = os.path.join(dst_dir, datetime.now(timezone.utc).strftime("sabz-%Y%m%d-%H%M%S.db"))
    part = dst + ".part"  # a crash mid-copy leaves a .part file, never a sabz-*.db that looks good
    try:
        os.makedirs(dst_dir, exist_ok=True)
        with closing(connect()) as src, closing(sqlite3.connect(part)) as out:
            src.backup(out)  # SQLite's online backup: a consistent copy mid-write, including pages still in the -wal file
            ok = out.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        if not ok:
            raise ValueError("integrity_check")
        os.replace(part, dst)
        for old in sorted(f for f in os.listdir(dst_dir) if f.startswith("sabz-") and f.endswith(".db"))[:-KEEP]:
            os.remove(os.path.join(dst_dir, old))
    except Exception as e:  # any failure: one line saying why, and a non-zero exit
        if os.path.exists(part):
            os.remove(part)
        log.error("event=backup ok=0 reason=%s", str(e) if isinstance(e, ValueError) else type(e).__name__)
        return 1
    log.info("event=backup ok=1 bytes=%d file=%s", os.path.getsize(dst), os.path.basename(dst))
    return 0


def check() -> int:
    try:
        with closing(connect()) as con:
            con.execute("BEGIN")  # one snapshot for every invariant
            broken = [name for name, sql in INVARIANTS.items() if con.execute(sql).fetchone()[0]]
    except Exception as e:
        log.error("event=ledger_check ok=0 reason=%s", type(e).__name__)
        return 1
    if broken:
        log.error("event=ledger_check ok=0 reason=%s", ",".join(broken))
        return 1
    log.info("event=ledger_check ok=1 reason=-")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "backup":
        sys.exit(backup(args[1]))
    if args == ["check"]:
        sys.exit(check())
    sys.exit("usage: python ops.py backup DIR | python ops.py check")
