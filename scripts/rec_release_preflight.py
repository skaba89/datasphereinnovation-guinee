"""Verify a staged REC bundle and prepare a B2 rollback snapshot, without installing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from rec_release_bundle import GROUPS, MAX_FILE, committed_file, private_dir, selected, write_private


def read_file(path, private=True):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("regular file required")
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != os.getuid() or (private and mode != 0o600):
            raise ValueError("unexpected owner or permissions")
        data = source.read(MAX_FILE + 1)
        if not data or len(data) > MAX_FILE:
            raise ValueError("invalid file size")
        return data, mode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    private_dir(root)
    files = set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            private_dir(Path(directory) / name)
        for name in names:
            path = Path(directory) / name
            files.add(path.relative_to(root).as_posix())
    return files


def verify_bundle(bundle, repo, commit):
    private_dir(bundle)
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("trusted full commit required")
    manifest = json.loads(read_file(bundle / "manifest.json")[0])
    if manifest.get("environment") != "REC" or manifest.get("commit") != commit:
        raise ValueError("environment or commit mismatch")
    if manifest.get("status") != "STAGED_ONLY" or any(manifest.get(k) is not False for k in
            ("production_authorized", "installed", "services_activated")):
        raise ValueError("invalid staging status")
    paths = selected(manifest["groups"])
    if set(manifest["files"]) != set(paths):
        raise ValueError("incomplete manifest")
    payload = bundle / "payload"
    if set(p.name for p in bundle.iterdir()) != {"manifest.json", "payload"} or inventory(payload) != set(paths):
        raise ValueError("unexpected bundle contents")
    for path in paths:
        data, _ = read_file(payload / path)
        mode, expected = committed_file(repo, commit, path)
        metadata = {"sha256": sha(expected), "git_mode": mode, "size": len(expected)}
        if data != expected or manifest["files"][path] != metadata:
            raise ValueError("bundle differs from trusted Git commit")
    return paths


def snapshot_b2(active, parent):
    """Copy only three existing B2 scripts; no unit or secret file is read."""
    private_dir(parent)
    scripts = active / "scripts"
    if active.is_symlink() or scripts.is_symlink():
        raise ValueError("symlinked source directory")
    inputs = {path: read_file(active / path, private=False) for path in GROUPS["b2"]}
    if any(mode & 0o022 or mode & 0o7000 for _, mode in inputs.values()):
        raise ValueError("unsafe source file permissions")
    destination = Path(tempfile.mkdtemp(prefix="dsig-rec-b2-rollback-", dir=parent))
    metadata = {}
    for path, (data, mode) in inputs.items():
        write_private(destination / "payload" / path, data)
        metadata[path] = {"sha256": sha(data), "original_mode": mode}
    write_private(destination / "manifest.json", json.dumps({
        "environment": "REC", "files": metadata, "status": "SNAPSHOT_ONLY",
        "units_backed_up": False, "rollback_rehearsed": False,
        "production_authorized": False,
    }, indent=2).encode())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--active-b2-source", type=Path)
    parser.add_argument("--rollback-parent", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        paths = verify_bundle(args.bundle, args.repo, args.commit)
        if bool(args.active_b2_source) != bool(args.rollback_parent):
            raise ValueError("snapshot options must be paired")
        snapshot = None
        if args.active_b2_source:
            if not set(GROUPS["b2"]) <= set(paths):
                raise ValueError("B2 component required")
            snapshot = snapshot_b2(args.active_b2_source, args.rollback_parent).name
        print(json.dumps({"environment": "REC", "bundle_integrity": "PASS",
                          "rollback_snapshot": snapshot, "installed": False,
                          "deployment_authorized": False, "production_authorized": False}))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__,
                          "deployment_authorized": False, "production_authorized": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
