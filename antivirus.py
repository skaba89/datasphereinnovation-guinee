"""Fail-closed ClamAV INSTREAM client over a private Unix socket."""
import os,re,socket,struct,time,threading

MAX_BYTES=1024*1024
TIMEOUT=15
SLOTS=threading.BoundedSemaphore(4)

class Unavailable(Exception):pass
class Infected(Exception):pass

def scan(data):
    path=os.environ.get('DSIG_CLAMD_SOCKET','')
    if not path or not os.path.isabs(path) or not 0<len(data)<=MAX_BYTES:raise Unavailable()
    if not SLOTS.acquire(blocking=False):raise Unavailable()
    try:
        deadline=time.monotonic()+TIMEOUT
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            def budget():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise Unavailable()
                sock.settimeout(remaining)
            budget();sock.connect(path)
            budget();sock.sendall(b'zINSTREAM\0')
            for i in range(0,len(data),65536):
                chunk=data[i:i+65536];budget();sock.sendall(struct.pack('!I',len(chunk))+chunk)
            budget();sock.sendall(b'\0'*4)
            response=b''
            while b'\0' not in response and len(response)<4096:
                budget();part=sock.recv(4096-len(response))
                if not part:break
                response+=part
            if response==b'stream: OK\0':return
            if re.fullmatch(rb'stream: [^\x00\r\n]+ FOUND\x00',response):raise Infected()
            raise Unavailable()
    except (OSError,ValueError):raise Unavailable() from None
    finally:SLOTS.release()
