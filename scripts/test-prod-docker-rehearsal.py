"""Explicit Docker qualification, isolated namespace, no business data or B2."""
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Running from scripts/ must resolve repository modules.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prod_backup_acquisition as acquisition
import prod_backup_rehearsal as rehearsal
import operations
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

DOCKER=['/usr/bin/docker','--host','unix:///var/run/docker.sock']
ENV={'PATH':'/usr/bin:/bin','HOME':str(Path.home()),'DOCKER_CONFIG':'/dev/null'}
INIT="""import os,time,server
from contextlib import closing
os.chmod('/app/data',0o700)
with closing(server.connect()) as db:
    db.execute('CREATE TABLE qualification_probe (value TEXT NOT NULL)')
    db.execute("INSERT INTO qualification_probe VALUES ('DSIG-V230-SYNTHETIC')")
    db.commit()
time.sleep(600)
"""
EXTRACT="""import sqlite3,sys
from contextlib import closing
with closing(sqlite3.connect('file:/app/data/requests.sqlite3?mode=ro',uri=True)) as db:
    if db.execute("SELECT value FROM qualification_probe").fetchone()!=('DSIG-V230-SYNTHETIC',):
        raise ValueError('unexpected qualification data')
    with closing(sqlite3.connect('/tmp/snapshot.sqlite3')) as target:
        db.backup(target)
with open('/tmp/snapshot.sqlite3','rb') as f:
    sys.stdout.buffer.write(f.read(67108865))
"""


def docker(*args,timeout=30):
    try:
        return subprocess.run(DOCKER+list(args),env=ENV,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              check=True,timeout=timeout).stdout
    except (OSError,subprocess.SubprocessError):
        raise ValueError('Docker qualification command failed') from None


def main(image):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):
        raise ValueError('provide a prebuilt local image ID')
    if docker('image','inspect','--format','{{.Id}}',image).decode().strip()!=image:
        raise ValueError('image mismatch')
    if docker('info','--format','{{.DockerRootDir}}').decode().strip()!='/var/lib/docker':
        raise ValueError('unsupported Docker data root')
    run_id=secrets.token_hex(8)
    project='dsig-qualification-'+run_id
    volume=project+'_prod-data'
    name=project+'-app'
    if docker('volume','ls','--format','{{.Name}}').decode().splitlines().count(volume):
        raise ValueError('volume collision')
    if docker('container','ls','--all','--format','{{.Names}}').decode().splitlines().count(name):
        raise ValueError('container collision')
    volume_created=False
    cid=None
    try:
        docker('volume','create','--label','com.docker.compose.project='+project,
               '--label','com.docker.compose.volume=prod-data',volume)
        volume_created=True
        cid=docker('run','-d','--pull=never','--name',name,'--network','none',
                   '--label','com.docker.compose.project='+project,'--label','com.docker.compose.service=app',
                   '--user','10001:10001','--read-only','--cap-drop','ALL',
                   '--security-opt','no-new-privileges:true','--memory','256m','--cpus','0.5',
                   '--pids-limit','64','--no-healthcheck','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=96m',
                   '--mount','type=volume,source='+volume+',target=/app/data',
                   '-e','DSIG_ENV=DEV','--entrypoint','python',image,'-c',INIT).decode().strip()
        if not re.fullmatch(r'[0-9a-f]{64}',cid):
            raise ValueError('invalid created container identity')
        import time
        for _ in range(30):
            try:
                data=docker('exec',cid,'python','-c',EXTRACT)
                break
            except ValueError:
                time.sleep(1)
        else:
            raise ValueError('synthetic source not ready')
        def check():
            return acquisition.acquire_qualification(expected_container_id=cid,
                expected_image_id=image,run_id=run_id)
        if check()['status']!='PASS':
            raise ValueError('qualification acquisition rejected')
        if acquisition.acquire(expected_container_id=cid,expected_image_id=image)['status']!='FAIL':
            raise ValueError('qualification accepted as production')
        if not 0<len(data)<=operations.MAX_DB_BYTES:
            raise ValueError('invalid synthetic snapshot')
        with tempfile.TemporaryDirectory(prefix='dsig-v230-') as tmp:
            root=Path(tmp)
            src=root/'source'
            keys=root/'keys'
            cycle=root/'cycle'
            for p in (src,keys,cycle,cycle/'archives',cycle/'replica',cycle/'state'):
                p.mkdir(mode=0o700)
            db=src/'source.sqlite3'
            operations.write_new(db,data)
            operations.verify(db)
            key=Fernet.generate_key()
            signer=Ed25519PrivateKey.generate()
            backup=keys/'backup.key'
            signing=keys/'signing.key'
            operations.write_new(backup,key)
            operations.write_new(signing,signer.private_bytes(serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,serialization.NoEncryption()))
            pin=hashlib.sha256(signer.public_key().public_bytes(serialization.Encoding.Raw,
                serialization.PublicFormat.Raw)).hexdigest()
            archive=datetime.now(timezone.utc).strftime('dsig-prod-%Y%m%dT%H%M%SZ.dsigbak')
            args=dict(active=db,root=cycle,name=archive,backup_path=backup,signer_path=signing,
                      pinned_signer_id=pin,forbidden_backup_ids={secrets.token_hex(32),secrets.token_hex(32)},
                      source_check=check)
            first=rehearsal.run_rehearsal(**args)
            second=rehearsal.run_rehearsal(**args)
            if not first['created'] or second['created'] or first['sha256']!=second['sha256']:
                raise ValueError('rehearsal not idempotent')
            print(json.dumps(dict(status='PASS',run_id=run_id,qualification_only=True,
                                  docker_source_verified=True,local_replica_verified=True,
                                  remote_verified=False,business_provenance_verified=False,
                                  production_authorized=False),sort_keys=True))
    finally:
        if cid and re.fullmatch(r'[0-9a-f]{64}',cid):
            docker('container','rm','-f',cid)
        if volume_created:
            docker('volume','rm',volume)


if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--qualification-image-id':
        raise SystemExit('usage: test-prod-docker-rehearsal.py --qualification-image-id sha256:...')
    try:
        main(sys.argv[2])
    except (ValueError,OSError):
        raise SystemExit('FAIL: isolated Docker qualification failed')
