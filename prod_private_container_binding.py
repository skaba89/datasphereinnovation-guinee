"""Read-only verification of a CREATED, stopped review container.
Never starts a container, consumes a permit or grants runtime authorization.
"""
import hmac
import re
import prod_backup_acquisition as acquisition
import prod_review
import prod_compose

FORMAT='{"Id":{{json .Id}},"Image":{{json .Image}},"State":{{json .State.Status}},"Config":{{json .Config}},"HostConfig":{{json .HostConfig}},"Mounts":{{json .Mounts}},"Networks":{{json .NetworkSettings.Networks}}}'

def inspect(*, container_id, image_id, compose_bytes, expected_image, run=None):
    """Compare selected actual container settings against a locked review topology.
    Full Docker output stays in memory; never return environment or error details.
    Expected identities and reviewed bytes must be independently trusted.
    """
    checks=dict.fromkeys(('topology','identity','state','environment','isolation','stable'),'NOT_RUN')
    result=dict(status='FAIL',checks=checks,local_daemon_used=run is None,
                startup_authorized=False,production_authorized=False)
    runner=acquisition.command if run is None else run
    try:
        checks['topology']='FAIL'
        if not re.fullmatch('[0-9a-f]{64}',container_id) or not re.fullmatch('sha256:[0-9a-f]{64}',image_id):
            return result
        compose=prod_review.decode(compose_bytes)
        if prod_compose.validate(compose,expected_image,8320)['status']!='PASS':
            return result
        checks['topology']='PASS'
        s=compose['services']['app']
        def snapshot():
            return prod_review.decode(runner(['container','inspect','--format',FORMAT,container_id]).encode('utf-8'))
        c=snapshot()
        checks['identity']='FAIL'
        cfg=c['Config']; hc=c['HostConfig']
        labels=cfg['Labels']
        if (c['Id']!=container_id or c['Image']!=image_id or cfg['Image']!=expected_image
                or labels['com.docker.compose.project']!='dsig-prod'
                or labels['com.docker.compose.service']!='app'):
            return result
        checks['identity']='PASS'
        checks['state']='FAIL'
        if c['State']!='created' or cfg['Entrypoint']!=prod_compose.STOP or cfg.get('Cmd') not in (None,[]):
            return result
        checks['state']='PASS'
        checks['environment']='FAIL'
        actual={}
        for item in cfg['Env']:
            key, sep, value=item.partition('=')
            if not sep or key in actual:
                return result
            actual[key]=value
        expected=s['environment']
        if set(k for k in actual if k.startswith('DSIG_')) != set(expected)|{'DSIG_CONTAINER'}:
            return result
        if actual.get('DSIG_CONTAINER')!='1':
            return result
        if any(not hmac.compare_digest(actual[k].encode(),v.encode()) for k,v in expected.items()):
            return result
        checks['environment']='PASS'
        checks['isolation']='FAIL'
        if (cfg['User']!='10001:10001' or hc['Privileged'] is not False
                or hc['ReadonlyRootfs'] is not True or hc['CapDrop']!=['ALL']
                or hc.get('CapAdd') not in (None,[])
                or hc['SecurityOpt'] not in (['no-new-privileges:true'],['no-new-privileges=true'])
                or hc['PortBindings']!={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8320'}]}
                or hc['RestartPolicy']['Name']!='no'
                or hc['Memory']!=536870912 or hc['MemorySwap']!=536870912
                or hc['NanoCpus']!=2000000000 or hc['PidsLimit']!=128
                or hc['NetworkMode']!='dsig-prod_prod-private'
                or set(c['Networks'])!={'dsig-prod_prod-private'}):
            return result
        mounts={m['Destination']:m for m in c['Mounts']}
        if len(c['Mounts'])!=2 or set(mounts)!={'/app/data','/run/dsig-clamav'}:
            return result
        d=mounts['/app/data']; a=mounts['/run/dsig-clamav']
        if (d['Type']!='volume' or d['Name']!='dsig-prod_prod-data' or d['RW'] is not True
                or a['Type']!='bind' or a['Source']!='/run/clamav' or a['RW'] is not False):
            return result
        checks['isolation']='PASS'
        checks['stable']='FAIL'
        if snapshot()!=c:
            return result
        checks['stable']='PASS'
        result['status']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OSError,RecursionError):
        pass
    return result
