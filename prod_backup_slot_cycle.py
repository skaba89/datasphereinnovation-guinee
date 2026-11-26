"""Slot-specific qualification planner, compatible with neither legacy IDs nor business authorization."""
from datetime import timedelta
from prod_backup_cadence import utc,slots,plan as cadence_plan

STAGES=('snapshot','export','audit')

def plan(now,completed):
    now=utc(now)
    identity=cadence_plan(now)['current_slot']
    slot=next(s for s in slots(identity[:10]) if s['slot']==identity)
    cycle=identity[:10]+'-'+identity[11:13]
    if not isinstance(completed,dict) or set(completed)-set(STAGES):
        raise ValueError('invalid completion records')
    previous=slot['snapshot_start']
    missing=False
    for stage in STAGES:
        if stage not in completed:
            missing=True
            continue
        stamp=utc(completed[stage])
        if missing or not max(previous,slot[stage+'_start'])<=stamp<=now or stamp>=slot[stage+'_end']:
            raise ValueError('invalid slot completion')
        previous=stamp
    result=dict(cycle=cycle,slot=identity,next_stage=None,status='COMPLETE',production_authorized=False,execution_authorized=False,completion_authenticated=False)
    for stage in STAGES:
        if stage in completed:continue
        result['next_stage']=stage
        result['status']='MISSED_WINDOW' if now>=slot[stage+'_end'] else ('WAIT' if now<slot[stage+'_start'] else 'DUE')
        break
    return result
