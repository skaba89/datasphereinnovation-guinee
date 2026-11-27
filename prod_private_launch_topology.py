"""Validate proposed executable topology separately from locked review.
No Docker mutation, no startup authority; the referenced runtime is not yet deployed.
"""
import copy
import prod_compose

ENTRYPOINT=['python','/app/prod_private_runtime_entrypoint.py']
CHANNEL='/run/dsig-private-launch'
HOST_CHANNEL='/run/dsig-prod-launch'

def validate(config,expected_image,expected_port=8320):
    result=dict(status='FAIL',startup_authorized=False,production_authorized=False)
    try:
        c=copy.deepcopy(config)
        s=c['services']['app']
        if expected_port!=8320 or s['entrypoint']!=ENTRYPOINT or s['profiles']!=['prod-private-launch']:
            return result
        mounts=s['volumes']
        channel=[m for m in mounts if m['target']==CHANNEL]
        if channel!=[{'type':'bind','source':HOST_CHANNEL,'target':CHANNEL,
                      'read_only':True,'bind':{'create_host_path':False}}]:
            return result
        s['volumes']=[m for m in mounts if m['target']!=CHANNEL]
        s['entrypoint']=prod_compose.STOP
        s['profiles']=['prod-review']
        if prod_compose.validate(c,expected_image,expected_port)['status']!='PASS':
            return result
        result['status']='PASS'
    except (KeyError,TypeError,ValueError,AttributeError):
        pass
    return result
