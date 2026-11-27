"""One-shot Unix socket handoff; transport qualification only, no startup."""
import json
import re
import socket
import struct
import time
import prod_authorization as auth
import prod_private_handoff_issuer as issuer

MAX_FRAME=16384
TIMEOUT=5

def peer(sock, uid):
    if sock.family!=socket.AF_UNIX or type(uid) is not int or uid<0:
        raise ValueError('invalid peer configuration')
    _,actual,_=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
    if actual!=uid:
        raise ValueError('unexpected peer uid')

def read_exact(sock,n,deadline):
    data=bytearray()
    while len(data)<n:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise TimeoutError()
        sock.settimeout(remaining)
        chunk=sock.recv(n-len(data))
        if not chunk:
            raise ValueError('truncated frame')
        data.extend(chunk)
    return bytes(data)

def receive(sock):
    deadline=time.monotonic()+TIMEOUT
    size=struct.unpack('!I',read_exact(sock,4,deadline))[0]
    if not 0<size<=MAX_FRAME:
        raise ValueError('invalid frame size')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key]=value
        return result
    return json.loads(read_exact(sock,size,deadline),object_pairs_hook=unique)

def send(sock,value):
    raw=auth.canonical(value)
    if not 0<len(raw)<=MAX_FRAME:
        raise ValueError('invalid frame size')
    sock.settimeout(TIMEOUT)
    sock.sendall(struct.pack('!I',len(raw))+raw)

def host_exchange(sock,*,expected_uid,ledger_path,envelope,signing_key,authority_pin,expected):
    result=dict(status='FAIL',nonce_consumed=False,startup_authorized=False,production_authorized=False)
    try:
        peer(sock,expected_uid)
        request=receive(sock)
        if not isinstance(request,dict) or set(request)!={'challenge'}:
            return result
        challenge=request['challenge']
        if not isinstance(challenge,str) or not re.fullmatch('[0-9a-f]{64}',challenge):
            return result
        issued=issuer.issue(ledger_path=ledger_path,envelope=envelope,signing_key=signing_key,
            authority_pin=authority_pin,expected=expected,challenge_value=challenge)
        result['nonce_consumed']=issued['nonce_consumed']
        if issued['status']!='PASS':
            return result
        send(sock,{'receipt':issued['receipt']})
        result['status']='PASS'
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        pass
    finally:
        sock.close()
    return result

def recipient_exchange(sock,*,expected_uid,envelope,public,authority_pin,expected):
    result=dict(status='FAIL',startup_authorized=False,production_authorized=False)
    try:
        peer(sock,expected_uid)
        recipient=issuer.Recipient()
        send(sock,{'challenge':recipient.challenge})
        response=receive(sock)
        if not isinstance(response,dict) or set(response)!={'receipt'}:
            return result
        return recipient.accept(response['receipt'],envelope,public,authority_pin=authority_pin,expected=expected)
    except (OSError,ValueError,TypeError,KeyError,RecursionError):
        return result
    finally:
        sock.close()
