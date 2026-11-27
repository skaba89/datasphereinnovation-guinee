"""Private runtime preflight with a lock retained for the caller's lifetime."""
import os
import re
import sqlite3
from pathlib import Path
from contextlib import closing, contextmanager, ExitStack
import prod_config
import prod_private_data_lifecycle as lifecycle
import prod_private_volume_init as volume
import prod_named_bootstrap as named
import prod_private_scanner as scanner
import authentication

DATA=Path('/app/data')
DB=DATA/'requests.sqlite3'

def _check(rec,candidate,stack):
    checks=dict.fromkeys(('identity','configuration','data','named_mfa','scanner'),'NOT_RUN')
    result=dict(status='FAIL',checks=checks,startup_authorized=False,production_authorized=False)
    try:
        checks['identity']='FAIL'
        env=dict(os.environ)
        if (os.getuid(),os.getgid())!=(10001,10001) or env.get('DSIG_CONTAINER')!='1':
            return result
        if env.get('DSIG_DB')!=str(DB) or 'DSIG_ADMIN_TOKEN' in env:
            return result
        checks['identity']='PASS'
        checks['configuration']=prod_config.inspect(env,rec,candidate)['status']
        if checks['configuration']!='PASS':
            return result
        checks['data']='FAIL'
        path,_=stack.enter_context(volume.exclusive(DATA))
        if lifecycle.inspect(path)['state']!='EXISTING_SCHEMA':
            return result
        checks['data']='PASS'
        checks['named_mfa']='FAIL'
        with closing(sqlite3.connect(DB.absolute().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if named.readiness(db)['status']!='PASS':
                return result
            rows=db.execute("SELECT m.secret FROM mfa m JOIN accounts a ON a.id=m.account_id WHERE a.role='ADMIN' AND a.enabled=1").fetchall()
            if not all(re.fullmatch('[A-Z2-7]{32}',authentication.decrypt_secret(row[0])) for row in rows):
                return result
        checks['named_mfa']='PASS'
        checks['scanner']=scanner.inspect()['status']
        if checks['scanner']!='PASS':
            return result
        result['status']='PASS'
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,authentication.InvalidToken):
        pass
    return result

@contextmanager
def locked_preflight(rec,candidate):
    """Keep the cooperative directory lock throughout the caller's context.
    No listener, permit consumption or startup authority. Failure releases
    the lock before returning. Exceptions from the caller propagate.
    """
    with ExitStack() as stack:
        result=_check(rec,candidate,stack)
        if result['status']!='PASS':
            stack.close()
        yield result

def inspect(rec,candidate):
    """Read-only legacy snapshot; the lock is released before return."""
    with locked_preflight(rec,candidate) as result:
        return result
