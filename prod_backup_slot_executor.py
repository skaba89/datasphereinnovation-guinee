"""One-step local qualification executor. No remote writes or production authority."""
import hashlib
import hmac
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives import serialization
import operations
import prod_backup_slot_journal as journal
import prod_backup_orchestrator as guard
import prod_backup_rehearsal as rehearsal
import prod_snapshot_review as snapshot
import prod_b2_export as export


def run(*, root, active, now, key, signer, pin, source_check):
    root,active=Path(root),Path(active)
    guard.private_dir(root)
    if root.resolve().is_relative_to(active.parent.resolve()) or active.resolve().is_relative_to(root.resolve()):
        raise ValueError('overlapping source and qualification root')
    state=root/'state'
    locks=root/'locks'
    archives=root/'archives'
    replica=root/'replica'
    for p in (state,locks,archives,replica):
        guard.private_dir(p)
    if len({p.resolve() for p in (state,locks,archives,replica)})!=4:
        raise ValueError('overlapping qualification directories')
    public=signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    with guard.locked(locks):
        before=journal.read(state,now=now,public=public,pin=pin)
        day=before['cycle'][:10].replace('-','')
        hour=before['cycle'][-2:]
        name=f'dsig-prod-{day}T{hour}1500Z.dsigbak'
        a,b=archives/name,replica/name
        def present(p):return p.exists() or p.is_symlink()
        def verified(p):
            data=rehearsal.read_archive(p)
            export.verify_archive(data,key)
            return data
        def same(data,expected):
            if not hmac.compare_digest(hashlib.sha256(data).hexdigest(),expected):
                raise ValueError('archive digest mismatch')
        stage=before['next_stage']
        digest=before['archive_sha256']
        # Revalidate existing artifacts before proceeding or reporting completion.
        if digest is not None:
            data=verified(a)
            same(data,digest)
            if stage=='audit' or before['status']=='COMPLETE':
                same(verified(b),digest)
        if before['status']!='DUE':
            return dict(before,performed=False,remote_verified=False)
        if stage=='snapshot':
            # An unsigned orphan cannot be trusted as the intended source.
            if present(a) or present(b):
                raise ValueError('unsigned snapshot requires operator review')
            result=snapshot.create_review_snapshot(active,a,backup_key=key,source_check=source_check)
            digest=result['sha256']
            same(verified(a),digest)
        elif stage=='export':
            # Local replica only, never B2. An interrupted copy may be reused
            # only if its exact bytes match the signed snapshot.
            if not present(b):
                operations.write_new(b,data)
                rehearsal.sync_dir(replica)
            same(verified(b),digest)
        elif stage=='audit':
            same(verified(b),digest)
        else:
            raise ValueError('unexpected stage')
        after=journal.append(state,now=now,stage=stage,archive_sha256=digest,signer=signer,pin=pin)
        return dict(after,performed=True,performed_stage=stage,remote_verified=False)
