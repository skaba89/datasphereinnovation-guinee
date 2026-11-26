"""Execute one qualification audit attempt under durable retry reservations."""
from pathlib import Path
from cryptography.hazmat.primitives import serialization
import prod_backup_retry_ledger as ledger
import prod_backup_cycle_journal as journal
import prod_backup_retry as retry
import prod_backup_orchestrator as guard
import prod_backup_journal_anchor as anchor
from prod_b2_cli import B2ReadTimeout


def run(*, root, retry_state, clock, signer, pin, key, run_id, bucket_id, remote):
    root,state=Path(root),Path(retry_state)
    guard.private_dir(root)
    guard.private_dir(state)
    if root.resolve()==state.resolve() or root.resolve() in state.resolve().parents or state.resolve() in root.resolve().parents:
        raise ValueError('overlapping retry state')
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    now=retry.utc(clock())
    local=journal.read(root/'state',now=now,public=public,pin=pin)
    if local['status']!='COMPLETE':
        raise ValueError('local cycle incomplete')
    args=dict(day=local['cycle'],stage='audit',run_id=run_id,pin=pin)
    before=ledger.inspect(state,now=now,public=public,**args)
    if before['status']!='DUE':
        return dict(before,performed=False,remote_verified=False)
    ledger.record(state,now=now,signer=signer,event='start',code='START',**args)
    try:
        result=anchor.publish(root=root,now=now,signer=signer,pin=pin,key=key,run_id=run_id,bucket_id=bucket_id,remote=remote)
        if result.get('status')!='PASS' or result.get('remote_restore_verified') is not True or result.get('external_journal_anchor_verified') is not True:
            raise ValueError('incomplete remote proof')
    except B2ReadTimeout:
        code='NETWORK_TIMEOUT'
        result=None
    except Exception:
        # Unknown/write errors are never automatically replayed.
        code='UNKNOWN'
        result=None
    else:
        code='SUCCESS'
    finished=retry.utc(clock())
    after=ledger.record(state,now=finished,signer=signer,event='end',code=code,**args)
    return dict(after,performed=True,remote_verified=code=='SUCCESS',
                outcome=code,proof=result)
