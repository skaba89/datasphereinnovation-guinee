"""Read-only snapshot of selected installed REC systemd units; never activate units."""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile

from rec_release_bundle import MAX_FILE, private_dir, write_private
from rec_release_preflight import sha

NAMES = tuple(f"dsig-rec-{name}.{kind}" for name in ("backup", "b2", "backup-audit", "monitor",
                 "outbox-observe", "outbox-deliver") for kind in ("service", "timer"))
REQUIRED = frozenset(n for n in NAMES if "-outbox-" not in n) | {"dsig-rec-alert@.service"}
OPTIONAL = frozenset(NAMES) - REQUIRED
UNITS = REQUIRED | OPTIONAL


def source_dir(path, owner):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
        raise ValueError("unsafe source directory")


def source_file(path, owner):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as inp:
        info = os.fstat(inp.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o7022:
            raise ValueError("unsafe source file")
        data = inp.read(MAX_FILE + 1)
        if not data or len(data) > MAX_FILE:
            raise ValueError("invalid source size")
        return data, stat.S_IMODE(info.st_mode)


def capture(source, parent, owner):
    source_dir(source, owner)
    private_dir(parent)
    files = {}
    absent = []
    files_empty = []
    for name in sorted(UNITS):
        try:
            files[name] = source_file(source / name, owner)
        except FileNotFoundError:
            if name in REQUIRED:
                raise ValueError("required REC unit missing") from None
            absent.append(name)
        directory = source / (name + ".d")
        try:
            source_dir(directory, owner)
        except FileNotFoundError:
            absent.append(name + ".d")
            continue
        # An empty drop-in directory has no effective configuration; record its presence.
        for child in sorted(directory.iterdir()):
            if not child.name.endswith(".conf"):
                raise ValueError("unexpected drop-in entry")
            files[directory.name + "/" + child.name] = source_file(child, owner)
        if not any(n.startswith(directory.name + "/") for n in files):
            files_empty.append(directory.name)
    destination = Path(tempfile.mkdtemp(prefix="dsig-rec-unit-snapshot-", dir=parent))
    metadata = {}
    for name, (data, mode) in files.items():
        write_private(destination / "payload" / name, data)
        metadata[name] = {"sha256": sha(data), "original_mode": mode, "original_uid": owner}
    report = {"environment": "REC", "status": "SNAPSHOT_ONLY",
              "source_scope": "etc-systemd-system-selected", "files": metadata,
              "absent": sorted(absent), "empty_dropin_dirs": sorted(files_empty),
              "effective_config_verified": False, "enablement_verified": False,
              "secrets_review_required": True, "rollback_rehearsed": False,
              "production_authorized": False}
    write_private(destination / "manifest.json", json.dumps(report, indent=2).encode())
    return {"snapshot": destination.name, "files_count": len(files),
            "status": "SNAPSHOT_ONLY", "production_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            raise ValueError("root required to capture root-owned unit files")
        print(json.dumps(capture(Path("/etc/systemd/system"), args.private_output, 0)))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__, "production_authorized": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
