"""Bounded retry planning, not an executor or production authorization."""
from datetime import datetime, timedelta, timezone
from prod_backup_cycle import STAGES

# Only explicitly classified transient failures can be retried.
TRANSIENT=frozenset({'NETWORK_TIMEOUT','NETWORK_UNAVAILABLE','REMOTE_THROTTLED'})
DELAYS=(60,120,240,480)
MAX_ATTEMPTS=5


def utc(value):
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('timezone-aware clock required')
    return value.astimezone(timezone.utc)


def decide(*, now, cycle_day, stage, failures):
    now=utc(now)
    day=datetime.strptime(cycle_day,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    if day.date().isoformat()!=cycle_day:
        raise ValueError('invalid cycle day')
    windows={n:(day+timedelta(minutes=s),day+timedelta(minutes=e)) for n,s,e in STAGES}
    if stage not in windows or not isinstance(failures,list) or len(failures)>MAX_ATTEMPTS:
        raise ValueError('invalid retry history')
    start,end=windows[stage]
    previous=None
    permanent=False
    for failure in failures:
        if not isinstance(failure,dict) or set(failure)!={'at','code'} or not isinstance(failure['code'],str) or not failure['code']:
            raise ValueError('invalid failure record')
        stamp=utc(failure['at'])
        if not start<=stamp<end or stamp>now or (previous is not None and stamp<=previous):
            raise ValueError('invalid failure chronology')
        previous=stamp
        permanent=permanent or failure['code'] not in TRANSIENT
    result=dict(status='WAIT',attempts=len(failures),next_attempt_at=None,
                production_authorized=False,execution_authorized=False)
    if permanent:
        result['status']='BLOCKED_PERMANENT'
    elif now>=end:
        result['status']='MISSED_WINDOW'
    elif len(failures)>=MAX_ATTEMPTS:
        result['status']='EXHAUSTED'
    else:
        due=start if previous is None else previous+timedelta(seconds=DELAYS[len(failures)-1])
        if due>=end:
            result['status']='MISSED_WINDOW'
        else:
            result['next_attempt_at']=due.isoformat()
            result['status']='DUE' if now>=due else 'WAIT'
    return result
