"""Read-only validation of a projected Docker source inspection.

Never runs Docker, reads database contents, or grants production access.
Caller must obtain observations directly from a trusted local daemon.
"""
import re

VOLUME='dsig-prod_prod-data'
DEST='/app/data'
DB=DEST+'/requests.sqlite3'


def inspect(container, volume, *, expected_container_id, expected_image_id):
    return _inspect(container, volume, expected_container_id=expected_container_id,
                    expected_image_id=expected_image_id, project='dsig-prod', name=VOLUME)


def inspect_qualification(container, volume, *, expected_container_id, expected_image_id, run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{16}',run_id):
        raise ValueError('invalid qualification run id')
    project='dsig-qualification-'+run_id
    result=_inspect(container,volume,expected_container_id=expected_container_id,
                    expected_image_id=expected_image_id,project=project,name=project+'_prod-data')
    return dict(result,qualification_only=True)


def _inspect(container, volume, *, expected_container_id, expected_image_id, project, name):
    checks=dict.fromkeys(('identity','image','project','mount','volume','runtime'),'NOT_RUN')
    try:
        checks['identity']='FAIL'
        if not re.fullmatch(r'[0-9a-f]{64}',expected_container_id) or container['Id']!=expected_container_id:
            raise ValueError()
        checks['identity']='PASS'
        checks['image']='FAIL'
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',expected_image_id) or container['Image']!=expected_image_id:
            raise ValueError()
        checks['image']='PASS'
        checks['project']='FAIL'
        labels=container['Config']['Labels']
        if (labels['com.docker.compose.project']!=project
                or labels['com.docker.compose.service']!='app'
                or container['Config']['User']!='10001:10001'):
            raise ValueError()
        checks['project']='PASS'
        checks['mount']='FAIL'
        mounts=container['Mounts']
        data=[m for m in mounts if m['Destination']==DEST]
        if len(data)!=1 or data[0]['Type']!='volume' or data[0]['Name']!=name or data[0]['RW'] is not True:
            raise ValueError()
        if any(m['Destination']!=DEST and (m['Destination']=='/' or DEST.startswith(m['Destination'].rstrip('/')+'/')
                    or m['Destination'].startswith(DEST+'/')) for m in mounts):
            raise ValueError()
        checks['mount']='PASS'
        checks['volume']='FAIL'
        vl=volume['Labels']
        if (volume['Name']!=name or volume['Driver']!='local' or volume['Scope']!='local'
                or volume.get('Options') not in (None,{})
                or vl['com.docker.compose.project']!=project
                or vl['com.docker.compose.volume']!='prod-data'
                or data[0]['Source']!=volume['Mountpoint']
                or volume['Mountpoint']!=f'/var/lib/docker/volumes/{name}/_data'):
            raise ValueError()
        checks['volume']='PASS'
        checks['runtime']='FAIL'
        if container['State']['Running'] is not True or container['HostConfig']['Privileged'] is not False:
            raise ValueError()
        if container['HostConfig']['ReadonlyRootfs'] is not True:
            raise ValueError()
        checks['runtime']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError):
        pass
    return {'status':'PASS' if all(x=='PASS' for x in checks.values()) else 'FAIL',
            'checks':checks,'source_path':DB,'observation_authenticated':False,
            'database_verified':False,'production_authorized':False}
