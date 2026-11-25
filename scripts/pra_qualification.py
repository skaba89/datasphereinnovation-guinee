"""Offline REC PRA evidence register. Completeness is not authorization."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

GATES = (
    "kits_verified", "independent_secrets", "independent_host",
    "data_snapshot_verified", "docker_sqlite_restore", "systemd_clamav",
    "caddy_https", "business_acceptance", "notifications_isolated",
    "automatic_backup_cycle", "rollback_exercised",
)
HEX = re.compile(r"[a-f0-9]{64}")
MAX_EVIDENCE = 16 * 1024**2


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("UTC timestamps required")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def evidence_ok(root, entry):
    if not isinstance(entry, dict) or entry.get("status") != "PASS":
        return False
    reviewer = entry.get("reviewer")
    name = entry.get("file")
    digest = entry.get("sha256")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return False
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", name):
        return False
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        return False
    path = root / name
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as handle:
        data = handle.read(MAX_EVIDENCE + 1)
    return 0 < len(data) <= MAX_EVIDENCE and hashlib.sha256(data).hexdigest() == digest


def assess(register, root, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(register, dict) or register.get("environment") != "REC":
        raise ValueError("REC register required")
    commit = register.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("commit required")
    gates = register.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(GATES):
        raise ValueError("exact gate register required")
    failures = [gate for gate in GATES if not evidence_ok(root, gates[gate])]
    rpo = rto = None
    timing = register.get("timing")
    if timing is not None:
        if not isinstance(timing, dict):
            raise ValueError("invalid timing")
        snapshot = timestamp(timing.get("snapshot_consistency_utc"))
        incident = timestamp(timing.get("exercise_start_utc"))
        recovered = timestamp(timing.get("business_recovery_utc"))
        if not snapshot <= incident <= recovered <= now:
            raise ValueError("invalid chronological order")
        # Only calculate metrics when the reviewer supplied matching evidence.
        if all(gate not in failures for gate in
               ("data_snapshot_verified", "independent_host", "business_acceptance")):
            rpo = (incident - snapshot).total_seconds()
            rto = (recovered - incident).total_seconds()
    if rpo is None or rto is None:
        failures.append("timing_not_demonstrated")
    else:
        if rpo > 86400:
            failures.append("rpo_target_exceeded")
        if rto > 14400:
            failures.append("rto_target_exceeded")
    return {
        "environment": "REC", "commit": commit,
        "missing_or_unverified": failures,
        "observed_rpo_seconds": rpo, "observed_rto_seconds": rto,
        "proposed_rpo_target_seconds": 86400,
        "proposed_rto_target_seconds": 14400,
        "decision": "NO_GO" if failures else "REVIEW_REQUIRED",
        "production_authorized": False,
        "evidence_authenticity_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("register", type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.evidence_dir.is_symlink() or not args.evidence_dir.is_dir():
            raise ValueError("invalid evidence directory")
        with args.register.open(encoding="utf-8") as source:
            report = assess(json.load(source), args.evidence_dir)
    except (OSError, ValueError) as exc:
        print(json.dumps({"decision": "NO_GO", "production_authorized": False,
                          "error": type(exc).__name__}))
        return 1
    print(json.dumps(report, indent=2))
    return 1 if report["missing_or_unverified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
