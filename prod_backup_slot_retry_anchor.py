"""Strict external mirror of the signed audit retry ledger.

No implicit repair: a missing or divergent previously anchored record blocks.
"""
from pathlib import Path
import hmac
from cryptography.hazmat.primitives import serialization
import prod_authorization as auth
import prod_backup_slot_retry_ledger as ledger
import prod_backup_orchestrator as guard
import prod_backup_journal_anchor as anchor
from prod_b2_export import BUCKET


def _objects(state,day,run_id):
    prefix=ledger._identity(day,'audit',run_id)
    for i in range(1,6):
        for event in ('start','end'):
            yield (state/f'{prefix}.{i}.{event}.json',
                   f'prod/qualification/v232-slots/{run_id}/{day}/retry/audit/{i}.{event}.json')


def _compare(state,*,now,day,run_id,public,pin,bucket_id,remote,allow_new=None):
    result=ledger._read(state,now,day,'audit',run_id,public,pin)
    anchor.policy_check(remote,bucket_id)
    count=0
    objects=list(_objects(state,day,run_id))
    batch=getattr(remote,'read_slot_retry_records',None)
    def inventory():
        if batch is None:
            return {obj:remote.read(BUCKET,obj) for _,obj in objects}
        rows=batch(BUCKET,run_id,day)
        if not isinstance(rows,dict) or set(rows)-{obj for _,obj in objects}:
            raise ValueError('invalid retry batch')
        if any(not isinstance(v,bytes) or not 0<len(v)<=8192 for v in rows.values()):
            raise ValueError('invalid retry batch record')
        return rows
    stored_records=inventory()
    # Compare all existing slots before writing even a single new record.
    pending=None
    for path,obj in objects:
        present=path.exists() or path.is_symlink()
        raw=auth.canonical(guard.read_proof(path)) if present else None
        stored=stored_records.get(obj)
        if raw is None and stored is None:
            continue
        if raw is not None and stored is None and path==allow_new:
            pending=(obj,raw)
            continue
        if not isinstance(raw,bytes) or not isinstance(stored,bytes) or not hmac.compare_digest(raw,stored):
            raise ValueError('retry anchor missing or divergent; operator review required')
        count+=1
    if pending is not None:
        obj,raw=pending
        remote.create_only(BUCKET,obj,raw)
        after=inventory()
        expected={k:v for k,v in stored_records.items() if v is not None}
        expected[obj]=raw
        if {k:v for k,v in after.items() if v is not None}!=expected:
            raise ValueError('retry inventory changed after publication')
        count+=1
    return dict(result,retry_external_anchor_verified=True,anchored_records=count)


def verify(state,*,now,day,run_id,public,pin,bucket_id,remote):
    state=Path(state)
    guard.private_dir(state)
    with guard.locked(state):
        return _compare(state,now=now,day=day,run_id=run_id,public=public,pin=pin,bucket_id=bucket_id,remote=remote)


def transition(state,*,now,day,run_id,signer,pin,bucket_id,remote,event,code):
    """Use a dedicated outer lock directory for the entire execution lifecycle.

    This function is a single-writer primitive. Local-only partial writes block.
    """
    state=Path(state)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    args=dict(now=now,day=day,run_id=run_id,public=public,pin=pin,bucket_id=bucket_id,remote=remote)
    before=verify(state,**args)
    result=ledger.record(state,now=now,day=day,stage='audit',run_id=run_id,signer=signer,pin=pin,event=event,code=code)
    attempt=result['attempts']
    expected=state/f"{ledger._identity(day,'audit',run_id)}.{attempt}.{event}.json"
    with guard.locked(state):
        after=_compare(state,allow_new=expected,**args)
    if after['head']!=result['head'] or after['anchored_records']!=before['anchored_records']+1:
        raise ValueError('unexpected retry anchor transition')
    return after
