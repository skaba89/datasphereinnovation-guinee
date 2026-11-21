#!/usr/bin/env python3
"""Compare resolved REC Compose configurations; no writes or deployment."""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verify_rec_config import validate


def check(before, after, sha):
    checks = dict.fromkeys(('baseline','candidate','rec_endpoint','rec_networks','candidate_image','only_image_changed'), False)
    try:
        checks['baseline'] = validate(before,'rec','dsig-rec_dsig-data')['status'] == 'PASS'
        checks['candidate'] = validate(after,'rec','dsig-rec_dsig-data')['status'] == 'PASS'
        a = after['services']['dsig']
        checks['rec_endpoint'] = (str(a['ports'][0]['published']) == '8300'
                                  and a['environment']['DSIG_HTTPS_ORIGIN'] == 'https://rec.dsig-consulting.com')
        checks['rec_networks'] = (set(a['networks']) == {'default','edge'}
                                  and after['networks']['default']['name'] == 'dsig-rec_default'
                                  and after['networks']['edge']['name'] == 'edge'
                                  and after['networks']['edge']['external'] is True)
        checks['candidate_image'] = bool(re.fullmatch(r'[0-9a-f]{40}',sha)) and a.get('image') == 'dsig-rec-candidate:'+sha
        original, proposed = copy.deepcopy(before), copy.deepcopy(after)
        for config in (original, proposed):
            config['services']['dsig'].pop('image',None)
        checks['only_image_changed'] = original == proposed
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        pass
    return {'status':'PASS' if all(checks.values()) else 'FAIL',
            'checks':{key:'PASS' if value else 'FAIL' for key,value in checks.items()},
            'production_authorized':False}


def read(path):
    try:
        with open(path,encoding='utf-8') as source:
            return json.load(source)
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sha')
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    args = parser.parse_args()
    result = check(read(args.baseline),read(args.candidate),args.sha)
    print(json.dumps(result,indent=2))
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
