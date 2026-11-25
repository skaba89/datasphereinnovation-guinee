"""Prepare a selective REC operations release bundle from a trusted Git commit.

No live file replacement, systemctl mutation, container restart or deployment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

GROUPS = {
    "b2": ("scripts/rec_b2.py", "scripts/export-rec-b2.py", "scripts/audit-rec-b2.py"),
    "outbox": ("scripts/rec_incident_state.py", "scripts/rec_alert_outbox.py",
               "deploy/systemd/dsig-rec-outbox-observe.service",
               "deploy/systemd/dsig-rec-outbox-observe.timer",
               "deploy/systemd/dsig-rec-outbox-deliver.service",
               "deploy/systemd/dsig-rec-outbox-deliver.timer"),
    "health": ("scripts/rec_operations_health.py",),
}
MAX_FILE = 1024 * 1024


def selected(groups):
    names = set(groups)
    if not names or not names <= GROUPS.keys():
        raise ValueError("unknown or empty release selection")
    if "health" in names and not {"b2", "outbox"} <= names:
        raise ValueError("health requires B2 and outbox components")
    return sorted(path for group in names for path in GROUPS[group])


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=30).stdout


def private_dir(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private owned directory required")


def committed_file(repo, commit, path):
    row = git(repo, "ls-tree", commit, "--", path).decode("utf-8").strip()
    if not row:
        raise ValueError("missing committed file")
    meta, name = row.split("\t", 1)
    mode, kind, oid = meta.split()
    if name != path or kind != "blob" or mode not in ("100644", "100755"):
        raise ValueError("unsupported Git tree entry")
    if int(git(repo, "cat-file", "-s", oid)) > MAX_FILE:
        raise ValueError("committed file too large")
    data = git(repo, "cat-file", "blob", oid)
    if not data or len(data) > MAX_FILE:
        raise ValueError("invalid committed file size")
    return mode, data


def ensure_private_dir(path):
    # pathlib mkdir(parents=True) applies mode only to the leaf.
    # Create every missing ancestor explicitly, independent of a permissive umask.
    try:
        private_dir(path)
    except FileNotFoundError:
        ensure_private_dir(path.parent)
        path.mkdir(mode=0o700)
        private_dir(path)


def write_private(path, data):
    ensure_private_dir(path.parent)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def prepare(repo, commit, parent, groups):
    private_dir(parent)
    paths = selected(groups)
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("full commit SHA required")
    if git(repo, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit:
        raise ValueError("commit mismatch")
    files = {path: committed_file(repo, commit, path) for path in paths}
    destination = Path(tempfile.mkdtemp(prefix="dsig-rec-release-", dir=parent))
    metadata = {}
    for path, (mode, data) in files.items():
        write_private(destination / "payload" / path, data)
        metadata[path] = {"sha256": hashlib.sha256(data).hexdigest(),
                          "git_mode": mode, "size": len(data)}
    report = {
        "environment": "REC", "commit": commit,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "groups": sorted(set(groups)), "files": metadata,
        "status": "STAGED_ONLY", "production_authorized": False,
        "installed": False, "services_activated": False,
        "required_before_install": [
            "v179_cycle_qualified", "candidate_ci_verified", "isolated_regression_passed",
            "maintenance_window_approved", "current_files_and_units_backed_up",
            "rollback_rehearsed", "operator_approval",
        ],
    }
    write_private(destination / "manifest.json", json.dumps(report, indent=2).encode())
    return dict(report, bundle=destination.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--private-stage-parent", type=Path, required=True)
    parser.add_argument("--component", choices=sorted(GROUPS), action="append", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(prepare(args.repo, args.commit, args.private_stage_parent, args.component), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "installed": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
