"""Combined offline review. No runtime activation or deployment."""
import hashlib
import json
import re
from datetime import datetime, timezone

import prod_authorization
import prod_compose
import prod_config
import prod_replay
import prod_trust

GATES = {f'G{i:02d}' for i in range(1, 11)}
MAX_INPUT = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_INPUT:
        raise ValueError('invalid input')
    return json.loads(data.decode('utf-8'), object_pairs_hook=prod_trust.unique_object)


def complete(data, commit):
    if not isinstance(data, dict) or data.get('commit') != commit:
        return False
    gates = data.get('gates')
    return (isinstance(gates, dict) and set(gates) == GATES
            and all(isinstance(g, dict) and g.get('status') == 'PASS'
                    and isinstance(g.get('reviewer'), str) and bool(g['reviewer'].strip())
                    and isinstance(g.get('evidence'), str) and bool(g['evidence'].strip())
                    for g in gates.values()))


def review(*, compose_bytes, evidence_bytes, rec, candidate, envelope,
           registry_bytes, pinned_sha256, expected_commit, expected_image,
           expected_port, ledger_path, now=None, dry_run=False):
    checks = dict.fromkeys(('input', 'topology', 'configuration', 'evidence_completeness',
                            'signed_binding', 'single_use'), 'NOT_RUN')
    try:
        checks['input'] = 'FAIL'
        if not isinstance(expected_commit, str) or not re.fullmatch(r'[0-9a-f]{40}', expected_commit):
            raise ValueError('invalid expected commit')
        if not isinstance(expected_image, str) or not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', expected_image):
            raise ValueError('invalid expected image')
        compose = decode(compose_bytes)
        evidence = decode(evidence_bytes)
        checks['input'] = 'PASS'
        checks['topology'] = prod_compose.validate(compose, expected_image, expected_port)['status']
        if checks['topology'] != 'PASS':
            raise ValueError('topology rejected')
        checks['configuration'] = prod_config.inspect(compose['services']['app']['environment'],
                                                       rec, candidate)['status']
        if checks['configuration'] != 'PASS':
            raise ValueError('configuration rejected')
        checks['evidence_completeness'] = 'PASS' if complete(evidence, expected_commit) else 'FAIL'
        if checks['evidence_completeness'] != 'PASS':
            raise ValueError('incomplete evidence')
        expected = dict(commit=expected_commit, image_digest=expected_image.rsplit('@', 1)[1],
                        config_sha256=digest(compose_bytes), evidence_sha256=digest(evidence_bytes))
        current = datetime.now(timezone.utc) if now is None else now
        checks['signed_binding'] = prod_trust.verify(envelope, registry_bytes, pinned_sha256,
                                                     now=current, **expected)['status']
        if checks['signed_binding'] != 'PASS':
            raise ValueError('signature rejected')
        if dry_run is True:
            return {'status': 'PASS', 'checks': checks, 'production_authorized': False,
                    'dry_run': True, 'authorization_consumed': False}
        # Consumption occurs last and re-verifies trust in the transactional ledger.
        checks['single_use'] = prod_replay.consume(ledger_path, envelope, registry_bytes,
                                                   pinned_sha256, now=current, **expected)['status']
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, RecursionError):
        pass
    return {'status': 'PASS' if all(v == 'PASS' for v in checks.values()) else 'FAIL',
            'checks': checks, 'production_authorized': False}
