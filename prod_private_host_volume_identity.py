"""Read-only identity measurement on a trusted Linux Docker host."""
import hashlib
import os
import re
import stat
from pathlib import Path
import prod_authorization as auth
import prod_backup_acquisition as acquisition
import prod_backup_source as source
import prod_review

MACHINE_ID=Path('/etc/machine-id')
VOLUME=source.VOLUME
MOUNT=Path('/var/lib/docker/volumes')/VOLUME/'_data'

def digest(domain, value):
    return hashlib.sha256(auth.canonical({'domain':domain,'value':value})).hexdigest()

def host_identity():
    fd=os.open(MACHINE_ID,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('unsafe machine identity')
        value=stream.read(128).decode('ascii').strip()
    if not re.fullmatch('[0-9a-f]{32}',value) or value=='0'*32:
        raise ValueError('invalid machine identity')
    return digest('DSIG-HOST-IDENTITY-V1',value)

def measure(*, container_id, image_id):
    result=dict(status='FAIL',local_daemon_used=False,startup_authorized=False,
                production_authorized=False)
    try:
        if not re.fullmatch('[0-9a-f]{64}',container_id) or not re.fullmatch('sha256:[0-9a-f]{64}',image_id):
            return result
        def snapshot():
            host=host_identity()
            c=prod_review.decode(acquisition.command(['container','inspect','--format',
                acquisition.CONTAINER_FORMAT,container_id]).encode())
            v=prod_review.decode(acquisition.command(['volume','inspect','--format',
                acquisition.VOLUME_FORMAT,VOLUME]).encode())
            ids=acquisition.command(['container','ls','--all','--no-trunc','--filter',
                'volume='+VOLUME,'--format','{{.ID}}']).splitlines()
            info=MOUNT.lstat()
            if not stat.S_ISDIR(info.st_mode) or MOUNT.resolve()!=MOUNT:
                raise ValueError('unsafe volume mountpoint')
            # Reuse source checks for identity and mounts; this review requires
            # a stopped container rather than the running backup source.
            if c['State']['Running'] is not False or ids!=[container_id]:
                raise ValueError('unexpected volume consumer')
            review=dict(c,State=dict(c['State'],Running=True))
            if source.inspect(review,v,expected_container_id=container_id,
                              expected_image_id=image_id)['status']!='PASS':
                raise ValueError('volume rejected')
            return host,c,v,ids,(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
        first=snapshot()
        if snapshot()!=first:
            return result
        host,_,volume,_,filesystem=first
        result.update(status='PASS',local_daemon_used=True,host_identity_sha256=host,
            volume_identity_sha256=digest('DSIG-VOLUME-IDENTITY-V1',
                {'host':host,'volume':volume,'filesystem':filesystem}))
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):
        pass
    return result
