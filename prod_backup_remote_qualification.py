"""Remote qualification of a locally completed signed cycle; no scheduler."""
import hashlib
import hmac
import re
from pathlib import Path
import prod_backup_cycle_journal as journal
import prod_backup_orchestrator as guard
import prod_backup_rehearsal as rehearsal
import prod_b2_export as export


def verify_remote(*, root, now, public, pin, key, run_id, bucket_id, remote):
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{32}',run_id):
        raise ValueError('invalid qualification id')
    if not isinstance(bucket_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',bucket_id):
        raise ValueError('invalid bucket id')
    root=Path(root)
    for p in (root,root/'state',root/'locks',root/'archives',root/'replica'):
        guard.private_dir(p)
    with guard.locked(root/'locks'):
        proof=journal.read(root/'state',now=now,public=public,pin=pin)
        if proof['status']!='COMPLETE':
            raise ValueError('local cycle not complete')
        name=f"dsig-prod-{proof['cycle'].replace('-','')}T011500Z.dsigbak"
        digest=proof['archive_sha256']
        data=rehearsal.read_archive(root/'archives'/name)
        replica=rehearsal.read_archive(root/'replica'/name)
        def check(blob):
            if not isinstance(blob,bytes) or not 0<len(blob)<=128*1024*1024 or not hmac.compare_digest(hashlib.sha256(blob).hexdigest(),digest):
                raise ValueError('qualification digest mismatch')
            export.verify_archive(blob,key)
        check(data)
        check(replica)
        policy=remote.bucket_info(export.BUCKET)
        if (policy.get('bucketName')!=export.BUCKET or policy.get('bucketId')!=bucket_id
                or policy.get('bucketType')!='allPrivate' or policy.get('encryption')!='SSE-B2'
                or policy.get('lock_mode')!='compliance' or type(policy.get('lock_days')) is not int or policy['lock_days']<30):
            raise ValueError('invalid remote policy')
        obj=f'prod/qualification/v232/{run_id}/{name}'
        downloaded=remote.read(export.BUCKET,obj)
        uploaded=False
        if downloaded is None:
            remote.create_only(export.BUCKET,obj,data)
            uploaded=True
            downloaded=remote.read(export.BUCKET,obj)
        check(downloaded)
        return dict(status='PASS',qualification_only=True,production_authorized=False,
                    business_provenance_verified=False,remote_verified=True,
                    remote_restore_verified=True,uploaded=uploaded,object=obj,
                    bucket_id=bucket_id,sha256=digest,journal_head=proof['head'])
