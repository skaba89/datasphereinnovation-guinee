"""Stage verified REC system files for offline review; never install or enable units."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from pra_verify import safe_name

SERVICES = ("b2", "backup-audit", "backup", "contact", "invitations", "monitor")
UNITS = {"systemd/dsig-rec-alert@.service"} | {
    f"systemd/dsig-rec-{name}.{kind}" for name in SERVICES
    for kind in ("service", "timer")
}
DROPINS = {f"systemd/dsig-rec-{name}.service.d/alert.conf"
           for name in ("b2", "backup-audit", "backup", "monitor")}
CLAMAV = {"clamav/clamd.conf", "clamav/freshclam.conf"}
SELECTED = UNITS | DROPINS | CLAMAV
MAX_FILE = 1024 * 1024


def private_dir(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("private owned directory required")


def read_private(root, name):
    name = safe_name(name)
    path = root
    for part in name.split("/")[:-1]:
        path = path / part
        private_dir(path)
    path = root / name
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("private regular input required")
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError("configuration too large")
    return data


def stage(source, parent):
    private_dir(source)
    private_dir(parent)
    # Source is a manually extracted, previously V180-verified kit.
    expected = {}
    for line in read_private(source, "SHA256SUMS").decode("ascii").splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("invalid checksum entry")
        name = safe_name(match[2])
        if name in expected:
            raise ValueError("duplicate checksum entry")
        expected[name] = match[1]
    if not SELECTED <= expected.keys():
        raise ValueError("incomplete system kit")
    if {n for n in expected if n.startswith("systemd/")} != UNITS | DROPINS:
        raise ValueError("unexpected systemd configuration")
    files = {}
    for name in sorted(SELECTED):
        data = read_private(source, name)
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError("configuration checksum mismatch")
        files[name] = data
    # Nothing is written until all selected inputs are checked.
    destination = Path(tempfile.mkdtemp(prefix="dsig-pra-stage-", dir=parent))
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(data)
    report = {
        "units": len(UNITS), "dropins": len(DROPINS), "clamav_configs": len(CLAMAV),
        "sha256": {name: expected[name] for name in sorted(SELECTED)},
        "stage": destination.name, "installed": False, "activated": False,
        "requires_manual_review": True, "production_authorized": False,
    }
    with os.fdopen(os.open(destination / "report.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(report, f, indent=2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--private-stage-parent", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report = stage(args.source, args.private_stage_parent)
    except (OSError, ValueError) as exc:
        print("FAIL: staging (" + type(exc).__name__ + ")")
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
