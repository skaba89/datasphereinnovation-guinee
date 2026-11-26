"""Review-only validator of resolved Docker Compose JSON. Never authorizes PROD."""
import json
import re
import sys

STOP = ["python", "-c", "raise SystemExit('PROD review topology: startup disabled')"]
ENV = {'DSIG_ENV': 'PROD', 'DSIG_HTTPS_ORIGIN': 'https://app.dsig-consulting.com',
       'DSIG_DB': '/app/data/requests.sqlite3', 'DSIG_CLAMD_SOCKET': '/run/dsig-clamav/clamd.ctl',
       'DSIG_MFA_REQUIRED_ROLES': 'ADMIN,CLIENT,DIRECTION,CONTROLE,COMPTABLE,AUDITEUR'}
KEYS = {'DSIG_MFA_KEY', 'DSIG_BACKUP_KEY', 'DSIG_DOCUMENT_KEY'}
SERVICE_FIELDS = {'profiles', 'image', 'pull_policy', 'user', 'environment', 'group_add',
                  'ports', 'volumes', 'networks', 'read_only', 'tmpfs', 'cap_drop',
                  'security_opt', 'mem_limit', 'mem_reservation', 'memswap_limit',
                  'cpus', 'pids_limit', 'restart', 'logging', 'entrypoint'}


def validate(c, expected_image, expected_port):
    checks = dict.fromkeys(('project', 'image', 'environment', 'port', 'volume', 'network',
                            'privileges', 'resources', 'logging', 'startup_lock'), False)
    try:
        s = c['services']['app']
        checks['project'] = (set(c) == {'name', 'services', 'volumes', 'networks'}
                             and c['name'] == 'dsig-prod' and set(c['services']) == {'app'}
                             and SERVICE_FIELDS <= set(s) <= SERVICE_FIELDS | {'command'}
                             and s.get('command') in (None, []))
        checks['image'] = (isinstance(expected_image, str) and bool(re.fullmatch(
            r'[^\s@]+@sha256:[0-9a-f]{64}', expected_image)) and s['image'] == expected_image
            and s['pull_policy'] == 'never')
        env = s['environment']
        checks['environment'] = (set(env) == set(ENV) | KEYS
                                 and all(env[k] == v for k, v in ENV.items())
                                 and all(isinstance(env[k], str) and bool(env[k]) for k in KEYS))
        p = s['ports'][0]
        checks['port'] = (len(s['ports']) == 1 and set(p) <= {'mode','host_ip','target','published','protocol'}
                          and p.get('mode','ingress') == 'ingress' and p.get('protocol','tcp') == 'tcp'
                          and p['host_ip'] == '127.0.0.1' and p['target'] == 8080
                          and str(p['published']) == str(expected_port)
                          and 1024 <= int(expected_port) <= 65535 and int(expected_port) not in (8300,8310))
        mounts = {m['target']: m for m in s['volumes']}
        d, a = mounts['/app/data'], mounts['/run/dsig-clamav']
        checks['volume'] = (len(s['volumes']) == 2 and set(c['volumes']) == {'prod-data'}
                            and c['volumes']['prod-data'] == {'name':'dsig-prod_prod-data'}
                            and set(d) <= {'type','source','target','volume','read_only'}
                            and d['type'] == 'volume' and d['source'] == 'prod-data'
                            and not d.get('read_only',False) and d.get('volume',{}) == {}
                            and set(a) <= {'type','source','target','read_only','bind'}
                            and a['type'] == 'bind' and a['source'] == '/run/clamav'
                            and a['read_only'] is True and a.get('bind',{}) in ({},{'create_host_path':False}))
        checks['network'] = (s['networks'] in ({'prod-private':None},{'prod-private':{}})
                             and set(c['networks']) == {'prod-private'}
                             and set(c['networks']['prod-private']) <= {'name','internal','ipam'}
                             and c['networks']['prod-private']['name'] == 'dsig-prod_prod-private'
                             and c['networks']['prod-private']['internal'] is True
                             and c['networks']['prod-private'].get('ipam') in (
                                 None, {}, {'driver':'default'}, {'config':[]},
                                 {'driver':'default','config':[]}))
        checks['privileges'] = (s['user'] == '10001:10001' and s['read_only'] is True
                                and s['cap_drop'] == ['ALL']
                                and s['security_opt'] in (['no-new-privileges:true'],['no-new-privileges=true'])
                                and len(s['group_add']) == 1 and 0 < int(s['group_add'][0]) < 2**31
                                and s['tmpfs'] == ['/tmp:rw,noexec,nosuid,nodev,size=64m'])
        checks['resources'] = (int(s['mem_limit']) == 536870912 and int(s['mem_reservation']) == 134217728
                               and int(s['memswap_limit']) == 536870912 and float(s['cpus']) == 2
                               and int(s['pids_limit']) == 128)
        checks['logging'] = s['logging'] == {'driver':'json-file','options':{'max-size':'10m','max-file':'5'}}
        checks['startup_lock'] = s['entrypoint'] == STOP and s['restart'] == 'no' and s['profiles'] == ['prod-review']
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        pass
    return {'status':'PASS' if all(checks.values()) else 'FAIL',
            'checks':{k:'PASS' if v else 'FAIL' for k,v in checks.items()}, 'production_authorized':False}


if __name__ == '__main__':
    try:
        result = validate(json.load(sys.stdin), sys.argv[1], sys.argv[2])
    except (ValueError, IndexError, OSError):
        result = {'status':'FAIL','checks':{'input':'FAIL'},'production_authorized':False}
    print(json.dumps(result))
    raise SystemExit(int(result['status'] != 'PASS'))
