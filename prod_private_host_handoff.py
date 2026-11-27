"""Host-side bridge for one accepted socket. No container start or HTTP bind."""
import os
import prod_private_authority as authority
import prod_private_runtime_contract as contract
import prod_private_peer_binding as binding
import prod_private_handoff_transport as transport
import prod_private_runtime_continuity as continuity
import prod_authorization as auth
import json


def exchange(sock, *, authority_path, approved_pin, approved_measurements, envelope, created_observation):
    """The operator supplies independently approved measurements and pin.
    Validate the actual running peer before the transport can consume a nonce.
    The CREATED observation must be captured and retained by the trusted host.
    This bridge checks continuity before the peer handoff; it does not launch Docker.
    """
    result = dict(status='FAIL', nonce_consumed=False,
                  startup_authorized=False, production_authorized=False)
    try:
        if os.geteuid() != 0:
            return result
        expected = json.loads(auth.canonical(approved_measurements))
        created = json.loads(auth.canonical(created_observation))
        key, public, ledger = authority.load(authority_path, approved_pin=approved_pin)
        if contract.verify(envelope, public, authority_pin=approved_pin,
                           expected=expected)['status'] != 'PASS':
            return result
        if continuity.inspect(created=created, approved_digest=expected['runtime_sha256'],
                              container_id=expected['container_id'])['status'] != 'PASS':
            return result
        if binding.inspect(sock, container_id=expected['container_id'],
                           image_id=expected['image_id'],
                           expected_uid=10001)['status'] != 'PASS':
            return result
        if continuity.inspect(created=created, approved_digest=expected['runtime_sha256'],
                              container_id=expected['container_id'])['status'] != 'PASS':
            return result
        return transport.host_exchange(sock, expected_uid=10001,
            ledger_path=ledger, envelope=envelope, signing_key=key,
            authority_pin=approved_pin, expected=expected)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return result
    finally:
        sock.close()
