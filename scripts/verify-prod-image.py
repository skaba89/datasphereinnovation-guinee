"""Inspect a locally available immutable image in a disposable sandbox; no PROD startup."""
import argparse
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rec_release_manifest', ROOT / 'verify-rec-release.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)

SCAN = """
import hashlib,json,pathlib
root=pathlib.Path('/app')
dist=root/'dist'
if dist.is_symlink() or not dist.is_dir():
    raise RuntimeError('invalid dist')
paths=list(root.glob('*.py'))+[root/'requirements.txt']
for p in dist.rglob('*'):
    if p.is_symlink(): raise RuntimeError('symlink')
    if p.is_file(): paths.append(p)
    elif not p.is_dir(): raise RuntimeError('invalid file')
if any(p.is_symlink() or not p.is_file() for p in paths):
    raise RuntimeError('invalid file')
print(json.dumps({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
"""


def invoke(args):
    return subprocess.run(args, cwd=ROOT.parent, check=True, capture_output=True, timeout=120).stdout


def verify(commit, image, *, ci_local=False, qualification_local=False):
    checks=dict.fromkeys(('source_manifest','immutable_reference','image_identity','content_matches'), 'FAIL')
    count=0
    try:
        if not re.fullmatch(r'[0-9a-f]{40}',commit):
            raise ValueError('invalid commit')
        if ci_local and qualification_local:
            raise ValueError('conflicting local modes')
        if qualification_local:
            if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):
                raise ValueError('qualification requires immutable local image ID')
        elif ci_local:
            if image != 'dsig-ci':
                raise ValueError('invalid CI image')
        elif not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}',image):
            raise ValueError('invalid digest reference')
        expected=manifest.source_manifest(commit)
        checks['source_manifest']='PASS'
        count=len(expected)
        info=json.loads(invoke(['docker','image','inspect',image]))
        if not isinstance(info,list) or len(info)!=1:
            raise ValueError('invalid image metadata')
        data=info[0]
        image_id=data['Id']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',image_id):
            raise ValueError('invalid image ID')
        if qualification_local:
            if image_id != image:
                raise ValueError('qualification image ID mismatch')
            checks['immutable_reference']='PASS'
        elif not ci_local:
            if image not in (data.get('RepoDigests') or []):
                raise ValueError('digest not found')
            checks['immutable_reference']='PASS'
        else:
            checks['immutable_reference']='NOT_APPLICABLE_CI'
        if data.get('Config',{}).get('User') != '10001:10001' or data.get('Config',{}).get('Volumes'):
            raise ValueError('unexpected image configuration')
        checks['image_identity']='PASS'
        actual=json.loads(invoke(['docker','run','--rm','--pull=never','--network=none',
            '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true',
            '--user=10001:10001','--memory=256m','--cpus=1','--pids-limit=32',
            '--entrypoint=python',image_id,'-I','-c',SCAN]))
        checks['content_matches']='PASS' if actual==expected else 'FAIL'
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,KeyError,AttributeError):
        pass
    ok=all(v=='PASS' or (ci_local and k=='immutable_reference' and v=='NOT_APPLICABLE_CI')
           for k,v in checks.items())
    return {'status':'PASS' if ok else 'FAIL','checks':checks,'file_count':count,
            'ci_local':ci_local,'qualification_local':qualification_local,'production_authorized':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commit')
    parser.add_argument('image')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--ci-local',action='store_true')
    modes.add_argument('--qualification-local',action='store_true')
    args=parser.parse_args()
    report=verify(args.commit,args.image,ci_local=args.ci_local,qualification_local=args.qualification_local)
    print(json.dumps(report))
    raise SystemExit(int(report['status']!='PASS'))
