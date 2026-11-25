"""REC incident outbox: atomic observation + enqueue, explicit SMTP delivery."""
import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from email.message import EmailMessage
import re
import smtplib
import ssl

from rec_incident_state import parse_report, transition

MAX_PENDING = 1000
RETRY_SECONDS = 300


def open_db(directory):
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private owned directory required")
    path = directory / "outbox.sqlite3"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("private regular database required")
    finally:
        os.close(fd)
    db = sqlite3.connect(path, timeout=5)
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS monitor_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS outbox (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
            event TEXT NOT NULL, failed TEXT NOT NULL, observed INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, retry_at INTEGER NOT NULL DEFAULT 0,
            accepted INTEGER)""")
        db.commit()
        return db
    except BaseException:
        db.close()
        raise


def observe(db, report, now):
    failed = parse_report(report)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT payload FROM monitor_state WHERE id=1").fetchone()
        state, event = transition(json.loads(row[0]) if row else None, failed, now)
        if event != "NONE":
            if db.execute("SELECT count(*) FROM outbox WHERE accepted IS NULL").fetchone()[0] >= MAX_PENDING:
                raise ValueError("outbox full; operator intervention required")
            db.execute("INSERT INTO outbox(event_id,event,failed,observed) VALUES(?,?,?,?)",
                       (uuid.uuid4().hex, event, json.dumps(failed), now))
        db.execute("INSERT INTO monitor_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                   (json.dumps(state),))
        db.commit()
        return event
    except BaseException:
        db.rollback()
        raise


def send(event, env):
    event_id, kind, failed, observed = event
    if not re.fullmatch(r"[a-f0-9]{32}", event_id) or kind not in ("OPEN", "CHANGED", "REMINDER", "RECOVERED"):
        raise ValueError("invalid event")
    host, sender, recipient, user, password = (env[k] for k in
        ("DSIG_ALERT_SMTP_HOST", "DSIG_ALERT_FROM", "DSIG_ALERT_TO",
         "DSIG_ALERT_SMTP_USER", "DSIG_ALERT_SMTP_PASSWORD"))
    address = r"[A-Za-z0-9.!#$%&'*+/=?^_~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not all(re.fullmatch(address, a) for a in (sender, recipient)) or not user or not password:
        raise ValueError("invalid SMTP configuration")
    message = EmailMessage()
    message["From"], message["To"] = sender, recipient
    message["Subject"] = "DSIG REC monitor: " + kind
    message["Message-ID"] = "<" + event_id + "@dsig-rec.invalid>"
    message.set_content("Environment: REC\nEvent: " + kind + "\nObserved UTC epoch: " +
                        str(observed) + "\nFailed checks: " + ", ".join(json.loads(failed)) +
                        "\nCheck the REC journal.\n")
    with smtplib.SMTP_SSL(host, 465, timeout=15, context=ssl.create_default_context()) as smtp:
        smtp.login(user, password)
        if smtp.send_message(message):
            raise ValueError("recipient rejected")


def deliver_one(db, now, transport):
    # Serialize senders using a DB write transaction. A crash after SMTP
    # acceptance but before commit may repeat the stable Message-ID.
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT seq,event_id,event,failed,observed,retry_at FROM outbox "
                         "WHERE accepted IS NULL ORDER BY seq LIMIT 1").fetchone()
        if row is None or row[5] > now:
            db.commit()
            return "NONE"
        try:
            transport(row[1:5])
        except (OSError, ValueError, KeyError, smtplib.SMTPException):
            db.execute("UPDATE outbox SET attempts=attempts+1,retry_at=? WHERE seq=?",
                       (now + RETRY_SECONDS, row[0]))
            db.commit()
            return "RETRY"
        db.execute("UPDATE outbox SET attempts=attempts+1,accepted=? WHERE seq=?", (now, row[0]))
        db.commit()
        return "SMTP_ACCEPTED"
    except BaseException:
        db.rollback()
        raise


def collect():
    # Execute the existing monitor directly, rather than accept stale external JSON.
    spec = importlib.util.spec_from_file_location("dsig_monitor", Path(__file__).with_name("monitor-rec.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--observe", action="store_true")
    group.add_argument("--deliver", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        with closing(open_db(args.state_dir)) as db:
            if args.observe:
                report = collect()
                result = observe(db, report, int(time.time()))
            else:
                result = deliver_one(db, int(time.time()), lambda event: send(event, os.environ))
            pending = db.execute("SELECT count(*) FROM outbox WHERE accepted IS NULL").fetchone()[0]
        print(json.dumps({"environment": "REC", "result": result, "pending": pending,
                          "production_authorized": False}))
        return int(result == "RETRY")
    except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
