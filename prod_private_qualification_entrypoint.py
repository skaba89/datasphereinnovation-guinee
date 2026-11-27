"""Executable isolated qualification only; never starts production business HTTP."""
import os
import socket
from prod_private_handoff_transport import recipient_exchange
from prod_private_http_transport import create_isolated

def prepare(sock,*,expected_uid,envelope,public,authority_pin,expected):
    """Open a real loopback HTTP listener only after a successful handoff.
    This is a DEV qualification path and cannot serve business data.
    Caller owns the returned server and must close it.
    """
    if os.environ.get('DSIG_ENV')!='DEV':
        sock.close()
        raise ValueError('qualification only in DEV')
    result=recipient_exchange(sock,expected_uid=expected_uid,envelope=envelope,
                              public=public,authority_pin=authority_pin,expected=expected)
    if result['status']!='PASS':
        raise ValueError('handoff refused')
    return create_isolated()
