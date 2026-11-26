"""Read-only acquisition from the local Docker socket; never starts containers."""
import json
import os
import re
import subprocess
import prod_backup_source as source

# Go templates project fields at the daemon/CLI boundary, not Config.Env.
CONTAINER_FORMAT='{"Id":{{json .Id}},"Image":{{json .Image}},"Config":{"User":{{json .Config.User}},"Labels":{"com.docker.compose.project":{{json (index .Config.Labels "com.docker.compose.project")}},"com.docker.compose.service":{{json (index .Config.Labels "com.docker.compose.service")}}}},"Mounts":{{json .Mounts}},"State":{"Running":{{json .State.Running}},"StartedAt":{{json .State.StartedAt}}},"HostConfig":{"Privileged":{{json .HostConfig.Privileged}},"ReadonlyRootfs":{{json .HostConfig.ReadonlyRootfs}}}}'
VOLUME_FORMAT='{"Name":{{json .Name}},"Driver":{{json .Driver}},"Scope":{{json .Scope}},"Options":{{json .Options}},"Mountpoint":{{json .Mountpoint}},"Labels":{"com.docker.compose.project":{{json (index .Labels "com.docker.compose.project")}},"com.docker.compose.volume":{{json (index .Labels "com.docker.compose.volume")}}}}'
MAX_OUTPUT=1024*1024


def command(args):
    env={'PATH':'/usr/bin:/bin','HOME':os.path.expanduser('~'),'DOCKER_CONFIG':'/dev/null'}
    try:
        out=subprocess.run(['/usr/bin/docker','--host','unix:///var/run/docker.sock',*args],
                           env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                           timeout=30,check=True).stdout
    except (OSError,subprocess.SubprocessError):
        raise ValueError('local Docker inspection failed') from None
    if len(out)>MAX_OUTPUT:
        raise ValueError('Docker projection too large')
    return out.decode('utf-8')


def acquire(*, expected_container_id, expected_image_id, run=None):
    return _acquire(expected_container_id=expected_container_id,expected_image_id=expected_image_id,
                    run=run,volume_name=source.VOLUME,validator=source.inspect)


def acquire_qualification(*, expected_container_id, expected_image_id, run_id, run=None):
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{16}',run_id):
        raise ValueError('invalid qualification run id')
    def validator(c,v,**kwargs):
        return source.inspect_qualification(c,v,run_id=run_id,**kwargs)
    result=_acquire(expected_container_id=expected_container_id,expected_image_id=expected_image_id,
                    run=run,volume_name='dsig-qualification-'+run_id+'_prod-data',validator=validator)
    return dict(result,qualification_only=True)


def _acquire(*, expected_container_id, expected_image_id, run, volume_name, validator):
    run=run or command
    checks=dict.fromkeys(('local_inspection','source','exclusive_consumer','stable_observation'),'NOT_RUN')
    try:
        checks['local_inspection']='FAIL'
        if not re.fullmatch(r'[0-9a-f]{64}',expected_container_id) or not re.fullmatch(r'sha256:[0-9a-f]{64}',expected_image_id):
            raise ValueError('invalid pinned identity')
        def snapshot():
            c=json.loads(run(['container','inspect','--format',CONTAINER_FORMAT,expected_container_id]))
            v=json.loads(run(['volume','inspect','--format',VOLUME_FORMAT,volume_name]))
            ids=run(['container','ls','--all','--no-trunc','--filter',f'volume={volume_name}','--format','{{.ID}}']).splitlines()
            return c,v,ids
        c,v,ids=snapshot()
        checks['local_inspection']='PASS'
        checks['source']='FAIL'
        if validator(c,v,expected_container_id=expected_container_id,expected_image_id=expected_image_id)['status']!='PASS':
            raise ValueError('source rejected')
        if not isinstance(c['State']['StartedAt'],str) or not c['State']['StartedAt']:
            raise ValueError('missing runtime generation')
        checks['source']='PASS'
        checks['exclusive_consumer']='FAIL'
        if ids!=[expected_container_id]:
            raise ValueError('unexpected volume consumer')
        checks['exclusive_consumer']='PASS'
        checks['stable_observation']='FAIL'
        if snapshot()!=(c,v,ids):
            raise ValueError('source changed during inspection')
        checks['stable_observation']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OSError,UnicodeError,RecursionError):
        pass
    return {'status':'PASS' if all(x=='PASS' for x in checks.values()) else 'FAIL',
            'checks':checks,'local_daemon_used':run is command,
            'database_verified':False,'production_authorized':False}
