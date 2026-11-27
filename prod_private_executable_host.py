"""Host-side measurement of a proposed executable production topology.
No nonce consumption, container creation, startup or production authorization.
"""
import hashlib
import json
import re
import prod_backup_acquisition
import prod_private_launch_topology as topology
import prod_config
import prod_review

IMAGE_FORMAT = '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},"User":{{json .Config.User}},"Revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}'

def measure(*, compose_bytes, evidence_bytes, rec, candidate, expected_commit,
            expected_image, expected_image_id, run=None):
    """Expected identities must originate in an independently trusted release.
    Hash exact reviewed bytes; never emit configuration, keys or command output.
    This measures a local image, not an actual container or its runtime state.
    """
    runner = prod_backup_acquisition.command if run is None else run
    checks = dict.fromkeys(('inputs','topology','configuration','evidence','image','stable'), 'NOT_RUN')
    result = dict(status='FAIL', checks=checks, local_daemon_used=run is None,
                  startup_authorized=False, production_authorized=False)
    try:
        checks['inputs']='FAIL'
        if not re.fullmatch(r'[0-9a-f]{40}', expected_commit):
            raise ValueError()
        if not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', expected_image):
            raise ValueError()
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', expected_image_id):
            raise ValueError()
        compose=prod_review.decode(compose_bytes)
        evidence=prod_review.decode(evidence_bytes)
        checks['inputs']='PASS'
        checks['topology']=topology.validate(compose,expected_image,8320)['status']
        if checks['topology']!='PASS':
            return result
        checks['configuration']=prod_config.inspect(compose['services']['app']['environment'],rec,candidate)['status']
        if checks['configuration']!='PASS':
            return result
        checks['evidence']='PASS' if prod_review.complete(evidence,expected_commit) else 'FAIL'
        if checks['evidence']!='PASS':
            return result
        def snapshot():
            return prod_review.decode(runner(['image','inspect','--format',IMAGE_FORMAT,expected_image]).encode('utf-8'))
        checks['image']='FAIL'
        image=snapshot()
        if (set(image)!={'Id','RepoDigests','User','Revision'}
                or image['Id']!=expected_image_id
                or not isinstance(image['RepoDigests'],list)
                or expected_image not in image['RepoDigests']
                or image['User']!='10001:10001'
                or image['Revision']!=expected_commit):
            return result
        checks['image']='PASS'
        checks['stable']='FAIL'
        if snapshot()!=image:
            return result
        checks['stable']='PASS'
        result.update(status='PASS',commit=expected_commit,image_id=expected_image_id,
                      image_digest=expected_image.rsplit('@',1)[1],
                      config_sha256=hashlib.sha256(compose_bytes).hexdigest(),
                      evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        pass
    return result
