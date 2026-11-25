"""Rehearse replacement and rollback of the three REC B2 scripts in a new private directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from rec_release_bundle import GROUPS, private_dir, write_private, committed_file
from rec_release_preflight import inventory, read_file, sha, verify_bundle

PATHS = GROUPS["b2"]


def load_snapshot(snapshot):
    private_dir(snapshot)
    doc = json.loads(read_file(snapshot / "manifest.json")[0])
    if doc.get("environment") != "REC" or doc.get("status") != "SNAPSHOT_ONLY":
        raise ValueError("invalid rollback snapshot")
    if any(doc.get(key) is not False for key in
           ("units_backed_up", "rollback_rehearsed", "production_authorized")):
        raise ValueError("invalid rollback status")
    if set(doc["files"]) != set(PATHS):
        raise ValueError("incomplete rollback manifest")
    if set(p.name for p in snapshot.iterdir()) != {"manifest.json", "payload"}:
        raise ValueError("unexpected snapshot entries")
    if inventory(snapshot / "payload") != set(PATHS):
        raise ValueError("unexpected rollback payload")
    result = {}
    for name in PATHS:
        data, _ = read_file(snapshot / "payload" / name)
        meta = doc["files"][name]
        mode = meta["original_mode"]
        if type(mode) is not int or not 0 <= mode <= 0o777 or mode & 0o022 or not mode & 0o400:
            raise ValueError("unsafe original mode")
        if meta != {"sha256": sha(data), "original_mode": mode}:
            raise ValueError("rollback digest mismatch")
        result[name] = (data, mode)
    return result


def replace_file(root, name, entry):
    data, mode = entry
    path = root / name
    private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".replace-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fchmod(out.fileno(), mode)
            os.fsync(out.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        Path(tmp).unlink(missing_ok=True)


def verify_state(root, expected):
    if inventory(root) != set(expected):
        raise ValueError("unexpected rehearsal files")
    for name, entry in expected.items():
        if read_file(root / name, private=False) != entry:
            raise ValueError("rehearsal state mismatch")


def rehearse(bundle, snapshot, repo, commit, parent, fault_after=None):
    """Only write under a freshly allocated scratch directory; never execute copied scripts."""
    private_dir(parent)
    if not set(PATHS) <= set(verify_bundle(bundle, repo, commit)):
        raise ValueError("B2 component required")
    original = load_snapshot(snapshot)
    candidate = {}
    for name in PATHS:
        mode, data = committed_file(repo, commit, name)
        candidate[name] = (data, 0o755 if mode == "100755" else 0o644)
    work = Path(tempfile.mkdtemp(prefix="dsig-rec-rehearsal-", dir=parent))
    root = work / "sandbox"
    root.mkdir(mode=0o700)
    for name, (data, mode) in original.items():
        write_private(root / name, data)
        (root / name).chmod(mode)
    verify_state(root, original)
    installed = False
    failure = None
    try:
        for index, name in enumerate(PATHS, 1):
            replace_file(root, name, candidate[name])
            if fault_after == index:
                raise RuntimeError("injected replacement failure")
        verify_state(root, candidate)
        installed = True
    except (OSError, ValueError, RuntimeError) as exc:
        failure = type(exc).__name__
    finally:
        for name in PATHS:
            replace_file(root, name, original[name])
        verify_state(root, original)
    report = {
        "environment": "REC", "commit": commit, "directory": work.name,
        "status": "PASS" if installed and failure is None else "INSTALL_FAILED_ROLLBACK_PASS",
        "candidate_verified_in_sandbox": installed, "rollback_bytes_and_modes_verified": True,
        "failure": failure, "live_deployment_performed": False,
        "systemd_tested": False, "production_authorized": False,
        "original": {name: {"sha256": sha(data), "mode": mode}
                     for name, (data, mode) in original.items()},
    }
    write_private(work / "report.json", json.dumps(report, indent=2).encode())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--scratch-parent", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = rehearse(args.bundle, args.snapshot, args.repo, args.commit, args.scratch_parent)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__,
                          "live_deployment_performed": False, "production_authorized": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
