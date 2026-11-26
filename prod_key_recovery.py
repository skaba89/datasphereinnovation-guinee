"""Offline key recovery kit. No provisioning of live PROD, no remote upload."""
import base64
import hashlib
import json
import os
import hmac
import re
from pathlib import Path
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.fernet import Fernet
import operations
import prod_backup_review_signing as signing
import prod_backup_orchestrator as guard

MAGIC=b'DSIG-KEY-RECOVERY-V1\x00'
N=2**17
ROLES=('backup','mfa','document','signer')


def raw_fernet(value):
    if not isinstance(value,bytes):
        raise ValueError('invalid key')
    raw=base64.b64decode(value,altchars=b'-_',validate=True)
    if len(raw)!=32 or base64.urlsafe_b64encode(raw)!=value:
        raise ValueError('invalid key encoding')
    Fernet(value)
    return raw


def identifiers(keys, forbidden):
    if not isinstance(keys,dict) or set(keys)!=set(ROLES):
        raise ValueError('invalid key inventory')
    if not isinstance(forbidden,(set,frozenset)) or len(forbidden)<2 or any(not isinstance(x,str) or not re.fullmatch(r'[0-9a-f]{64}',x) for x in forbidden):
        raise ValueError('missing independent reference fingerprints')
    raw={role:raw_fernet(keys[role]) for role in ROLES[:-1]}
    seed=keys['signer']
    if not isinstance(seed,bytes) or len(seed)!=32:
        raise ValueError('invalid signer')
    raw['signer']=seed
    fingerprints={role:hashlib.sha256(value).hexdigest() for role,value in raw.items()}
    if len(set(fingerprints.values()))!=4 or set(fingerprints.values())&forbidden:
        raise ValueError('key reuse')
    public=Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    return dict(backup_id=fingerprints['backup'],mfa_id=fingerprints['mfa'],
                document_id=fingerprints['document'],signer_id=hashlib.sha256(public).hexdigest())


def derive(passphrase,salt):
    if not isinstance(passphrase,bytes) or not 20<=len(passphrase)<=1024:
        raise ValueError('recovery passphrase must contain at least 20 bytes')
    return Scrypt(salt=salt,length=32,n=N,r=8,p=1).derive(passphrase)


def pack(keys, *, passphrase, forbidden):
    pins=identifiers(keys,forbidden)
    salt=os.urandom(16)
    nonce=os.urandom(12)
    header=MAGIC+salt+nonce
    payload=json.dumps({role:base64.b64encode(keys[role]).decode('ascii') for role in ROLES},
                       sort_keys=True,separators=(',',':')).encode()
    blob=header+AESGCM(derive(passphrase,salt)).encrypt(nonce,payload,header)
    return blob,pins


def unpack(blob, *, passphrase, forbidden, expected_pins):
    if not isinstance(blob,bytes) or not len(MAGIC)+28+16<len(blob)<=4096 or not blob.startswith(MAGIC):
        raise ValueError('invalid recovery kit')
    i=len(MAGIC)
    salt=blob[i:i+16]
    nonce=blob[i+16:i+28]
    from cryptography.exceptions import InvalidTag
    try:
        plain=AESGCM(derive(passphrase,salt)).decrypt(nonce,blob[i+28:],blob[:i+28])
        payload=json.loads(plain)
        if not isinstance(payload,dict) or set(payload)!=set(ROLES):
            raise ValueError('invalid recovery payload')
        keys={role:base64.b64decode(payload[role],validate=True) for role in ROLES}
        pins=identifiers(keys,forbidden)
        if not isinstance(expected_pins,dict) or set(expected_pins)!=set(pins) or not all(
            isinstance(expected_pins[k],str) and hmac.compare_digest(pins[k],expected_pins[k]) for k in pins):
            raise ValueError('independent key pins mismatch')
    except (InvalidTag,ValueError,TypeError,KeyError,UnicodeError):
        raise ValueError('recovery kit authentication or identity failed') from None
    return keys


def generate():
    return dict(backup=Fernet.generate_key(),mfa=Fernet.generate_key(),
                document=Fernet.generate_key(),signer=os.urandom(32))


def write_kit(destination,keys,*,passphrase,forbidden):
    path=Path(destination)
    guard.private_dir(path.parent)
    blob,pins=pack(keys,passphrase=passphrase,forbidden=forbidden)
    if unpack(blob,passphrase=passphrase,forbidden=forbidden,expected_pins=pins)!=keys:
        raise ValueError('self recovery failed')
    operations.write_new(path,blob)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'sha256':hashlib.sha256(blob).hexdigest(),'pins':pins,
            'local_recovery_verified':True,'external_recovery_verified':False,
            'production_authorized':False}
