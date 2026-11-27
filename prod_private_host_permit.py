"""Host-side private permit reservation; does not authorize runtime or start Docker."""
import json
import prod_authorization
import prod_private_host_measurement as measurement
import prod_private_release as release
import prod_private_replay as replay

def reserve(*, envelope, public, authority_pin, ledger_path, compose_bytes,
            evidence_bytes, rec, candidate, expected_commit, expected_image,
            expected_image_id):
    """Call from trusted operator code with independently provisioned inputs.

    No caller-controlled runner or clock. A successful reservation burns the
    nonce even if subsequent startup fails. No runtime capability is issued.
    """
    checks=dict.fromkeys(('measurement','signature','reservation'),'NOT_RUN')
    result=dict(status='FAIL',checks=checks,startup_authorized=False,
                production_authorized=False,nonce_consumed=False)
    try:
        envelope=json.loads(prod_authorization.canonical(envelope))
        checks['measurement']='FAIL'
        observed=measurement.measure(compose_bytes=compose_bytes,
            evidence_bytes=evidence_bytes,rec=rec,candidate=candidate,
            expected_commit=expected_commit,expected_image=expected_image,
            expected_image_id=expected_image_id)
        if observed['status']!='PASS' or observed['local_daemon_used'] is not True:
            return result
        checks['measurement']='PASS'
        expected={k:observed[k] for k in
                  ('commit','image_digest','config_sha256','evidence_sha256')}
        checks['signature']='FAIL'
        if release.verify(envelope,public,authority_pin=authority_pin,**expected)['status']!='PASS':
            return result
        checks['signature']='PASS'
        checks['reservation']='FAIL'
        consumed=replay.consume(ledger_path,envelope,public,authority_pin=authority_pin,**expected)
        if consumed['status']!='PASS':
            return result
        checks['reservation']='PASS'
        result.update(status='PASS',nonce_consumed=True)
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        pass
    return result
