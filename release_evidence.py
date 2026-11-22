"""Release evidence completeness check, not evidence authentication or production approval."""
import argparse
from datetime import datetime, timezone
import json
import re
import sys

GATES = (
    'ci_exact_sha','isolated_regression','compose_configuration','deployed_content',
    'site_fr_en_mobile','crm_catalogue_supply_chain','recruitment_missions_cra',
    'finance_exports_reconciliation','roles_mfa_revocation','antivirus_real',
    'tls_access_restriction','backup_offsite_restore','monitoring_alerts',
    'migration_rollback_review','independent_security_review','retention_policy',
    'business_acceptance','human_decision',
    'public_site_seo_isolation','saas_subscription_billing_renewal',
    'partner_commissions_targets','client_portal_isolation',
    'commercial_automation','strategic_dashboard','audit_governance',
)

def template(sha):
    return {'schema':2,'commit':sha,'environment':'REC','checks':{
        name:{'status':'NOT_RUN','commit':sha,'date_utc':'','reviewer':'','evidence_ref':''} for name in GATES}}

def valid_date(value, now):
    try:
        if not isinstance(value,str) or not value.endswith('Z'):
            return False
        date = datetime.fromisoformat(value[:-1]+'+00:00')
        return date <= now
    except (ValueError, TypeError):
        return False

def evaluate(data, sha, now=None):
    now = now or datetime.now(timezone.utc)
    valid = isinstance(data,dict) and type(data.get('schema')) is int and data.get('schema') == 2 and data.get('commit') == sha and data.get('environment') == 'REC'
    checks = data.get('checks') if valid else None
    exact = isinstance(checks,dict) and set(checks) == set(GATES)
    results = {}
    for name in GATES:
        item = checks.get(name) if isinstance(checks,dict) else None
        if not isinstance(item,dict) or item.get('commit') != sha:
            results[name] = 'INVALID'
        elif item.get('status') in ('FAIL','NOT_RUN'):
            results[name] = item['status']
        elif item.get('status') == 'PASS' and valid_date(item.get('date_utc'),now) and all(
            isinstance(item.get(k),str) and 0 < len(item[k].strip()) <= 256 for k in ('reviewer','evidence_ref')):
            results[name] = 'DECLARED_PASS'
        else:
            results[name] = 'INVALID'
    complete = valid and exact and all(v == 'DECLARED_PASS' for v in results.values())
    return {'commit':sha,'environment':'REC','status':'REVIEW_REQUIRED' if complete else 'NO_GO',
            'checks':results,'declared_pass_count':sum(v=='DECLARED_PASS' for v in results.values()),
            'total':len(GATES),'production_authorized':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sha')
    parser.add_argument('--template',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.sha):
        parser.error('Exact lowercase Git SHA required')
    if args.template:
        result=template(args.sha)
    else:
        try:
            result=evaluate(json.load(sys.stdin),args.sha)
        except (ValueError,OSError):
            result=evaluate(None,args.sha)
    print(json.dumps(result,indent=2))
    return int(not args.template and result['status']=='NO_GO')

if __name__=='__main__':
    raise SystemExit(main())
