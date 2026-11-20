"""Read-only technical release evidence; never authorizes production."""
import json
import subprocess
import sys
from urllib.request import urlopen

REC = 'dsig-rec-dsig-1'
CANDIDATE = 'dsig-prod-candidate-candidate-1'


def command(*args):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=45).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def parse(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def config(container):
    # Only inspect networking and mount metadata, never environment variables.
    return parse(command('docker', 'inspect', '--format',
                         '{"mounts":{{json .Mounts}},"ports":{{json .NetworkSettings.Ports}},"networks":{{json .NetworkSettings.Networks}}}',
                         container))


def data_volume(info):
    if not isinstance(info, dict):
        return None
    matches = [m.get('Name') for m in info.get('mounts', [])
               if m.get('Destination') == '/app/data' and m.get('Type') == 'volume']
    return matches[0] if len(matches) == 1 and matches[0] else None


def private_port(info, port):
    if not isinstance(info, dict):
        return False
    ports = info.get('ports', {})
    return ports.get('8080/tcp') == [{'HostIp': '127.0.0.1', 'HostPort': str(port)}] and all(
        not value for key, value in ports.items() if key != '8080/tcp')


def ready(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/ready', timeout=5) as response:
            return response.status == 200 and json.loads(response.read(4096)) == {'status': 'ready'}
    except (OSError, ValueError):
        return False


def inspect():
    rec, candidate = config(REC), config(CANDIDATE)
    rec_volume, candidate_volume = data_volume(rec), data_volume(candidate)
    checks = {
        'distinct_data_volumes': bool(rec_volume and candidate_volume and rec_volume != candidate_volume),
        'rec_loopback': private_port(rec, 8300),
        'candidate_loopback': private_port(candidate, 8310),
        'candidate_no_edge': isinstance(candidate, dict) and set(candidate.get('networks', {})) == {'dsig-prod-candidate_default'},
        'rec_ready': ready(8300),
        'candidate_ready': ready(8310),
    }
    for label, container in (('rec', REC), ('candidate', CANDIDATE)):
        preflight = parse(command('docker', 'exec', container, 'python', 'preflight.py'))
        antivirus = parse(command('docker', 'exec', container, 'python', 'check_antivirus.py'))
        checks[label + '_preflight'] = isinstance(preflight, dict) and preflight.get('status') == 'PASS' and preflight.get('production_authorized') is False
        checks[label + '_antivirus'] = antivirus == {'clean': 'PASS', 'eicar_rejected': 'PASS'}
    return {'technical_status': 'PASS' if all(checks.values()) else 'FAIL',
            'checks': {name: 'PASS' if result else 'FAIL' for name, result in checks.items()},
            'production_authorized': False,
            'remaining': ['business_acceptance', 'external_backup_restore', 'external_alert_delivery', 'security_review', 'human_release_approval']}


if __name__ == '__main__':
    report = inspect()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report['technical_status'] == 'PASS' else 1)
