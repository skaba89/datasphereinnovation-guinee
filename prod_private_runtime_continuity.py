"""Read-only continuity check for the exact approved CREATED observation.

Only explicitly enumerated Docker-assigned endpoint fields may change.
No launch authority is granted. The caller must retain the original observation
in trusted host memory, never obtain it from the recipient.
"""
import hashlib
import hmac
import ipaddress
import re
import os
import prod_authorization as auth
import prod_backup_acquisition as acquisition
import prod_private_executable_binding as binding
import prod_private_executable_measurement as measurement
import prod_review

NETWORK = 'dsig-prod_prod-private'
DYNAMIC = frozenset(('EndpointID', 'IPAddress', 'IPPrefixLen', 'Gateway',
                     'GlobalIPv6Address', 'GlobalIPv6PrefixLen', 'IPv6Gateway',
                     'MacAddress'))


def digest(observation):
    return hashlib.sha256(auth.canonical(
        {'domain': measurement.DOMAIN, 'observation': observation})).hexdigest()


def compare(created, running, *, approved_digest):
    """Compare immutable settings exactly, including all environment fields."""
    try:
        if not re.fullmatch('[0-9a-f]{64}', approved_digest):
            return False
        if not hmac.compare_digest(digest(created), approved_digest):
            return False
        if created['State'] != 'created' or running['State'] != 'running':
            return False
        if set(created) != set(running):
            return False
        if any(created[k] != running[k] for k in created if k not in ('State', 'Networks')):
            return False
        if set(created['Networks']) != {NETWORK} or set(running['Networks']) != {NETWORK}:
            return False
        before, after = created['Networks'][NETWORK], running['Networks'][NETWORK]
        if set(before) != set(after):
            return False
        if any(before[k] != after[k] for k in before if k not in DYNAMIC):
            return False
        if not re.fullmatch('[0-9a-f]{64}', after['NetworkID']):
            return False
        if not re.fullmatch('[0-9a-f]{64}', after['EndpointID']):
            return False
        if not re.fullmatch('[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}', after['MacAddress']):
            return False
        for address, prefix, version in (
            ('IPAddress', 'IPPrefixLen', 4),
            ('GlobalIPv6Address', 'GlobalIPv6PrefixLen', 6),
        ):
            if type(after[prefix]) is not int:
                return False
            if after[address]:
                value = ipaddress.ip_address(after[address])
                if value.version != version or not 0 < after[prefix] <= value.max_prefixlen:
                    return False
            elif after[prefix] != 0:
                return False
        if not after['IPAddress'] and not after['GlobalIPv6Address']:
            return False
        # An internal launch network must not acquire a default gateway.
        if after['Gateway'] or after['IPv6Gateway']:
            return False
        return True
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return False


def inspect(*, created, approved_digest, container_id):
    result = dict(status='FAIL', startup_authorized=False, production_authorized=False)
    try:
        if os.geteuid() != 0 or not re.fullmatch('[0-9a-f]{64}', container_id):
            return result
        if created['Id'] != container_id:
            return result
        args = ['container', 'inspect', '--format', binding.FORMAT, container_id]
        def snapshot():
            return prod_review.decode(acquisition.command(args).encode('utf-8'))
        first = snapshot()
        if not compare(created, first, approved_digest=approved_digest):
            return result
        if snapshot() != first:
            return result
        result['status'] = 'PASS'
    except (ValueError, TypeError, KeyError, OSError, AttributeError, RecursionError):
        pass
    return result
