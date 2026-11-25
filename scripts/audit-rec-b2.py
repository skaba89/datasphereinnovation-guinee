#!/usr/bin/env python3
"""Audit of the REC -> Backblaze B2 chain.

  audit-rec-b2.py                         daily cycle (timer): today's 02:00-03:00 UTC archive, proof
                                          created 03:00-04:00 UTC, remote object re-downloaded and hashed
  audit-rec-b2.py --manual [--archive N]  manual qualification of a recent archive exported outside the
                                          window; it NEVER validates the daily cycle
  audit-rec-b2.py --preflight             prerequisites only
Selection rules are shared with the export (rec_b2.py), so both designate the same archive.
"""
import hashlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rec_b2  # noqa: E402

HOME = Path("/home/ubuntu")
BACKUPS = HOME / "dsig-backups"
STATE = HOME / "dsig-b2-automation"
B2 = HOME / ".local/bin/b2"
BUCKET = "dsig-backup"


def fail(message):
    print("FAIL:", message, flush=True)
    raise SystemExit(1)


def command(args, timeout=60):
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        fail("commande impossible ou délai dépassé")
    if result.returncode != 0:
        fail("commande en échec : " + Path(str(args[0])).name)
    return result.stdout.decode("utf-8", errors="replace").strip()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def timer_active(name):
    return command(
        ["systemctl", "is-active", name]
    ) == "active"


def local_checks(archive):
    """Archive and proof checks shared by both modes; returns (digest, marker)."""
    try:
        rec_b2.check_archive(archive)
        digest = sha256(archive)
        marker = rec_b2.proof_path(STATE, archive.name)
        recorded = rec_b2.read_proof(marker, archive.name)
    except rec_b2.Failure as error:
        fail(str(error))
    if recorded is None:
        fail("preuve B2 absente")
    if recorded != digest:
        fail("SHA256 local différent de la preuve B2")
    return digest, marker


def remote_check(archive, digest):
    if not B2.is_file():
        fail("exécutable Backblaze absent")
    with tempfile.TemporaryDirectory(prefix="dsig-b2-audit-") as tmp:
        dest = Path(tmp) / "archive.dsigbak"
        command(
            [
                str(B2), "file", "download",
                "--no-progress",
                f"b2://{BUCKET}/{rec_b2.object_name(archive.name)}",
                str(dest),
            ],
            timeout=600,
        )
        if not dest.is_file() or sha256(dest) != digest:
            fail("archive B2 absente ou SHA256 incorrect")
    print("PASS : objet distant et intégrité SHA256", flush=True)


def private_dirs():
    try:
        rec_b2.private_dir(BACKUPS, "répertoire de sauvegarde")
        rec_b2.private_dir(STATE, "répertoire des preuves")
    except rec_b2.Failure as error:
        fail(str(error))


def audit():
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y%m%d")

    print("=== AUDIT DSIG REC / B2 ===", flush=True)
    print("Date UTC :", day, flush=True)

    if now.hour < 3 or (now.hour == 3 and now.minute < 30):
        fail("audit lancé avant 03:30 UTC")

    for timer in (
        "dsig-rec-backup.timer",
        "dsig-rec-b2.timer",
    ):
        if not timer_active(timer):
            fail("timer inactif : " + timer)
        print("PASS : timer", timer, flush=True)

    private_dirs()
    try:
        archive = rec_b2.select_daily(BACKUPS, day)
    except rec_b2.Failure as error:
        fail(str(error))

    digest, marker = local_checks(archive)
    marker_time = datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc)
    start, end = rec_b2.PROOF_HOURS
    if (
        marker_time.strftime("%Y%m%d") != day
        or not (start <= marker_time.hour < end)
    ):
        fail("preuve B2 non créée pendant la fenêtre prévue")

    print("PASS : archive et preuve locale", flush=True)
    remote_check(archive, digest)
    print("Archive :", archive.name, flush=True)
    print("PASS : cycle quotidien REC vers B2 vérifié", flush=True)


def manual(name=None):
    """Qualify a recent exported archive at any time. Does not validate the daily cycle."""
    now = datetime.now(timezone.utc)
    print("=== QUALIFICATION MANUELLE DSIG REC / B2 ===", flush=True)
    print("(ne valide pas le cycle quotidien)", flush=True)
    private_dirs()
    try:
        archive = rec_b2.select_manual(BACKUPS, now, name)
    except rec_b2.Failure as error:
        fail(str(error))
    digest, marker = local_checks(archive)
    marker_time = datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc)
    if marker_time < rec_b2.archive_time(archive.name) or marker_time > now + rec_b2.FUTURE_TOLERANCE:
        fail("preuve B2 incohérente avec l'archive")
    print("PASS : archive et preuve locale", flush=True)
    remote_check(archive, digest)
    print("Archive :", archive.name, flush=True)
    print("PASS : qualification manuelle (cycle quotidien NON validé)", flush=True)


def main(argv):
    if argv == ["--preflight"]:
        assert BACKUPS.is_dir()
        assert STATE.is_dir()
        assert B2.is_file()
        for name in ("dsig-rec-backup.timer", "dsig-rec-b2.timer"):
            assert timer_active(name)
        print("PASS : prérequis de l'audit")
    elif not argv:
        audit()
    elif argv == ["--manual"]:
        manual()
    elif len(argv) == 3 and argv[:2] == ["--manual", "--archive"]:
        manual(argv[2])
    else:
        fail("argument non reconnu")


if __name__ == "__main__":
    main(sys.argv[1:])
