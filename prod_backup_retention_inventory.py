"""Read-only B2 inventory collection; no delete, upload or policy mutation."""
from datetime import datetime,timezone,timedelta
import re
from prod_b2_cli import B2ReviewAdapter
from prod_b2_export import BUCKET
import prod_backup_retention_review as review

def millis(value):
    if isinstance(value,str) and re.fullmatch(r'[0-9]{1,15}',value):
        value=int(value)
    if type(value) is not int or value<0:
        raise ValueError('invalid B2 timestamp')
    return datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=value)

def normalize(row,bucket_id):
    if not isinstance(row,dict) or row.get('bucketId')!=bucket_id:
        raise ValueError('invalid version bucket')
    review.archive_stamp(row.get('fileName'))
    retention=row.get('fileRetention')
    hold=row.get('legalHold')
    if not isinstance(retention,dict):
        raise ValueError('retention unavailable')
    # Native API authorization wrapper or CLI SDK flattened metadata.
    if 'isClientAuthorizedToRead' in retention:
        if retention['isClientAuthorizedToRead'] is not True:
            raise ValueError('retention unreadable')
        retention=retention.get('value')
    if not isinstance(retention,dict) or retention.get('mode')!='compliance':
        raise ValueError('compliance retention unavailable')
    if isinstance(hold,dict):
        if hold.get('isClientAuthorizedToRead') is not True:
            hold='unknown'
        else:hold=hold.get('value')
    # Unknown/unreadable hold is conservatively treated as protected.
    protected=hold!='off'
    return dict(object=row['fileName'],version=row.get('fileId'),action=row.get('action'),
                uploaded_at=millis(row.get('uploadTimestamp')),
                retain_until=millis(retention.get('retainUntilTimestamp')),
                lock_mode='compliance',legal_hold=protected)

class RetentionInventory(B2ReviewAdapter):
    def create_only(self,*args,**kwargs):
        raise ValueError('retention inventory is read-only')

    def collect(self,*,now):
        now=review.utc(now)
        self.bucket_info(BUCKET)
        before=self._json(['bucket','get',BUCKET])
        policy=review.inspect_bucket(before,self.expected)
        if policy['status']!='PASS':
            raise ValueError('retention policy refused')
        def scan():
            self.bucket_info(BUCKET)
            rows=self._json(['ls','--recursive','--versions','--json',f'b2://{BUCKET}/prod/'])
            if not isinstance(rows,list) or len(rows)>10000:
                raise ValueError('invalid inventory')
            selected=[]
            excluded=0
            for row in rows:
                if not isinstance(row,dict) or not isinstance(row.get('fileName'),str):
                    raise ValueError('invalid inventory row')
                name=row['fileName']
                if name.startswith('prod/qualification/'):
                    excluded+=1
                    continue
                if name.startswith('prod/qualification/') or not name.startswith('prod/'):
                    raise ValueError('unexpected namespace')
                # V219 known synthetic object in business-shaped namespace.
                if name=='prod/2026/11/dsig-prod-20261126T100822Z.dsigbak':
                    excluded+=1
                    continue
                selected.append(normalize(row,self.expected))
            return sorted(selected,key=lambda x:(x['object'],str(x['version']))),excluded
        records,excluded=scan()
        repeated,excluded_again=scan()
        after=self._json(['bucket','get',BUCKET])
        if records!=repeated or excluded!=excluded_again or review.inspect_bucket(after,self.expected)!=policy:
            raise ValueError('inventory or policy changed')
        result=review.plan(records,now=now)
        return dict(result,policy=policy,excluded_objects=excluded,inventory_observed_twice=True,
                    inventory_authenticated=False,production_authorized=False,delete_authorized=False)
