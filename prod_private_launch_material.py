"""Public runtime launch material, separate from the host signing authority.

Never publish private keys, raw Docker observations or REC credentials.
The runtime mount must be read-only and owned by the trusted host.
"""
import base64
import json
import os
import stat
from pathlib import Path
import prod_authorization as auth
import prod_private_runtime_contract as contract
import prod_private_launch_socket as channel
import prod_private_launch_topology as topology
import prod_review

NAME = 'launch-material.json'
LIMIT = 16384


def encode(*, envelope, public, approved_pin, approved_measurements):
    if contract.verify(envelope, public, authority_pin=approved_pin,
                       expected=approved_measurements)['status'] != 'PASS':
        raise ValueError('invalid launch material')
    raw = auth.canonical(dict(envelope=envelope,
        public=base64.b64encode(public).decode('ascii'),
        authority_pin=approved_pin, expected=approved_measurements))
    if len(raw) > LIMIT:
        raise ValueError('oversized material')
    return raw


def decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT:
        raise ValueError('invalid material length')
    value = prod_review.decode(raw)
    if set(value) != {'envelope', 'public', 'authority_pin', 'expected'}:
        raise ValueError('invalid material fields')
    public = base64.b64decode(value['public'], validate=True)
    if contract.verify(value['envelope'], public, authority_pin=value['authority_pin'],
                       expected=value['expected'])['status'] != 'PASS':
        raise ValueError('invalid launch material')
    return dict(envelope=value['envelope'], public=public,
                authority_pin=value['authority_pin'], expected=value['expected'])


def publish(**kwargs):
    """Host-only, exclusive publication. Caller manages one-shot cleanup."""
    directory = channel._directory(topology.HOST_CHANNEL, host=True)
    raw = encode(**kwargs)
    path = directory / NAME
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fchown(stream.fileno(), 0, 10001)
        os.fchmod(stream.fileno(), 0o440)
        os.fsync(stream.fileno())
    dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def load():
    """Trust the fixed host-owned mount, not a caller-provided path or envelope."""
    directory = channel._directory(topology.CHANNEL, host=False)
    fd = os.open(directory / NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_gid != 10001 or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_nlink != 1):
            raise ValueError('unsafe launch material')
        return decode(stream.read(LIMIT + 1))
