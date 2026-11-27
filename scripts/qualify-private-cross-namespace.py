"""CI-only cross-namespace qualification using synthetic keys and a disposable container."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_authorization as auth
import prod_private_runtime_contract as contract
import prod_private_runtime_replay as replay
import prod_private_handoff_transport as transport
import prod_private_peer_binding as binding

CLIENT = """
import base64,json,os,socket,urllib.request
from prod_private_qualification_entrypoint import prepare
with socket.socket(socket.AF_UNIX) as sock:
    sock.connect('/qualification/channel.sock')
    config=json.loads(os.environ['QUALIFICATION_CONFIG'])
    http=prepare(sock,expected_uid=config['uid'],envelope=config['envelope'],
        public=base64.b64decode(config['public']),authority_pin=config['pin'],
        expected=config['expected'])
    try:
        import threading
        t=threading.Thread(target=http.serve_forever)
        t.start()
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(http.server_port)+'/api/ready',timeout=3) as response:
                assert json.load(response)['qualification_only'] is True
        finally:
            http.shutdown()
            t.join()
    finally:
        http.server_close()
"""

def docker(*args):
    return subprocess.check_output(['/usr/bin/docker','--host','unix:///var/run/docker.sock',*args],text=True,timeout=30).strip()

def main():
    if len(sys.argv)!=2 or sys.argv[1]!='dsig-ci':
        raise ValueError('CI image required')
    name='dsig-cross-qualification-'+secrets.token_hex(8)
    image=docker('image','inspect','--format','{{.Id}}','dsig-ci')
    # Container ID is learned after creation; the child receives public synthetic
    # configuration through a read-only shared file, never the signing key.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        shared=root/'channel'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        ledger=root/'ledger.sqlite3'
        replay.initialize(ledger)
        listener=socket.socket(socket.AF_UNIX)
        try:
            listener.bind(str(shared/'channel.sock'))
            (shared/'channel.sock').chmod(0o666)
            listener.listen(1)
            listener.settimeout(30)
            code=CLIENT.replace("config=json.loads(os.environ['QUALIFICATION_CONFIG'])","config=json.load(open('/qualification/config.json'))")
            cid=docker('create','--name',name,'--network','none','--read-only',
                '--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','10001:10001',
                '--memory','512m','--pids-limit','128','--no-healthcheck',
                '--mount','type=bind,src='+str(shared)+',dst=/qualification,readonly',
                '-e','DSIG_ENV=DEV',image,'python','-c',code)
            key=Ed25519PrivateKey.generate()
            public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
            pin=hashlib.sha256(public).hexdigest()
            expected={k:('sha256:'+'a'*64 if k in ('image_id','image_digest') else 'a'*(40 if k=='commit' else 64)) for k in contract.PATTERNS}
            expected.update(container_id=cid,image_id=image)
            now=datetime.now(timezone.utc)
            payload=dict(expected,schema=2,purpose=contract.PURPOSE,scope=contract.SCOPE,
                nonce=secrets.token_hex(32),issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                expires_at=(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
            envelope=dict(payload=payload,signature=base64.b64encode(key.sign(auth.canonical(payload))).decode())
            config=shared/'config.json'
            config.write_bytes(auth.canonical(dict(uid=os.getuid(),envelope=envelope,
                public=base64.b64encode(public).decode(),pin=pin,expected=expected)))
            config.chmod(0o644)
            docker('start',cid)
            conn,_=listener.accept()
            with conn:
                if binding.inspect(conn,container_id=cid,image_id=image)['status']!='PASS':
                    raise RuntimeError('Docker peer binding failed')
                report=transport.host_exchange(conn,expected_uid=10001,ledger_path=ledger,
                    envelope=envelope,signing_key=key,authority_pin=pin,expected=expected)
                if report['status']!='PASS' or not report['nonce_consumed']:
                    raise RuntimeError('handoff failed')
            if docker('wait',cid)!='0':
                raise RuntimeError('isolated HTTP qualification failed')
            print('PASS: cross-namespace qualification only')
        finally:
            listener.close()
            subprocess.run(['/usr/bin/docker','--host','unix:///var/run/docker.sock','rm','-f',name],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

if __name__=='__main__':
    main()
