"""Local durable attempt reservations for qualification; no job execution."""
import hashlib
import hmac
import base64
import re
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import prod_authorization as auth
import prod_backup_orchestrator as guard
import prod_backup_rehearsal as rehearsal
import prod_backup_retry as retry
import operations

PURPOSE='DSIG-QUALIFICATION-RETRY-V1'
CODES=retry.TRANSIENT|{'PERMANENT','INTEGRITY','PERMISSION','UNKNOWN'}


def _identity(day,stage,run_id):
    retry.decide(now=auth.timestamp(day+'T00:00:00Z'),cycle_day=day,stage=stage,failures=[])
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{32}',run_id):
        raise ValueError('invalid run id')
    return f'{day}.{stage}.{run_id}'


def _read(state,now,day,stage,run_id,public,pin):
    prefix=_identity(day,stage,run_id)
    if not isinstance(public,bytes) or len(public)!=32 or not isinstance(pin,str) or not hmac.compare_digest(hashlib.sha256(public).hexdigest(),pin):
        raise ValueError('untrusted retry signer')
    previous='0'*64
    failures=[]
    pending=False
    completed=False
    count=0
    gap=False
    for i in range(1,retry.MAX_ATTEMPTS+1):
        for kind in ('start','end'):
            path=state/f'{prefix}.{i}.{kind}.json'
            if not path.exists() and not path.is_symlink():
                gap=True
                continue
            if gap or completed:
                raise ValueError('invalid attempt sequence')
            record=guard.read_proof(path)
            p=record['payload']
            if set(record)!={'payload','signature'} or set(p)!={'purpose','run_id','cycle','stage','attempt','event','at','code','previous','key_id'}:
                raise ValueError('invalid record')
            if (p['purpose'],p['run_id'],p['cycle'],p['stage'],p['attempt'],p['event'],p['previous'],p['key_id'])!=(PURPOSE,run_id,day,stage,i,kind,previous,pin):
                raise ValueError('invalid retry binding')
            Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(record['signature'],validate=True),auth.canonical(p))
            stamp=auth.timestamp(p['at'])
            if stamp>retry.utc(now):
                raise ValueError('future record')
            if kind=='start':
                decision=retry.decide(now=stamp,cycle_day=day,stage=stage,failures=failures)
                if decision['status']!='DUE' or p['code']!='START':
                    raise ValueError('invalid reservation')
                start=stamp
                count=i
                pending=True
            else:
                if not pending or stamp<start:
                    raise ValueError('invalid completion')
                pending=False
                if p['code']=='SUCCESS':
                    completed=True
                elif p['code'] in CODES:
                    failures.append(dict(at=stamp,code=p['code']))
                else:
                    raise ValueError('unknown outcome')
            previous=hashlib.sha256(auth.canonical(record)).hexdigest()
    decision=retry.decide(now=now,cycle_day=day,stage=stage,failures=failures)
    if pending:decision['status']='BLOCKED_UNCERTAIN'
    if completed:decision['status']='COMPLETE'
    return dict(decision,attempts=count,head=previous,pending=pending,qualification_only=True)


def inspect(state,*,now,day,stage,run_id,public,pin):
    state=Path(state)
    guard.private_dir(state)
    with guard.locked(state):
        return _read(state,now,day,stage,run_id,public,pin)


def record(state,*,now,day,stage,run_id,signer,pin,event,code):
    state=Path(state)
    guard.private_dir(state)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    with guard.locked(state):
        before=_read(state,now,day,stage,run_id,public,pin)
        if event=='start' and code=='START' and before['status']=='DUE':
            attempt=before['attempts']+1
        elif event=='end' and code in CODES|{'SUCCESS'} and before['pending']:
            attempt=before['attempts']
            # Validate end time before writing; outside-window results require review.
            retry.decide(now=now,cycle_day=day,stage=stage,failures=[dict(at=now,code='PERMANENT')])
        else:
            raise ValueError('attempt transition refused')
        p=dict(purpose=PURPOSE,run_id=run_id,cycle=day,stage=stage,attempt=attempt,event=event,
               at=retry.utc(now).strftime('%Y-%m-%dT%H:%M:%SZ'),code=code,previous=before['head'],key_id=pin)
        envelope=dict(payload=p,signature=base64.b64encode(signer.sign(auth.canonical(p))).decode('ascii'))
        operations.write_new(state/f'{_identity(day,stage,run_id)}.{attempt}.{event}.json',auth.canonical(envelope))
        rehearsal.sync_dir(state)
        return _read(state,now,day,stage,run_id,public,pin)
