"""Read-only evaluation of future daily backup evidence.

No scheduler, remote calls, or production authorization.
Review evidence can never count as a business backup.
"""
import re
from datetime import datetime, timezone, timedelta
from prod_b2_export import NAME

SYNTHETIC={'dsig-prod-20261126T100822Z.dsigbak'}
FIELDS={'schema','kind','archive','object','sha256','bucket_id','verified_at',
        'qualification_only','synthetic_data','ephemeral_key','remote_restore_verified',
        'daily_backup_qualified','production_authorized'}


def evaluate(proof, *, expected_bucket_id, now=None):
    now=datetime.now(timezone.utc) if now is None else now
    checks=dict.fromkeys(('business_evidence','identity','freshness','integrity_claim'),'NOT_RUN')
    try:
        checks['business_evidence']='FAIL'
        if not isinstance(proof,dict) or set(proof)!=FIELDS or type(proof['schema']) is not int or proof['schema']!=1:
            raise ValueError()
        if (proof['kind']!='business-daily' or proof['qualification_only'] is not False
                or proof['synthetic_data'] is not False or proof['ephemeral_key'] is not False
                or proof['daily_backup_qualified'] is not True or proof['production_authorized'] is not False):
            raise ValueError()
        if proof['archive'] in SYNTHETIC:
            raise ValueError()
        checks['business_evidence']='PASS'
        checks['identity']='FAIL'
        match=NAME.fullmatch(proof['archive'])
        if not match or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',expected_bucket_id):
            raise ValueError()
        stamp=match.group(1)
        if proof['bucket_id']!=expected_bucket_id or proof['object']!=f"prod/{stamp[:4]}/{stamp[4:6]}/{proof['archive']}":
            raise ValueError()
        checks['identity']='PASS'
        checks['freshness']='FAIL'
        created=datetime.strptime(stamp,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        verified=datetime.fromisoformat(proof['verified_at'])
        if not isinstance(now,datetime) or now.utcoffset() is None or verified.utcoffset() is None:
            raise ValueError()
        now=now.astimezone(timezone.utc)
        verified=verified.astimezone(timezone.utc)
        if not created<=verified<=now or now-created>timedelta(hours=24):
            raise ValueError()
        # Both UTC slots share the same half-open windows. Audit is separate.
        from prod_backup_cadence import slot_for_snapshot
        slot=slot_for_snapshot(created)
        if slot is None or not slot['export_start']<=verified<slot['export_end']:
            raise ValueError()
        checks['freshness']='PASS'
        checks['integrity_claim']='FAIL'
        if not re.fullmatch(r'[0-9a-f]{64}',proof['sha256']) or proof['remote_restore_verified'] is not True:
            raise ValueError()
        checks['integrity_claim']='PASS'
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        pass
    return {'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'FAIL',
            'checks':checks,'evidence_authenticated':False,'remote_verified':False,
            'production_authorized':False}
