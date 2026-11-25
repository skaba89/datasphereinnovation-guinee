"""Persistent REC monitor incident state; no notification transport or service changes."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

CHECKS = frozenset(("container_healthy", "api_health", "api_ready",
                    "antivirus_clean_scan", "backup_recent", "disk_available"))
REMINDER_SECONDS = 3600


def parse_report(report):
    if not isinstance(report, dict) or set(report.get("checks", {})) != CHECKS:
        raise ValueError("incomplete monitor report")
    checks = report["checks"]
    if any(value not in ("PASS", "FAIL") for value in checks.values()):
        raise ValueError("invalid monitor result")
    failed = sorted(key for key, value in checks.items() if value == "FAIL")
    if report.get("status") != ("FAIL" if failed else "PASS"):
        raise ValueError("inconsistent monitor report")
    return failed


def transition(previous, failed, now):
    if type(now) is not int or now < 0:
        raise ValueError("invalid timestamp")
    if previous is not None:
        if not isinstance(previous, dict) or set(previous) != {"failed", "opened", "last_event", "observed"}:
            raise ValueError("invalid incident state")
        old = previous["failed"]
        if not isinstance(old, list) or old != sorted(set(old)) or not set(old) <= CHECKS:
            raise ValueError("invalid previous checks")
        if any(type(previous[k]) is not int for k in ("opened", "last_event", "observed")):
            raise ValueError("invalid state timestamps")
        if not 0 <= previous["opened"] <= previous["last_event"] <= previous["observed"] <= now:
            raise ValueError("clock regression or invalid state")
    else:
        old = []
    if failed and not old:
        event, opened, last = "OPEN", now, now
    elif old and not failed:
        event, opened, last = "RECOVERED", now, now
    elif failed and failed != old:
        event, opened, last = "CHANGED", previous["opened"], now
    elif failed and now - previous["last_event"] >= REMINDER_SECONDS:
        event, opened, last = "REMINDER", previous["opened"], now
    elif previous is not None:
        event, opened, last = "NONE", previous["opened"], previous["last_event"]
    else:
        event, opened, last = "NONE", now, now
    return {"failed": failed, "opened": opened, "last_event": last, "observed": now}, event


def secure_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("private file required")
        data = source.read(65537)
        if len(data) > 65536:
            raise ValueError("input exceeds limit")
        return json.loads(data)


def record(directory, report, now):
    failed = parse_report(report)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private owned state directory required")
    lock = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("invalid lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory / "incident.json"
        try:
            previous = secure_read(path)
        except FileNotFoundError:
            previous = None
        state, event = transition(previous, failed, now)
        fd, tmp = tempfile.mkstemp(prefix=".incident-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(state, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
            dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return {"environment": "REC", "event": event, "failed": failed,
                "observed_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "notification_sent": False, "production_authorized": False}
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor-report", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report = record(args.state_dir, secure_read(args.monitor_report),
                        int(datetime.now(timezone.utc).timestamp()))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
