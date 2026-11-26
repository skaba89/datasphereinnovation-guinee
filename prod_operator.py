"""Read-only production review using private files and independent checkpoint inputs."""
import argparse
import base64
import json
import os
import stat
from pathlib import Path

import prod_checkpoint
import prod_review


def read_private(directory, name):
    directory = Path(directory)
    parent = directory.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError('unsafe directory')
    fd = os.open(directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > prod_review.MAX_INPUT):
            raise ValueError('unsafe file')
        data = stream.read(prod_review.MAX_INPUT + 1)
        if not 0 < len(data) <= prod_review.MAX_INPUT:
            raise ValueError('invalid size')
        return data


def inspect_bundle(directory, *, expected_commit, expected_image, expected_port,
                   pinned_sha256, anchor_public_key, expected_sequence, ledger_path, now=None):
    checks = dict.fromkeys(('private_inputs', 'checkpoint', 'review'), 'NOT_RUN')
    try:
        checks['private_inputs'] = 'FAIL'
        files = {name: read_private(directory, name) for name in
                 ('compose.json','evidence.json','rec.json','candidate.json',
                  'envelope.json','registry.json','checkpoint.json')}
        rec, candidate, envelope, checkpoint = (prod_review.decode(files[n]) for n in
            ('rec.json','candidate.json','envelope.json','checkpoint.json'))
        checks['private_inputs'] = 'PASS'
        checks['checkpoint'] = prod_checkpoint.verify(checkpoint,
            anchor_public_key=anchor_public_key, expected_sequence=expected_sequence,
            registry_bytes=files['registry.json'], ledger_path=ledger_path, now=now)['status']
        if checks['checkpoint'] != 'PASS':
            raise ValueError('checkpoint rejected')
        report = prod_review.review(compose_bytes=files['compose.json'],
            evidence_bytes=files['evidence.json'], rec=rec, candidate=candidate,
            envelope=envelope, registry_bytes=files['registry.json'],
            pinned_sha256=pinned_sha256, expected_commit=expected_commit,
            expected_image=expected_image, expected_port=expected_port,
            ledger_path=ledger_path, now=now, dry_run=True)
        checks['review'] = report['status']
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        pass
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'dry_run':True,'authorization_consumed':False,
            'production_authorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--ledger',required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--port',required=True,type=int)
    parser.add_argument('--registry-pin',required=True)
    parser.add_argument('--anchor-public-key',required=True,help='Independent raw Ed25519 public key in base64')
    parser.add_argument('--sequence',required=True,type=int)
    args=parser.parse_args()
    try:
        report=inspect_bundle(args.bundle,expected_commit=args.commit,expected_image=args.image,
            expected_port=args.port,pinned_sha256=args.registry_pin,
            anchor_public_key=base64.b64decode(args.anchor_public_key,validate=True),
            expected_sequence=args.sequence,ledger_path=args.ledger)
    except (ValueError,TypeError,OSError):
        report={'status':'FAIL','checks':{'input':'FAIL'},'dry_run':True,
                'authorization_consumed':False,'production_authorized':False}
    print(json.dumps(report))
    return int(report['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
