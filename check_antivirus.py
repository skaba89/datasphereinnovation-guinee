"""Explicit REC antivirus acceptance: clean and standard harmless EICAR test."""
import json
import os
import antivirus

EICAR = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'


def inspect():
    results = {'clean': 'FAIL', 'eicar_rejected': 'FAIL'}
    if os.environ.get('DSIG_ENV') != 'REC':
        return results
    try:
        antivirus.scan(b'DSIG harmless antivirus acceptance check')
        results['clean'] = 'PASS'
    except (antivirus.Infected, antivirus.Unavailable):
        pass
    try:
        antivirus.scan(EICAR)
    except antivirus.Infected:
        results['eicar_rejected'] = 'PASS'
    except antivirus.Unavailable:
        pass
    return results


if __name__ == '__main__':
    checks = inspect()
    print(json.dumps(checks))
    raise SystemExit(int(any(result != 'PASS' for result in checks.values())))
