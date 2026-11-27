"""Private runtime admission integration. CLI remains locked until host provisioning.
The supervisor must independently measure the executable container and provision
the authority pin; never derive expected values from the signed envelope.
"""
import os
from contextlib import contextmanager
import prod_private_runtime_contract as contract
import prod_private_runtime_preflight as preflight
import prod_private_handoff_transport as transport
import server

@contextmanager
def admission(sock,*,rec,candidate,envelope,public,authority_pin,expected):
    """Keep preflight lock throughout the admitted context; no HTTP bind here.
    Trusted integration caller only. A PASS is not production authorization.
    """
    try:
        if os.environ.get('DSIG_ENV')!='PROD' or server.ADMIN_TOKEN:
            raise ValueError('private runtime configuration refused')
        if contract.verify(envelope,public,authority_pin=authority_pin,expected=expected)['status']!='PASS':
            raise ValueError('runtime contract refused')
        with preflight.locked_preflight(rec,candidate) as report:
            if report['status']!='PASS':
                raise ValueError('runtime preflight refused')
            receipt=transport.recipient_exchange(sock,expected_uid=0,envelope=envelope,
                public=public,authority_pin=authority_pin,expected=expected)
            if receipt['status']!='PASS':
                raise ValueError('host handoff refused')
            if contract.verify(envelope,public,authority_pin=authority_pin,expected=expected)['status']!='PASS':
                raise ValueError('runtime contract expired')
            yield {'status':'PASS','production_authorized':False,'startup_authorized':False}
    finally:
        sock.close()

def main():
    raise SystemExit('PROD startup disabled: trusted host provisioning and executable measurements required')

if __name__=='__main__':
    main()
