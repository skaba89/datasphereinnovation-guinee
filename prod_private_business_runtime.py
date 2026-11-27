"""Private business runtime integration, not yet an executable CLI.

The trusted host must independently approve and publish launch material, and
authenticate the running container before issuing a one-shot receipt.
The locked production CLI and Compose remain unchanged pending qualification.
"""
import os
import prod_private_launch_material as material
import prod_private_launch_socket as channel
import prod_private_runtime_preflight as preflight
import prod_private_runtime_contract as contract
import prod_private_handoff_transport as transport
import prod_private_http_lifecycle as lifecycle
import server


def run():
    """Serve the existing business handler only after authenticated admission.

    The local database lock encloses the listener and the draining of handlers.
    No REC credentials are required or accepted here.
    """
    if (os.environ.get('DSIG_ENV') != 'PROD'
            or 'DSIG_ADMIN_TOKEN' in os.environ or server.ADMIN_TOKEN
            or server.DB != preflight.DB):
        raise ValueError('private runtime configuration refused')
    with lifecycle.termination_event() as stop:
        launch = material.load()
        with preflight.locked_local_preflight() as report:
            if report['status'] != 'PASS':
                raise ValueError('local preflight refused')
            if stop.is_set():
                return
            if contract.verify(**launch)['status'] != 'PASS':
                raise ValueError('launch contract refused')
            with channel.runtime_connection() as sock:
                receipt = transport.recipient_exchange(sock, expected_uid=0, **launch)
            if receipt['status'] != 'PASS':
                raise ValueError('host handoff refused')
            if contract.verify(**launch)['status'] != 'PASS':
                raise ValueError('launch contract expired')
            if stop.is_set():
                return
            # Docker publishes only host loopback:8320; the private container
            # must listen on its own interface, not on container loopback.
            with lifecycle.listener(('0.0.0.0', 8080)) as http:
                lifecycle.serve_until_stopped(http, stop)
