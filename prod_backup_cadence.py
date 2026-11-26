"""Biquotidian UTC policy, not a scheduler or business backup producer."""
from datetime import datetime,timedelta,timezone
from prod_b2_export import NAME

RPO=timedelta(hours=24)
INTERVAL=timedelta(hours=12)
MINUTES=(75,795)

def utc(value):
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('timezone-aware clock required')
    return value.astimezone(timezone.utc)

def slots(day):
    if type(day) is not str:
        raise ValueError('invalid day')
    midnight=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    if midnight.date().isoformat()!=day:
        raise ValueError('invalid day')
    result=[]
    for offset in MINUTES:
        start=midnight+timedelta(minutes=offset)
        result.append(dict(slot=start.strftime('%Y-%m-%dT%H:%MZ'),
                           snapshot_start=start,snapshot_end=start+timedelta(minutes=50),
                           export_start=start+timedelta(minutes=50),export_end=start+timedelta(minutes=105),
                           audit_start=start+timedelta(minutes=105),audit_end=start+timedelta(minutes=165)))
    return result

def slot_for_snapshot(stamp):
    stamp=utc(stamp)
    return next((s for s in slots(stamp.date().isoformat()) if s['snapshot_start']<=stamp<s['snapshot_end']),None)

def plan(now):
    now=utc(now)
    day=now.date()
    candidates=[s for delta in (-1,0,1) for s in slots((day+timedelta(days=delta)).isoformat())]
    last=max((s for s in candidates if s['snapshot_start']<=now),key=lambda s:s['snapshot_start'])
    next_slot=min((s for s in candidates if s['snapshot_start']>now),key=lambda s:s['snapshot_start'])
    phase=next((n for n in ('snapshot','export','audit') if last[n+'_start']<=now<last[n+'_end']),'IDLE')
    return dict(current_slot=last['slot'],phase=phase,next_snapshot=next_slot['snapshot_start'].isoformat(),
                production_authorized=False,execution_authorized=False)

def evaluate(envelopes,public_key,*,pinned_key_id,expected_bucket_id,remote,backup_key,now):
    """Check fresh signed claims against actual remote bytes, not caller PASS flags."""
    import prod_backup_authenticated as authenticated
    now=utc(now)
    if not isinstance(envelopes,list) or len(envelopes)>8:
        raise ValueError('bounded evidence list required')
    valid=[]
    rejected=0
    seen=set()
    for envelope in envelopes:
        result=authenticated.verify(envelope,public_key,pinned_key_id=pinned_key_id,
                  expected_bucket_id=expected_bucket_id,remote=remote,backup_key=backup_key,now=now)
        if result['status']!='PASS' or result['evidence_authenticated'] is not True or result['remote_verified'] is not True:
            rejected+=1
            continue
        proof=envelope['proof']
        stamp=datetime.strptime(NAME.fullmatch(proof['archive']).group(1),'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if proof['object'] in seen:
            continue
        seen.add(proof['object'])
        valid.append(stamp)
    latest=max(valid,default=None)
    age=(now-latest).total_seconds() if latest is not None else None
    remaining=RPO.total_seconds()-age if age is not None else None
    # Early warning when next scheduled cycle cannot complete before deadline.
    nxt=datetime.fromisoformat(plan(now)['next_snapshot'])
    deadline=latest+RPO if latest is not None else None
    # Include an active cycle if its export window has not expired.
    active=[s for s in slots(now.date().isoformat()) if s['snapshot_start']<=now<s['export_end']]
    next_export_end=active[0]['export_end'] if active else nxt+timedelta(minutes=105)
    status='NO_VERIFIED_BACKUP' if latest is None else ('BREACH' if remaining<0 else ('AT_RISK' if next_export_end>deadline else 'WITHIN_RPO'))
    return dict(status=status,latest_verified_snapshot=latest.isoformat() if latest else None,
                age_seconds=age,remaining_seconds=remaining,verified_archives=len(valid),rejected_claims=rejected,
                next_export_deadline=next_export_end.isoformat(),production_authorized=False,
                cadence_operationally_qualified=False)
