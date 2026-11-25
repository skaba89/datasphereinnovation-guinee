"""Offline PRA kit verification. Never extracts files or changes running services."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile

MAX_BYTES = 2 * 1024**3
MAX_FILES = 4096
MAX_MANIFEST = 1024**2
HEX = re.compile(r"[a-f0-9]{64}")


def safe_name(name):
    if name.startswith("./"):
        name = name[2:]
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "\\" in name or str(p) != name:
        raise ValueError("unsafe archive path")
    return name


def digest(stream):
    h = hashlib.sha256()
    while True:
        data = stream.read(1024 * 1024)
        if not data:
            return h.hexdigest()
        h.update(data)


def verify_tar(stream):
    hashes = {}
    seen = set()
    manifest = None
    total = 0
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            if member.isdir() and member.name in (".", "./"):
                continue
            name = safe_name(member.name)
            if name in seen or len(seen) >= MAX_FILES:
                raise ValueError("duplicate or excessive archive entries")
            seen.add(name)
            if member.isdir():
                continue
            if not member.isreg() or member.issparse() or member.size < 0:
                raise ValueError("unsupported archive member")
            total += member.size
            if total > MAX_BYTES:
                raise ValueError("archive size limit exceeded")
            with archive.extractfile(member) as data:
                if name == "SHA256SUMS":
                    if member.size > MAX_MANIFEST:
                        raise ValueError("checksum manifest too large")
                    manifest = data.read().decode("ascii")
                else:
                    hashes[name] = digest(data)
    if manifest is None or "MANIFEST.txt" not in hashes:
        raise ValueError("missing kit manifest")
    expected = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("invalid checksum record")
        name = safe_name(match[2])
        if name in expected:
            raise ValueError("duplicate checksum record")
        expected[name] = match[1]
    if hashes != expected:
        raise ValueError("internal checksums or coverage differ")
    return len(hashes)


def verify(path, expected):
    if not HEX.fullmatch(expected):
        raise ValueError("expected a trusted lowercase SHA256")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("archive must be private, regular and owned by caller")
        if digest(source) != expected:
            raise ValueError("outer checksum differs")
        source.seek(0)
        proc = subprocess.Popen(
            ["gpg", "--no-symkey-cache", "--decrypt"],
            stdin=source, stdout=subprocess.PIPE,
        )
        try:
            count = verify_tar(proc.stdout)
            # Drain to EOF so GPG verifies authentication before success.
            while proc.stdout.read(1024 * 1024):
                pass
            if proc.wait() != 0:
                raise ValueError("GPG verification failed")
            source.seek(0)
            if digest(source) != expected:
                raise ValueError("archive changed during verification")
            return count
        finally:
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True, help="trusted independent SHA256")
    args = parser.parse_args()
    try:
        count = verify(args.archive, args.sha256)
    except (OSError, ValueError, tarfile.TarError) as exc:
        # Do not expose paths or archive contents in logs.
        print("FAIL: PRA verification (" + type(exc).__name__ + ")")
        return 1
    print(f"PASS: {count} checksummed files; GPG and outer SHA256 verified")
    print("NOTE: no extraction, deployment or disaster recovery test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
