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
import base64,json,os,socket,urllib.request,urllib.error
from prod_private_business_qualification import run
restart_state={}
def exercise(port,rows):
    import authentication as auth
    import secrets
    base='http://127.0.0.1:'+str(port)
    common={'Host':'qualification.invalid','Origin':'https://qualification.invalid',
        'Content-Type':'application/json','X-DSIG-Session':'cookie'}
    def call(route,expected,session=None,data=None):
        headers=dict(common)
        if session:
            headers.update(Authorization='Bearer session',Cookie=session)
        req=urllib.request.Request(base+route,headers=headers,
            data=None if data is None else json.dumps(data).encode())
        try:
            response=urllib.request.urlopen(req,timeout=15)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            assert response.code in ((expected,) if isinstance(expected,int) else expected),(route,response.code)
            return json.load(response),response.headers.get('Set-Cookie','')
    assert call('/api/ready',200)[0]['status']=='ready'
    call('/api/admin/requests',401)
    for row in rows:
        auth.ATTEMPTS.clear()
        credentials=dict(username=row['username'],password=secrets.token_urlsafe(32))
        call('/api/auth/activate',200,data=dict(credentials,key=row['activation_key']))
        body,cookie=call('/api/auth/login',200,data=credentials)
        assert 'token' not in body and 'Secure' in cookie and 'HttpOnly' in cookie
        session=cookie.split(';',1)[0]
        call('/api/admin/requests',(401,403),session)
        setup,_=call('/api/auth/mfa-setup',200,session,{'password':credentials['password']})
        confirmation,_=call('/api/auth/mfa-confirm',200,session,
            {'code':auth.totp(setup['secret'],int(auth.time.time())//30)})
        call('/api/admin/requests',(401,403),session)
        call('/api/auth/login',401,data=credentials)
        auth.ATTEMPTS.clear()
        otp=confirmation['recovery_codes'][0]
        restart_state['credentials']=credentials
        restart_state['otp']=confirmation['recovery_codes'][1]
        body,cookie=call('/api/auth/login',200,data=dict(credentials,otp=otp))
        assert body['mfa_enabled'] and 'token' not in body
        session=cookie.split(';',1)[0]
        for route in ('/api/admin/requests','/api/admin/crm/organizations','/api/admin/quotes','/api/admin/billing','/api/admin/direction'):
            call(route,200,session)
        call('/api/auth/login',401,data=dict(credentials,otp=otp))
        call('/api/auth/logout',200,session,{})
        call('/api/admin/requests',(401,403),session)
    payload=dict(nom='Qualification',org='Synthetic',email='qa@example.invalid',
        besoin='Demande de démonstration',solution='MineFleet360',message='Qualification isolée',
        consent=True,website='')
    created,_=call('/api/requests',201,data=payload)
    assert created['id']
    restart_state['id']=created['id']

def restart_exercise(port):
    import authentication as auth
    auth.ATTEMPTS.clear()
    base='http://127.0.0.1:'+str(port)
    headers={'Host':'qualification.invalid','Origin':'https://qualification.invalid',
        'Content-Type':'application/json','X-DSIG-Session':'cookie'}
    credentials=restart_state['credentials']
    req=urllib.request.Request(base+'/api/auth/login',headers=headers,
        data=json.dumps(dict(credentials,otp=restart_state['otp'])).encode())
    with urllib.request.urlopen(req,timeout=15) as response:
        assert json.load(response)['mfa_enabled']
        headers.update(Authorization='Bearer session',Cookie=response.headers['Set-Cookie'].split(';',1)[0])
    req=urllib.request.Request(base+'/api/admin/requests',headers=headers)
    with urllib.request.urlopen(req,timeout=15) as response:
        body=json.load(response)
        assert restart_state['id'] in json.dumps(body)
    req=urllib.request.Request(base+'/api/auth/logout',headers=headers,data=b'{}')
    with urllib.request.urlopen(req,timeout=15) as response:
        assert response.code==200
with socket.socket(socket.AF_UNIX) as sock:
    sock.connect('/qualification/channel.sock')
    config=json.load(open('/qualification/config.json'))
    result=run(sock,expected_uid=config['uid'],envelope=config['envelope'],
        public=base64.b64decode(config['public']),authority_pin=config['pin'],
        expected=config['expected'],exercise=exercise,restart_exercise=restart_exercise)
    assert result['qualification_only'] and not result['production_authorized']
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
            code=CLIENT
            cid=docker('create','--name',name,'--network','none','--read-only',
                '--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','10001:10001',
                '--memory','512m','--pids-limit','128','--no-healthcheck',
                '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777',
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
            exit_code=docker('wait',cid)
            if exit_code!='0':
                # CI-only disposable container: report bounded synthetic diagnostics
                # before cleanup, never inspect its environment or configuration.
                diagnostics=subprocess.run(['/usr/bin/docker','--host','unix:///var/run/docker.sock',
                    'logs','--tail','80',cid],capture_output=True,text=True,timeout=15)
                print('Synthetic qualification container exit:',exit_code,file=sys.stderr)
                print((diagnostics.stdout+diagnostics.stderr)[-12000:],file=sys.stderr)
                raise RuntimeError('isolated HTTP qualification failed')
            print('PASS: cross-namespace qualification only')
        finally:
            listener.close()
            subprocess.run(['/usr/bin/docker','--host','unix:///var/run/docker.sock','rm','-f',name],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

if __name__=='__main__':
    main()
