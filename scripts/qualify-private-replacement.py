"""CI-only Docker replacement qualification; no production volumes."""
import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_authorization as auth
import prod_private_runtime_contract as contract
import prod_private_runtime_replay as replay
import prod_private_peer_binding as binding
import prod_private_handoff_transport as transport

CLIENT="""
import base64,json,socket
from prod_private_handoff_transport import recipient_exchange
from prod_private_replacement_qualification import exercise
with open('/qualification/config.json') as stream:
    c=json.load(stream)
with socket.socket(socket.AF_UNIX) as sock:
    sock.connect('/qualification/channel.sock')
    result=recipient_exchange(sock,expected_uid=c['uid'],envelope=c['envelope'],
        public=base64.b64decode(c['public']),authority_pin=c['pin'],expected=c['expected'])
    if result['status']!='PASS':
        raise SystemExit('handoff refused')
assert exercise(c['phase'],c['marker'])['status']=='PASS'
"""

def docker(*args):
    return subprocess.check_output(['/usr/bin/docker','--host','unix:///var/run/docker.sock',*args],
        text=True,timeout=60).strip()

def main():
    if sys.argv[1:]!=['dsig-ci']:
        raise ValueError('local CI image required')
    image=docker('image','inspect','--format','{{.Id}}','dsig-ci')
    prefix='dsig-replacement-ci-'+secrets.token_hex(8)
    vol=prefix+'-data'
    marker=secrets.token_hex(16)
    key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    pin=hashlib.sha256(public).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        shared=root/'channel'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        ledger=root/'ledger.sqlite3'
        replay.initialize(ledger)
        listener=socket.socket(socket.AF_UNIX)
        try:
            docker('volume','create','--label','dsig.qualification=ci',vol)
            # Prepare only the freshly generated named qualification volume.
            docker('run','--rm','--network','none','--user','0:0','--mount',
                'type=volume,src='+vol+',dst=/qualification-data',image,'python','-c',
                "import os; p='/qualification-data'; assert not os.listdir(p); os.chown(p,10001,10001); os.chmod(p,0o700)")
            listener.bind(str(shared/'channel.sock'))
            (shared/'channel.sock').chmod(0o666)
            listener.listen(1)
            listener.settimeout(30)
            previous=None
            for phase in ('create','replace'):
                name=prefix+'-'+phase
                cid=docker('create','--name',name,'--network','none','--read-only',
                    '--cap-drop','ALL','--security-opt','no-new-privileges:true',
                    '--user','10001:10001','--memory','512m','--pids-limit','128',
                    '--no-healthcheck','--mount','type=volume,src='+vol+',dst=/qualification-data',
                    '--mount','type=bind,src='+str(shared)+',dst=/qualification,readonly',
                    '-e','DSIG_ENV=DEV',image,'python','-c',CLIENT)
                expected={k:('sha256:'+'a'*64 if k in ('image_id','image_digest') else 'a'*(40 if k=='commit' else 64)) for k in contract.PATTERNS}
                expected.update(container_id=cid,image_id=image)
                if previous:
                    old,old_expected=previous
                    assert old_expected['container_id']!=cid
                    assert contract.verify(old,public,authority_pin=pin,expected=expected)['status']=='FAIL'
                    assert replay.consume(ledger,old,public,authority_pin=pin,expected=old_expected)['status']=='FAIL'
                now=datetime.now(timezone.utc)
                payload=dict(expected,schema=2,purpose=contract.PURPOSE,scope=contract.SCOPE,
                    nonce=secrets.token_hex(32),issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    expires_at=(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
                envelope=dict(payload=payload,signature=base64.b64encode(key.sign(auth.canonical(payload))).decode())
                config=shared/'config.json'
                config.write_bytes(auth.canonical(dict(uid=os.getuid(),envelope=envelope,public=base64.b64encode(public).decode(),
                    pin=pin,expected=expected,phase=phase,marker=marker)))
                config.chmod(0o644)
                docker('start',cid)
                conn,_=listener.accept()
                with conn:
                    assert binding.inspect(conn,container_id=cid,image_id=image)['status']=='PASS'
                    result=transport.host_exchange(conn,expected_uid=10001,ledger_path=ledger,
                        envelope=envelope,signing_key=key,authority_pin=pin,expected=expected)
                    assert result['status']=='PASS' and result['nonce_consumed']
                if docker('wait',cid)!='0':
                    raise RuntimeError('replacement phase failed: '+phase)
                docker('rm',cid)
                previous=envelope,expected
            print('PASS: isolated Docker volume replacement and fresh permits')
        finally:
            listener.close()
            for phase in ('create','replace'):
                subprocess.run(['/usr/bin/docker','--host','unix:///var/run/docker.sock','rm','-f',prefix+'-'+phase],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            docker('volume','rm',vol)

if __name__=='__main__':
    main()
