"""Read-only retention review. No delete, hide, bucket update or production authority."""
from datetime import datetime,timedelta,timezone
import re
from prod_b2_export import NAME,BUCKET
from prod_backup_cadence import utc

LOCAL_DAYS=7
REMOTE_DAYS=90
LOCK_DAYS=30

def inspect_bucket(bucket,expected_bucket_id):
    checks=dict(identity=False,privacy=False,object_lock=False,lifecycle_safe=False)
    if not isinstance(bucket,dict):
        return dict(status='FAIL',checks=checks,production_authorized=False)
    checks['identity']=isinstance(expected_bucket_id,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{8,128}',expected_bucket_id)) and bucket.get('bucketId')==expected_bucket_id and bucket.get('bucketName')==BUCKET
    checks['privacy']=bucket.get('bucketType')=='allPrivate' and bucket.get('defaultServerSideEncryption')=={'mode':'SSE-B2','algorithm':'AES256'}
    retention=bucket.get('defaultRetention')
    if isinstance(retention,dict):
        period=retention.get('period')
        checks['object_lock']=bucket.get('isFileLockEnabled') is True and retention.get('mode')=='compliance' and isinstance(period,dict) and period.get('unit')=='days' and type(period.get('duration')) is int and period['duration']>=LOCK_DAYS
    # No automatic expiry until a separate, explicitly approved tier policy.
    checks['lifecycle_safe']=bucket.get('lifecycleRules')==[]
    return dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
                automatic_expiry_configured=False,production_authorized=False)

def archive_stamp(name):
    if not isinstance(name,str):raise ValueError('invalid archive object')
    parts=name.split('/')
    if len(parts)!=4 or parts[0]!='prod':raise ValueError('non-business namespace')
    match=NAME.fullmatch(parts[-1])
    if not match:raise ValueError('invalid archive name')
    stamp=datetime.strptime(match.group(1),'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if parts[1:3]!=[stamp.strftime('%Y'),stamp.strftime('%m')]:raise ValueError('archive path mismatch')
    return stamp

def plan(records,*,now):
    """Conservative review of normalized inventory, not evidence of restorability.
    
    All monthly and annual candidates are held until separately authenticated.
    Unknown metadata, duplicate versions and missing locks block the entire plan.
    """
    now=utc(now)
    if not isinstance(records,list) or len(records)>10000:raise ValueError('invalid inventory')
    parsed=[]
    names=set()
    ids=set()
    for row in records:
        if not isinstance(row,dict) or set(row)!={'object','version','action','uploaded_at','retain_until','lock_mode','legal_hold'}:
            raise ValueError('invalid inventory record')
        stamp=archive_stamp(row['object'])
        version=row['version']
        if not isinstance(version,str) or not version or version in ids or row['object'] in names or row['action']!='upload':
            raise ValueError('ambiguous inventory')
        ids.add(version);names.add(row['object'])
        uploaded=utc(row['uploaded_at'])
        locked=utc(row['retain_until'])
        if not stamp<=uploaded<=now or locked<uploaded+timedelta(days=LOCK_DAYS) or row['lock_mode']!='compliance' or type(row['legal_hold']) is not bool:
            raise ValueError('invalid retention metadata')
        parsed.append((stamp,row,uploaded,locked))
    # Preserve newest two and one newest archive per month/year independently
    # of verification; no purge selection may assume a synthetic archive is real.
    ordered=sorted(parsed,key=lambda x:x[0],reverse=True)
    months=set();years=set()
    decisions=[]
    for i,(stamp,row,uploaded,locked) in enumerate(ordered):
        month=stamp.strftime('%Y-%m');year=stamp.year
        monthly=month not in months
        annual=year not in years
        months.add(month);years.add(year)
        age=now-stamp
        if row['legal_hold'] or now<locked:reason='LOCKED'
        elif i<2:reason='KEEP_NEWEST_TWO'
        elif age<timedelta(days=REMOTE_DAYS):reason='KEEP_90_DAYS'
        elif monthly or annual:reason='KEEP_TIER_REVIEW'
        else:reason='REVIEW_EXPIRED'
        decisions.append(dict(object=row['object'],version=row['version'],decision=reason,delete_authorized=False))
    return dict(status='REVIEW_ONLY',objects=decisions,inventory_authenticated=False,
                restore_verified=False,delete_authorized=False,production_authorized=False)
