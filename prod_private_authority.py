"""Host-only authority provisioning. No automatic approval or launch.

Use an empty, root-owned 0700 directory under a trusted local parent.
Partial provisioning fails closed and must be reviewed manually.
"""
import hashlib
import hmac
import os
import stat
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import prod_private_runtime_replay as replay


def _directory(path):
    if os.geteuid() != 0:
        raise PermissionError('root authority required')
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('unsafe authority path')
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unsafe authority ancestor')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ValueError('unsafe authority directory')
    return fd


def _write(fd, name, value):
    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                  0o600, dir_fd=fd)
    with os.fdopen(out, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _read(fd, name, length):
    inp = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(inp, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('unsafe authority file')
        value = stream.read(length + 1)
        if len(value) != length:
            raise ValueError('invalid authority file length')
        return value


def provision(path):
    """Explicit one-time operation. Return only the public fingerprint."""
    fd = _directory(path)
    try:
        if os.listdir(fd):
            raise FileExistsError('authority directory is not empty')
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)
        pin = hashlib.sha256(public).hexdigest()
        _write(fd, 'authority.key', private)
        _write(fd, 'authority.pub', public)
        _write(fd, 'authority.pin', pin.encode('ascii'))
        replay.initialize(Path(path) / 'runtime-ledger.sqlite3')
        os.fsync(fd)
        return dict(status='PASS', authority_pin=pin,
                    startup_authorized=False, production_authorized=False)
    finally:
        os.close(fd)


def load(path, *, approved_pin):
    """Require a separately recorded operator pin, not an envelope-derived pin."""
    fd = _directory(path)
    try:
        private = _read(fd, 'authority.key', 32)
        public = _read(fd, 'authority.pub', 32)
        stored = _read(fd, 'authority.pin', 64).decode('ascii')
        key = Ed25519PrivateKey.from_private_bytes(private)
        derived = key.public_key().public_bytes(serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)
        actual = hashlib.sha256(public).hexdigest()
        if not isinstance(approved_pin, str) or not all((
                hmac.compare_digest(derived, public),
                hmac.compare_digest(actual, stored),
                hmac.compare_digest(actual, approved_pin))):
            raise ValueError('authority pin mismatch')
        ledger = Path(path) / 'runtime-ledger.sqlite3'
        info = ledger.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('unsafe ledger')
        return key, public, ledger
    finally:
        os.close(fd)
