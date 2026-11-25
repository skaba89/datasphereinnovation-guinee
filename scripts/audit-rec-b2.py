#!/usr/bin/env python3
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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

    if not BACKUPS.is_dir() or not STATE.is_dir():
        fail("répertoire de sauvegarde absent")

    candidates = []
    pattern = re.compile(
        rf"^dsig-rec-{day}T(\d{{6}})Z\.dsigbak$"
    )

    for p in BACKUPS.iterdir():
        if p.is_symlink() or not p.is_file():
            continue
        match = pattern.fullmatch(p.name)
        if match and "020000" <= match.group(1) < "030000":
            candidates.append(p)

    if len(candidates) != 1:
        fail("une archive unique attendue entre 02:00 et 03:00 UTC")

    archive = candidates[0]
    if archive.stat().st_size == 0:
        fail("archive vide")

    if archive.stat().st_mode & 0o077:
        fail("permissions archive trop ouvertes")

    digest = sha256(archive)
    marker = STATE / (archive.name + ".sha256")

    if marker.is_symlink() or not marker.is_file():
        fail("preuve B2 absente")

    if marker.stat().st_mode & 0o077:
        fail("permissions preuve trop ouvertes")

    if marker.read_text().strip() != digest:
        fail("SHA256 local différent de la preuve B2")

    marker_time = datetime.fromtimestamp(
        marker.stat().st_mtime, timezone.utc
    )

    if (
        marker_time.strftime("%Y%m%d") != day
        or not (3 <= marker_time.hour < 4)
    ):
        fail("preuve B2 non créée pendant la fenêtre prévue")

    object_name = (
        f"rec/{day[:4]}/{day[4:6]}/{archive.name}"
    )

    if not B2.is_file():
        fail("exécutable Backblaze absent")

    print("PASS : archive et preuve locale", flush=True)

    with tempfile.TemporaryDirectory(prefix="dsig-b2-audit-") as tmp:
        dest = Path(tmp) / "archive.dsigbak"

        command(
            [
                str(B2), "file", "download",
                "--no-progress",
                f"b2://{BUCKET}/{object_name}",
                str(dest),
            ],
            timeout=600,
        )

        if not dest.is_file() or sha256(dest) != digest:
            fail("archive B2 absente ou SHA256 incorrect")

    print("PASS : objet distant et intégrité SHA256", flush=True)
    print("Archive :", archive.name, flush=True)
    print("PASS : cycle quotidien REC vers B2 vérifié", flush=True)

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--preflight":
        assert BACKUPS.is_dir()
        assert STATE.is_dir()
        assert B2.is_file()
        for name in ("dsig-rec-backup.timer", "dsig-rec-b2.timer"):
            assert timer_active(name)
        print("PASS : prérequis de l'audit")
    elif len(sys.argv) == 1:
        audit()
    else:
        fail("argument non reconnu")
