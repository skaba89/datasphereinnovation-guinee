"""Anchored qualification execution; old local-only rehearsal remains separate."""
from pathlib import Path
from cryptography.hazmat.primitives import serialization
import prod_backup_retry_anchor as mirror
import prod_backup_cycle_journal as journal
import prod_backup_retry as retry
import prod_backup_orchestrator as guard
import prod_backup_journal_anchor as anchor
from prod_b2_cli import B2ReadTimeout


def run(*, root, retry_state, execution_lock, clock, signer, pin, key, run_id, bucket_id, remote):
    root,state,lock=map(Path,(root,retry_state,execution_lock))
    paths=[p.resolve() for p in (root,state,lock)]
    if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(paths) for b in paths[i+1:]):
        raise ValueError('overlapping execution directories')
    for p in (root,state,lock):guard.private_dir(p)
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    with guard.locked(lock):
        now=retry.utc(clock())
        local=journal.read(root/'state',now=now,public=public,pin=pin)
        if local['status']!='COMPLETE':
            raise ValueError('local cycle incomplete')
        args=dict(day=local['cycle'],run_id=run_id,pin=pin,bucket_id=bucket_id,remote=remote)
        before=mirror.verify(state,now=now,public=public,**args)
        if before['status']!='DUE':
            return dict(before,performed=False,remote_verified=False)
        # Reservation must exist both locally and remotely before any business of this attempt.
        now=retry.utc(clock())
        reservation=mirror.transition(state,now=now,signer=signer,event='start',code='START',**args)
        if not reservation['pending'] or not reservation['retry_external_anchor_verified']:
            raise ValueError('reservation not anchored')
        current=retry.utc(clock())
        if journal.read(root/'state',now=current,public=public,pin=pin)['head']!=local['head']:
            raise ValueError('local journal changed')
        if retry.decide(now=current,cycle_day=local['cycle'],stage='audit',failures=[])['status']!='DUE':
            raise ValueError('audit window closed after reservation')
        try:
            result=anchor.publish(root=root,now=current,signer=signer,pin=pin,key=key,run_id=run_id,bucket_id=bucket_id,remote=remote)
            if result.get('status')!='PASS' or result.get('remote_restore_verified') is not True or result.get('external_journal_anchor_verified') is not True or result.get('journal_head')!=local['head']:
                raise ValueError('incomplete remote proof')
        except B2ReadTimeout:
            code='NETWORK_TIMEOUT'
            result=None
        except Exception:
            code='UNKNOWN'
            result=None
        else:
            code='SUCCESS'
        after=mirror.transition(state,now=retry.utc(clock()),signer=signer,event='end',code=code,**args)
        return dict(after,performed=True,outcome=code,proof=result,
                    remote_verified=code=='SUCCESS')
