"""Canonical measurement of the locked review container, not a launch authority."""
import hashlib
import re
import prod_authorization as auth
import prod_backup_acquisition as acquisition
import prod_private_container_binding as binding
import prod_review

DOMAIN='DSIG-DOCKER-REVIEW-OBSERVATION-V1'

def measure(*, container_id, image_id, expected_image, compose_bytes):
    """Capture actual local daemon output, validate those exact observations,
    and expose only a digest. The review entrypoint remains locked.
    """
    result=dict(status='FAIL',local_daemon_used=False,startup_authorized=False,
                production_authorized=False)
    try:
        if not re.fullmatch('[0-9a-f]{64}',container_id) or not re.fullmatch('sha256:[0-9a-f]{64}',image_id):
            return result
        args=['container','inspect','--format',binding.FORMAT,container_id]
        def snapshot():
            return prod_review.decode(acquisition.command(args).encode('utf-8'))
        first=snapshot()
        # Validate the captured observation, rather than a separate unbound one.
        def captured(request):
            if request!=args:
                raise ValueError('unexpected inspection')
            return auth.canonical(first).decode('ascii')
        validation=binding.inspect(container_id=container_id,image_id=image_id,
            expected_image=expected_image,compose_bytes=compose_bytes,run=captured)
        if validation['status']!='PASS':
            return result
        second=snapshot()
        if auth.canonical(first)!=auth.canonical(second):
            return result
        result.update(status='PASS',local_daemon_used=True,container_id=container_id,
            image_id=image_id,runtime_sha256=hashlib.sha256(auth.canonical(
                {'domain':DOMAIN,'observation':first})).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        pass
    return result
