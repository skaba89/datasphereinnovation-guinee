"""UTC backup-cycle planning. Read-only; never launches jobs or authorizes PROD."""
from datetime import datetime, timedelta, timezone

STAGES=(('snapshot',75,125),('export',125,180),('audit',180,240))


def plan(now, completed):
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('timezone-aware clock required')
    now=now.astimezone(timezone.utc)
    day=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if now<day+timedelta(minutes=75):
        day-=timedelta(days=1)
    cycle=day.date().isoformat()
    if not isinstance(completed,dict) or set(completed)-{x[0] for x in STAGES}:
        raise ValueError('invalid completion records')
    prior=day
    pending=False
    for name,start,end in STAGES:
        if name not in completed:
            pending=True
            continue
        stamp=completed[name]
        if pending or not isinstance(stamp,datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('invalid stage sequence')
        stamp=stamp.astimezone(timezone.utc)
        if not max(prior,day+timedelta(minutes=start))<=stamp<=min(now,day+timedelta(minutes=end)):
            raise ValueError('invalid completion time')
        prior=stamp
    result=dict(cycle=cycle,next_stage=None,status='COMPLETE',production_authorized=False,
                execution_authorized=False,completion_authenticated=False)
    for name,start,end in STAGES:
        if name in completed:
            continue
        result['next_stage']=name
        if now>=day+timedelta(minutes=end):
            result['status']='MISSED_WINDOW'
        elif now<day+timedelta(minutes=start):
            result['status']='WAIT'
        else:
            result['status']='DUE'
        break
    return result
