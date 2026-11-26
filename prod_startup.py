"""Read-only first-start filesystem and environment preflight.

Does not initialize a database or grant production authorization.
"""
import os
import stat
from pathlib import Path

import prod_config

DB_PATH = '/app/data/requests.sqlite3'


def inspect(env, rec, candidate, *, data_dir, scanner_socket, expected_uid, expected_gid):
    checks = dict.fromkeys(('configuration', 'identity', 'empty_data_directory',
                            'scanner_socket'), 'NOT_RUN')
    try:
        checks['configuration'] = prod_config.inspect(env, rec, candidate)['status']
        if checks['configuration'] != 'PASS':
            raise ValueError('configuration rejected')
        checks['identity'] = 'FAIL'
        if (type(expected_uid) is not int or type(expected_gid) is not int
                or expected_uid <= 0 or expected_gid <= 0
                or env.get('DSIG_DB') != DB_PATH):
            raise ValueError('invalid identity')
        if os.getuid() != expected_uid or os.getgid() != expected_gid:
            raise ValueError('unexpected identity')
        checks['identity'] = 'PASS'
        checks['empty_data_directory'] = 'FAIL'
        data = Path(data_dir)
        info = data.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid
                or info.st_gid != expected_gid or stat.S_IMODE(info.st_mode) != 0o700
                or any(data.iterdir())):
            raise ValueError('data directory not private and empty')
        checks['empty_data_directory'] = 'PASS'
        checks['scanner_socket'] = 'FAIL'
        scanner = Path(scanner_socket)
        info = scanner.lstat()
        if not stat.S_ISSOCK(info.st_mode):
            raise ValueError('invalid scanner socket')
        checks['scanner_socket'] = 'PASS'
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'database_initialized':False,'production_authorized':False}
