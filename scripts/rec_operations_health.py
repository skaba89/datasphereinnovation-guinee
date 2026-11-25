"""Read-only REC operational health; local evidence is not remote availability."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat

import rec_b2
from rec_incident_state import transition
from rec_alert_outbox import MAX_PENDING

MAX_AGE = 900
WARN_PENDING = MAX_PENDING * 80 // 100


def check_outbox(directory, now):
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private directory required")
    path = directory / "outbox.sqlite3"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("private database required")
    with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        integrity = db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        row = db.execute("SELECT payload FROM monitor_state WHERE id=1").fetchone()
        timestamp = int(now.timestamp())
        state = json.loads(row[0]) if row else None
        if state is not None:
            transition(state, state["failed"], timestamp)
        age = timestamp - state["observed"] if state else None
        pending, oldest = db.execute("SELECT count(*), min(observed) FROM outbox WHERE accepted IS NULL").fetchone()
        pending_age = timestamp - oldest if oldest is not None else None
        accepted = db.execute("SELECT count(*) FROM outbox WHERE accepted IS NOT NULL").fetchone()[0]
        aged = db.execute("SELECT count(*) FROM outbox WHERE accepted IS NOT NULL AND accepted < ?",
                          (timestamp - 90 * 86400,)).fetchone()[0]
    return {
        "sqlite_quick_check": "PASS" if integrity else "FAIL",
        "monitor_freshness": "PASS" if age is not None and 0 <= age <= MAX_AGE else "FAIL",
        "monitor_checks": "UNKNOWN" if state is None else ("FAIL" if state["failed"] else "PASS"),
        "pending_age": "FAIL" if pending_age is not None and not 0 <= pending_age <= MAX_AGE else "PASS",
        "queue_capacity": "FAIL" if pending >= MAX_PENDING else ("WARN" if pending >= WARN_PENDING else "PASS"),
    }, {"observation_age_seconds": age, "pending": pending, "oldest_pending_age_seconds": pending_age,
        "accepted_count": accepted, "accepted_older_than_90_days": aged}


def check_b2(backups, proofs, now):
    # Allow the scheduled audit its ten-minute download timeout plus grace.
    cutoff = now.replace(hour=4, minute=20, second=0, microsecond=0)
    day = (now if now >= cutoff else now - timedelta(days=1)).strftime("%Y%m%d")
    try:
        rec_b2.private_dir(backups, "backup")
        rec_b2.private_dir(proofs, "proof")
        archive = rec_b2.select_daily(backups, day)
        rec_b2.check_archive(archive)
        marker = rec_b2.proof_path(proofs, archive.name, "scheduled")
        digest = rec_b2.read_proof(marker, archive.name)
        if digest is None:
            raise ValueError("missing proof")
        created = rec_b2.proof_time(marker)
        if created.strftime("%Y%m%d") != day or not 3 <= created.hour < 4 or created > now:
            raise ValueError("invalid proof timing")
        if rec_b2.sha256(archive) != digest:
            raise ValueError("digest mismatch")
        return "PASS", day
    except (OSError, ValueError, rec_b2.Failure):
        return "FAIL", day


def inspect(directory, backups, proofs, now):
    try:
        checks, metrics = check_outbox(directory, now)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        checks, metrics = {"outbox_readable": "FAIL"}, {}
    checks["b2_local_scheduled_proof"], day = check_b2(backups, proofs, now)
    status = "FAIL" if "FAIL" in checks.values() else ("WARN" if any(v != "PASS" for v in checks.values()) else "PASS")
    return {"environment": "REC", "status": status, "checks": checks, "metrics": metrics,
            "expected_b2_day_utc": day, "remote_b2_verified": False,
            "smtp_inbox_verified": False, "production_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--backups", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.state_dir, args.backups, args.proofs, datetime.now(timezone.utc))
    print(json.dumps(report, indent=2))
    return {"PASS": 0, "WARN": 2, "FAIL": 1}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
