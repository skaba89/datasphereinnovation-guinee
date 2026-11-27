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
        {'domain': measurement.DOMAIN, 'observation': binding.canonical_observation(observation)})).hexdigest()


def compare(created, running, *, approved_digest, network_id=None, dns_names=None):
    """Compare immutable settings exactly, including all environment fields."""
    try:
        if not re.fullmatch('[0-9a-f]{64}', approved_digest):
            return False
        if not hmac.compare_digest(digest(created), approved_digest):
            return False
        created = binding.canonical_observation(created)
        running = binding.canonical_observation(running)
        if created['State'] != 'created' or running['State'] != 'running':
            return False
        if set(created) != set(running):
            return False
        if any(created[k] != running[k] for k in created if k not in ('State', 'Networks', 'HostConfig')):
            return False
        old_host, new_host = dict(created['HostConfig']), dict(running['HostConfig'])
        if old_host.get('OomKillDisable') is False and new_host.get('OomKillDisable') is None:
            if 'OomKillDisable' in old_host and 'OomKillDisable' in new_host:
                new_host['OomKillDisable'] = False
        if old_host != new_host:
            return False
        if set(created['Networks']) != {NETWORK} or set(running['Networks']) != {NETWORK}:
            return False
        before, after = created['Networks'][NETWORK], running['Networks'][NETWORK]
        if set(before) != set(after):
            return False
        dynamic = set(DYNAMIC)
        if before['NetworkID'] == '':
            if network_id is None or after['NetworkID'] != network_id:
                return False
            dynamic.add('NetworkID')
        elif network_id is not None and after['NetworkID'] != network_id:
            return False
        if before.get('DNSNames') is None and after.get('DNSNames') is not None:
            names = after['DNSNames']
            if (not isinstance(names, list) or not names or dns_names is None
                    or not all(isinstance(n, str) for n in names)
                    or len(names) != len(set(names)) or set(names) != set(dns_names)):
                return False
            dynamic.add('DNSNames')
        if any(before[k] != after[k] for k in before if k not in dynamic):
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
            return binding.canonical_observation(prod_review.decode(acquisition.command(args).encode('utf-8')))
        first = snapshot()
        network = prod_review.decode(acquisition.command(
            ['network','inspect','--format','{"Id":{{json .Id}},"Name":{{json .Name}},"Internal":{{json .Internal}}}',NETWORK]).encode('utf-8'))
        if network['Name'] != NETWORK or network['Internal'] is not True:
            return result
        name = acquisition.command(['container','inspect','--format','{{.Name}}',container_id]).strip()
        if not name.startswith('/') or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*',name[1:]):
            return result
        aliases = created['Networks'][NETWORK].get('Aliases') or []
        names = set(aliases) | {name[1:], container_id[:12]}
        if not compare(created, first, approved_digest=approved_digest,
                       network_id=network['Id'], dns_names=names):
            return result
        if snapshot() != first:
            return result
        if prod_review.decode(acquisition.command(
            ['network','inspect','--format','{"Id":{{json .Id}},"Name":{{json .Name}},"Internal":{{json .Internal}}}',NETWORK]).encode('utf-8')) != network:
            return result
        result['status'] = 'PASS'
    except (ValueError, TypeError, KeyError, OSError, AttributeError, RecursionError):
        pass
    return result
