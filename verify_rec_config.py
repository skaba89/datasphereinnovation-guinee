"""Validate resolved REC Compose JSON from stdin; never print configuration or secrets."""
import argparse
import json
import sys

def validate(config, profile, expected_volume):
    project, service = ('dsig-rec', 'dsig') if profile == 'rec' else ('dsig-prod-candidate', 'candidate')
    checks = dict.fromkeys(('project_service','rec_mode','loopback_port','isolation','data_volume','scanner_mount'), False)
    try:
        services = config['services']
        app = services[service]
        checks['project_service'] = config.get('name') == project and set(services) == {service}
        env = app.get('environment', {})
        checks['rec_mode'] = env.get('DSIG_ENV') == 'REC'
        ports = app.get('ports', [])
        checks['loopback_port'] = len(ports) == 1 and ports[0].get('host_ip') == '127.0.0.1' and ports[0].get('target') == 8080 and str(ports[0].get('published','')).isdigit()
        checks['isolation'] = (app.get('read_only') is True and 'ALL' in app.get('cap_drop', [])
            and not app.get('cap_add') and not app.get('privileged') and not app.get('devices')
            and not app.get('device_cgroup_rules') and not app.get('volumes_from')
            and app.get('network_mode','') != 'host' and app.get('pid','') != 'host' and app.get('ipc','') != 'host'
            and not app.get('user') and any(v in ('no-new-privileges:true','no-new-privileges=true','no-new-privileges') for v in app.get('security_opt', [])))
        mounts = app.get('volumes', [])
        data = [v for v in mounts if v.get('target') == '/app/data']
        scanner = [v for v in mounts if v.get('target') == '/run/dsig-clamav']
        checks['data_volume'] = (len(data) == 1 and data[0].get('type') == 'volume'
            and not data[0].get('read_only') and config.get('volumes',{}).get(data[0].get('source'),{}).get('name') == expected_volume)
        checks['scanner_mount'] = (len(mounts) == 2 and len(scanner) == 1 and scanner[0].get('type') == 'bind'
            # Docker Compose >= 2.40 omits boolean options set to false from its resolved JSON: an absent
            # create_host_path means false. Only an explicit true (silent creation of an empty host
            # directory in place of the clamd socket) is refused.
            and scanner[0].get('read_only') is True and scanner[0].get('bind',{}).get('create_host_path',False) is False
            and env.get('DSIG_CLAMD_SOCKET') == '/run/dsig-clamav/clamd.ctl'
            and scanner[0].get('source','').startswith('/') and scanner[0].get('source') not in ('/','/var/run','/run','/etc'))
    except (KeyError, TypeError, AttributeError, IndexError):
        pass
    return {'status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {k: 'PASS' if v else 'FAIL' for k,v in checks.items()},
            'production_authorized': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('rec','candidate'), required=True)
    parser.add_argument('--volume', required=True, help='Expected resolved Docker volume name, verified independently')
    args = parser.parse_args()
    try:
        config = json.load(sys.stdin)
        result = validate(config,args.profile,args.volume)
    except (ValueError, OSError):
        result = {'status':'FAIL','checks':{'json':'FAIL'},'production_authorized':False}
    print(json.dumps(result,indent=2))
    return int(result['status'] != 'PASS')

if __name__ == '__main__':
    raise SystemExit(main())
