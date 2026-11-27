"""Host orchestration for an independently approved CREATED container.

Production CLI remains locked. The trusted operator must supply a qualified
start action and independently approved measurements. No automatic approval.
"""
import json
import os
from contextlib import contextmanager
import prod_authorization as auth
import prod_backup_acquisition as acquisition
import prod_private_authority as authority
import prod_private_executable_binding as binding
import prod_private_runtime_continuity as continuity
import prod_private_runtime_permit as permit
import prod_private_launch_material as material
import prod_private_launch_socket as channel
import prod_private_host_handoff as handoff
import prod_private_launch_topology as topology
import prod_review


@contextmanager
def published(**kwargs):
    directory = channel._directory(topology.HOST_CHANNEL, host=True)
    path = directory / material.NAME
    material.publish(**kwargs)
    info = path.lstat()
    try:
        yield
    finally:
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass


def prepare(*, authority_path, approved_pin, approved_measurements, measurement_inputs):
    """Retain the exact approved observation in trusted host memory only."""
    if os.geteuid() != 0:
        raise PermissionError('root required')
    expected = json.loads(auth.canonical(approved_measurements))
    container_id = expected['container_id']
    if measurement_inputs['container_id'] != container_id:
        raise ValueError('container identity mismatch')
    key, public, _ = authority.load(authority_path, approved_pin=approved_pin)
    report = permit.issue(signing_key=key, authority_pin=approved_pin,
        approved_measurements=expected, measurement_inputs=measurement_inputs)
    if report['status'] != 'PASS':
        raise ValueError('permit refused')
    args = ['container', 'inspect', '--format', binding.FORMAT, container_id]
    created = binding.canonical_observation(prod_review.decode(acquisition.command(args).encode('utf-8')))
    if (created['Id'] != container_id or created['State'] != 'created'
            or continuity.digest(created) != expected['runtime_sha256']):
        raise ValueError('approved observation changed')
    if binding.canonical_observation(prod_review.decode(acquisition.command(args).encode('utf-8'))) != created:
        raise ValueError('unstable observation')
    return expected, created, report['envelope'], public


def exchange_prepared(*, authority_path, approved_pin, approved_measurements,
                      measurement_inputs, start_created, stop_failed):
    """Trusted integration caller only; no default Docker mutation command.

    On any failure after start is attempted, request cleanup of the same
    pinned container. Cleanup errors propagate rather than report success.
    """
    expected, created, envelope, public = prepare(authority_path=authority_path,
        approved_pin=approved_pin, approved_measurements=approved_measurements,
        measurement_inputs=measurement_inputs)
    container_id = expected['container_id']
    attempted = False
    completed = False
    try:
        with channel.host_listener() as listener:
            with published(envelope=envelope, public=public, approved_pin=approved_pin,
                           approved_measurements=expected):
                attempted = True
                start_created(container_id)
                sock, _ = listener.accept()
                with sock:
                    report = handoff.exchange(sock, authority_path=authority_path,
                        approved_pin=approved_pin, approved_measurements=expected,
                        envelope=envelope, created_observation=created)
                if report['status'] != 'PASS' or report['nonce_consumed'] is not True:
                    raise ValueError('host handoff refused')
        completed = True
        return dict(status='PASS', nonce_consumed=True,
                    startup_authorized=False, production_authorized=False)
    finally:
        if attempted and not completed:
            stop_failed(container_id)


def launch_approved(*, authority_path, approved_pin, approved_measurements,
                    measurement_inputs):
    """Use only pinned Docker actions; PASS denotes handoff, not HTTP readiness."""
    import prod_private_docker_actions as docker
    expected = json.loads(auth.canonical(approved_measurements))
    start, stop = docker.actions(container_id=expected['container_id'],
        image_id=expected['image_id'], approved_digest=expected['runtime_sha256'])
    return exchange_prepared(authority_path=authority_path, approved_pin=approved_pin,
        approved_measurements=expected, measurement_inputs=measurement_inputs,
        start_created=start, stop_failed=stop)
