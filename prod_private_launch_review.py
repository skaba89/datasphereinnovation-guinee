"""Host launch review, deliberately non-executing while runtime topology is locked."""
import json
import prod_authorization as auth
import prod_private_release as release
import prod_private_host_measurement as measurement
import prod_private_container_binding as binding

def review(*, envelope, public, authority_pin, compose_bytes, evidence_bytes,
           rec, candidate, expected_commit, expected_image, expected_image_id,
           container_id):
    checks=dict.fromkeys(('measurement','signature','container','signature_recheck'),'NOT_RUN')
    result=dict(status='FAIL',checks=checks,nonce_consumed=False,
                startup_authorized=False,production_authorized=False)
    try:
        envelope=json.loads(auth.canonical(envelope))
        checks['measurement']='FAIL'
        observed=measurement.measure(compose_bytes=compose_bytes,evidence_bytes=evidence_bytes,
            rec=rec,candidate=candidate,expected_commit=expected_commit,
            expected_image=expected_image,expected_image_id=expected_image_id)
        if observed['status']!='PASS' or observed['local_daemon_used'] is not True:
            return result
        checks['measurement']='PASS'
        expected={k:observed[k] for k in ('commit','image_digest','config_sha256','evidence_sha256')}
        checks['signature']='FAIL'
        if release.verify(envelope,public,authority_pin=authority_pin,**expected)['status']!='PASS':
            return result
        checks['signature']='PASS'
        checks['container']='FAIL'
        actual=binding.inspect(container_id=container_id,image_id=expected_image_id,
                              compose_bytes=compose_bytes,expected_image=expected_image)
        if actual['status']!='PASS' or actual['local_daemon_used'] is not True:
            return result
        checks['container']='PASS'
        checks['signature_recheck']='FAIL'
        if release.verify(envelope,public,authority_pin=authority_pin,**expected)['status']!='PASS':
            return result
        checks['signature_recheck']='PASS'
        result['status']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        pass
    return result
