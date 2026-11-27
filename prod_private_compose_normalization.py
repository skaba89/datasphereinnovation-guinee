"""Reconcile a lossy Compose rendering with an independently reviewed source.

Never use the reconciled object as the input to Compose creation. The original
source must be used unchanged; actual Docker mount settings must be inspected.
"""
import copy
import prod_private_launch_topology as topology


def reconcile(reviewed, rendered, expected_image):
    """Only tolerate omission of the explicit false channel bind option."""
    if topology.validate(reviewed, expected_image)['status'] != 'PASS':
        raise ValueError('source topology rejected')
    candidate = copy.deepcopy(rendered)
    try:
        mounts = candidate['services']['app']['volumes']
        channel = [m for m in mounts if m['target'] == topology.CHANNEL]
        if len(channel) != 1:
            raise ValueError('channel missing or duplicated')
        mount = channel[0]
        if 'bind' not in mount:
            mount['bind'] = {}
        if not isinstance(mount['bind'], dict):
            raise ValueError('invalid bind')
        if 'create_host_path' not in mount['bind']:
            mount['bind']['create_host_path'] = False
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('invalid rendering') from exc
    if candidate != reviewed or topology.validate(candidate, expected_image)['status'] != 'PASS':
        raise ValueError('unexpected Compose drift')
    return candidate


def inspect_channel(host_config):
    """Require explicit bind API mount; absent CreateMountpoint means false.

    Docker Engine's optional bool defaults to false. Allow only the exact
    named PROD data volume in legacy Binds; reject duplicate channel mounts
    and all additional channel bind options.
    """
    try:
        if host_config.get('Binds') not in (None, [], ['dsig-prod_prod-data:/app/data:rw']):
            return False
        mounts = host_config['Mounts']
        channel = [m for m in mounts if m['Target'] == topology.CHANNEL]
        if len(channel) != 1:
            return False
        m = channel[0]
        if not set(m) <= {'Type','Source','Target','ReadOnly','BindOptions'}:
            return False
        if (m['Type'] != 'bind' or m['Source'] != topology.HOST_CHANNEL
                or m['ReadOnly'] is not True):
            return False
        options = m.get('BindOptions', {})
        return (isinstance(options, dict)
                and set(options) <= {'CreateMountpoint','Propagation'}
                and options.get('CreateMountpoint', False) is False
                and options.get('Propagation', 'rprivate') in ('', 'rprivate'))
    except (KeyError, TypeError, AttributeError):
        return False
