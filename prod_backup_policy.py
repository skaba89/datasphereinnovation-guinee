"""Read-only review of a dedicated PROD backup policy; no B2 calls or data writes."""
import re
from pathlib import PurePosixPath

BUCKET = 'dsig-prod-backups'
FIELDS = {'bucket','bucket_id','prefix','local_dir','state_dir','credential_id',
          'bucket_type','encryption','lock_mode','lock_days','local_days',
          'remote_days','rpo_hours','rto_hours'}


def inspect(policy, rec, candidate):
    checks=dict.fromkeys(('format','namespace','credentials','retention','recovery_targets'),False)
    try:
        if not isinstance(policy,dict) or set(policy)!=FIELDS:
            raise ValueError()
        if not all(isinstance(x,dict) for x in (rec,candidate)):
            raise ValueError()
        checks['format']=True
        def identifier(v):
            return isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{8,128}',v))
        def private_path(v):
            return isinstance(v,str) and v.startswith('/') and str(PurePosixPath(v))==v and '..' not in PurePosixPath(v).parts
        paths=[policy['local_dir'],policy['state_dir']]
        references=[x[k] for x in (rec,candidate) for k in ('local_dir','state_dir')]
        def overlaps(a,b):
            a,b=PurePosixPath(a),PurePosixPath(b)
            return a==b or a in b.parents or b in a.parents
        checks['namespace']=(policy['bucket']==BUCKET and policy['prefix']=='prod/'
            and identifier(policy['bucket_id'])
            and all(identifier(x['bucket_id']) and x['bucket_id']!=policy['bucket_id'] for x in (rec,candidate))
            and all(private_path(p) for p in paths+references)
            and paths==['/home/ubuntu/dsig-prod-backups','/home/ubuntu/dsig-prod-backup-state']
            and not overlaps(*paths)
            and not any(overlaps(p,q) for p in paths for q in references))
        checks['credentials']=(identifier(policy['credential_id']) and
            all(identifier(x['credential_id']) and x['credential_id']!=policy['credential_id'] for x in (rec,candidate)))
        ints=('lock_days','local_days','remote_days','rpo_hours','rto_hours')
        if not all(type(policy[k]) is int for k in ints):
            raise ValueError()
        checks['retention']=(policy['bucket_type']=='allPrivate' and policy['encryption']=='SSE-B2'
            and policy['lock_mode']=='compliance' and 30<=policy['lock_days']<=policy['remote_days']<=365
            and 7<=policy['local_days']<=policy['remote_days'])
        checks['recovery_targets']=(1<=policy['rpo_hours']<=24 and 1<=policy['rto_hours']<=4)
    except (ValueError,TypeError,KeyError,AttributeError):
        pass
    return {'status':'PASS' if all(checks.values()) else 'FAIL',
            'checks':{k:'PASS' if v else 'FAIL' for k,v in checks.items()},
            'remote_verified':False,'production_authorized':False}
