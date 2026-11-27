"""Collect executable measurements; no issuance or Docker mutation."""
import re
import prod_private_executable_host as host
import prod_private_executable_measurement as runtime
import prod_private_host_volume_identity as identity

DOMAIN='DSIG-EXECUTABLE-SUPERVISOR-V1'

def inspect(*, compose_bytes, evidence_bytes, rec, candidate, expected_commit,
            expected_image, expected_image_id, container_id):
    result=dict(status='FAIL',domain=DOMAIN,nonce_consumed=False,
                startup_authorized=False,production_authorized=False)
    try:
        def snapshot():
            a=host.measure(compose_bytes=compose_bytes,evidence_bytes=evidence_bytes,
                rec=rec,candidate=candidate,expected_commit=expected_commit,
                expected_image=expected_image,expected_image_id=expected_image_id)
            if a['status']!='PASS' or a['local_daemon_used'] is not True:
                raise ValueError('host measurement rejected')
            b=runtime.measure(container_id=container_id,image_id=expected_image_id,
                expected_image=expected_image,compose_bytes=compose_bytes)
            if b['status']!='PASS' or b['local_daemon_used'] is not True:
                raise ValueError('runtime measurement rejected')
            c=identity.measure(container_id=container_id,image_id=expected_image_id)
            if c['status']!='PASS' or c['local_daemon_used'] is not True:
                raise ValueError('volume measurement rejected')
            if (a['commit'],a['image_id'],b['image_id'],b['container_id'])!=(
                    expected_commit,expected_image_id,expected_image_id,container_id):
                raise ValueError('identity mismatch')
            values=dict(commit=a['commit'],image_digest=a['image_digest'],
                image_id=a['image_id'],container_id=b['container_id'],
                config_sha256=a['config_sha256'],evidence_sha256=a['evidence_sha256'],
                runtime_sha256=b['runtime_sha256'],
                host_identity_sha256=c['host_identity_sha256'],
                volume_identity_sha256=c['volume_identity_sha256'])
            for k,v in values.items():
                pattern=('[0-9a-f]{40}' if k=='commit' else
                    'sha256:[0-9a-f]{64}' if k in ('image_id','image_digest') else '[0-9a-f]{64}')
                if not re.fullmatch(pattern,v):
                    raise ValueError('invalid measurement')
            return values
        first=snapshot()
        if snapshot()!=first:
            return result
        result.update(status='PASS',runtime_measurements=first)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):
        pass
    return result
