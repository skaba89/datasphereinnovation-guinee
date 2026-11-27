"""DEV-only business qualification; never a PROD startup entrypoint."""
import os
import tempfile
from pathlib import Path
from contextlib import closing
import prod_named_bootstrap as named
import server
from prod_private_handoff_transport import recipient_exchange

def run(sock,*,expected_uid,envelope,public,authority_pin,expected,exercise):
    """Run a caller-supplied test against an isolated business listener.
    Dedicated process only: server globals are not thread-local.
    No production database, secrets or listener are used.
    """
    if os.environ.get('DSIG_ENV')!='DEV' or os.environ.get('DSIG_CONTAINER')!='1':
        sock.close()
        raise ValueError('disposable DEV container required')
    if os.environ.get('DSIG_ADMIN_TOKEN') or server.ADMIN_TOKEN:
        sock.close()
        raise ValueError('external admin token forbidden')
    result=recipient_exchange(sock,expected_uid=expected_uid,envelope=envelope,
        public=public,authority_pin=authority_pin,expected=expected)
    if result['status']!='PASS':
        raise ValueError('handoff refused')
    previous_db,previous_token=server.DB,server.ADMIN_TOKEN
    import threading
    from unittest.mock import patch
    from cryptography.fernet import Fernet
    class JoinedServer(server.BoundedHTTPServer):
        daemon_threads=False
        block_on_close=True
    with tempfile.TemporaryDirectory(prefix='dsig-business-qualification-') as root:
        try:
            server.DB=Path(root)/'requests.sqlite3'
            server.ADMIN_TOKEN=''
            server.RATE.clear()
            with patch.dict(os.environ,{'DSIG_MFA_KEY':Fernet.generate_key().decode(),
                'DSIG_DOCUMENT_KEY':Fernet.generate_key().decode(),
                'DSIG_BACKUP_KEY':Fernet.generate_key().decode(),
                'DSIG_MFA_REQUIRED_ROLES':'ADMIN,CLIENT,DIRECTION,CONTROLE,COMPTABLE,AUDITEUR','DSIG_HTTPS_ORIGIN':'https://qualification.invalid'}):
                with closing(server.connect()) as db:
                    rows=named.initialize_review(db,['alice.example','bob.example'])
                with JoinedServer(('127.0.0.1',0),server.Handler) as http:
                    thread=threading.Thread(target=http.serve_forever)
                    thread.start()
                    try:
                        exercise(http.server_port,rows)
                        with closing(server.connect()) as db:
                            if named.readiness(db)['status']!='PASS':
                                raise ValueError('named MFA readiness failed')
                    finally:
                        http.shutdown()
                        thread.join()
        finally:
            server.DB,server.ADMIN_TOKEN=previous_db,previous_token
            server.RATE.clear()
    return dict(status='PASS',qualification_only=True,production_authorized=False)
