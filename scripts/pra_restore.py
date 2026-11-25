"""REC recovery rehearsal on a dedicated, empty local Docker host."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import time
import uuid


def docker(*args, **kwargs):
    return subprocess.run(["docker", "--host", "unix:///var/run/docker.sock", *args],
                          check=True, timeout=180, **kwargs)


def private_input(path, expected):
    path = Path(path)
    if not re.fullmatch("[a-f0-9]{64}", expected):
        raise ValueError("invalid trusted digest")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("input must be a private regular file owned by caller")
        h = hashlib.sha256()
        for block in iter(lambda: source.read(1024**2), b""):
            h.update(block)
        if h.hexdigest() != expected:
            raise ValueError("input digest mismatch")


def require_empty_host():
    # Refuse stopped containers and existing volumes as well as live services.
    for args in [("ps", "-aq"), ("volume", "ls", "-q")]:
        if docker(*args, stdout=subprocess.PIPE).stdout.strip():
            raise ValueError("dedicated empty Docker host required")
    nets = docker("network", "ls", "--format", "{{.Name}}", stdout=subprocess.PIPE)
    if set(nets.stdout.decode().splitlines()) - {"bridge", "host", "none"}:
        raise ValueError("custom Docker networks present")


def isolation_args(name, image):
    if not re.fullmatch(r"dsig-pra-[0-9a-f]{32}", name):
        raise ValueError("invalid rehearsal name")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("immutable image ID required")
    return ["run", "--rm", "-i", "--name", name, "--pull", "never",
            "--network", "none", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m,mode=1777",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "10001:10001", "--memory", "768m", "--pids-limit", "128",
            "--log-driver", "none", "--entrypoint", "python", image, "-c", WORKER]


# Only the backup key is necessary for a structural restore. Fresh admin token
# prevents access using the original administrative credential.
WORKER = r"""
import json, os, pathlib, secrets, sqlite3, subprocess, sys, time, urllib.request
from contextlib import closing
import operations
key = sys.stdin.buffer.readline(256).strip().decode("ascii")
os.environ.update(DSIG_ENV="REC", DSIG_DB="/tmp/restored.sqlite3",
                  DSIG_BACKUP_KEY=key, DSIG_ADMIN_TOKEN=secrets.token_urlsafe(48),
                  DSIG_HTTPS_ORIGIN="https://recovery.invalid", DSIG_CLAMD_SOCKET="")
backup = pathlib.Path("/tmp/backup.dsigbak")
data = sys.stdin.buffer.read(operations.MAX_ENCRYPTED_BYTES + 1)
if not data or len(data) > operations.MAX_ENCRYPTED_BYTES:
    raise ValueError("invalid backup size")
operations.write_new(backup, data)
db = pathlib.Path(os.environ["DSIG_DB"])
operations.restore_isolated(backup, db, "/tmp/never-active.sqlite3", "/app/dist")
backup.unlink()
with closing(operations.readonly(db)) as conn:
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("foreign key violations")
    if conn.execute("SELECT count(*) FROM sessions").fetchone() != (0,):
        raise ValueError("old sessions retained")
    count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
os.environ.pop("DSIG_BACKUP_KEY", None)
app = subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
try:
    for attempt in range(30):
        if app.poll() is not None:
            raise ValueError("application exited")
        try:
            for endpoint, expected in (("health", "ok"), ("ready", "ready")):
                with urllib.request.urlopen("http://127.0.0.1:8080/api/" + endpoint, timeout=2) as res:
                    if json.load(res)["status"] != expected:
                        raise ValueError("unexpected health status")
            break
        except OSError:
            time.sleep(1)
    else:
        raise ValueError("application unavailable")
    print(json.dumps({"sqlite_integrity": "PASS", "foreign_keys": "PASS",
                      "sessions_invalidated": True, "tables": count,
                      "health": "PASS", "ready": "PASS"}))
finally:
    app.terminate()
    try:
        app.wait(timeout=5)
    except subprocess.TimeoutExpired:
        app.kill()
        app.wait()
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-tar", required=True, type=Path)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--backup-sha256", required=True)
    parser.add_argument("--dedicated-recovery-host", action="store_true", required=True)
    args = parser.parse_args()
    start = time.monotonic()
    name = "dsig-pra-" + uuid.uuid4().hex
    try:
        command = isolation_args(name, args.image_id)
        require_empty_host()
        private_input(args.image_tar, args.image_sha256)
        private_input(args.backup, args.backup_sha256)
        # A trusted, separately verified Docker save archive is mandatory.
        docker("load", "--input", str(args.image_tar), stdout=subprocess.DEVNULL)
        actual = docker("image", "inspect", "--format", "{{.Id}}", args.image_id,
                        stdout=subprocess.PIPE).stdout.decode().strip()
        if actual != args.image_id:
            raise ValueError("image ID mismatch")
        require_empty_host()
        key = getpass.getpass("Backup Fernet key (not logged): ")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}=", key):
            raise ValueError("invalid key format")
        # Temporary anonymous file contains encrypted backup and key only.
        # Use memory rather than a named file on disk.
        with open(args.backup, "rb") as source:
            payload = source.read(128 * 1024**2 + 1)
        if len(payload) > 128 * 1024**2 or hashlib.sha256(payload).hexdigest() != args.backup_sha256:
            raise ValueError("backup size or digest mismatch")
        result = docker(*command, input=key.encode() + b"\n" + payload,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        report = json.loads(result.stdout)
        if any(report.get(k) != "PASS" for k in ("sqlite_integrity", "foreign_keys", "health", "ready")):
            raise ValueError("incomplete restore report")
        report.update(image_id=actual, elapsed_seconds=round(time.monotonic()-start, 2),
                      production_authorized=False, full_disaster_recovery_test=False)
        print(json.dumps(report))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("FAIL: recovery rehearsal (" + type(exc).__name__ + ")")
        return 1
    finally:
        # --rm removes a successful or exited container. On timeout, remove only
        # the uniquely named rehearsal container, never prune images or volumes.
        try:
            docker("rm", "-f", name, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


if __name__ == "__main__":
    raise SystemExit(main())
