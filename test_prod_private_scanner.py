import os
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import prod_private_scanner as scanner

class ScannerTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=str(Path(temp.name)/'scanner.sock')
        p=patch.object(scanner,'SOCKET',self.path)
        p.start()
        self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'DSIG_ENV':'PROD','DSIG_CLAMD_SOCKET':self.path})
        p.start()
        self.addCleanup(p.stop)

    def run_server(self,responses):
        received=[]
        errors=[]
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        listener.bind(self.path)
        listener.listen(2)
        listener.settimeout(3)
        def worker():
            try:
                with listener:
                    for response in responses:
                        conn,_=listener.accept()
                        with conn:
                            conn.settimeout(3)
                            def read(n):
                                data=b''
                                while len(data)<n:
                                    part=conn.recv(n-len(data))
                                    if not part:
                                        raise EOFError()
                                    data+=part
                                return data
                            if read(10)!=b'zINSTREAM\0':
                                raise ValueError('unexpected command')
                            payload=b''
                            while True:
                                size=struct.unpack('!I',read(4))[0]
                                if not size:
                                    break
                                payload+=read(size)
                            received.append(payload)
                            conn.sendall(response)
            except Exception as exc:
                errors.append(exc)
        thread=threading.Thread(target=worker,daemon=True)
        thread.start()
        result=scanner.inspect()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        return result,received

    def test_roundtrip(self):
        result,received=self.run_server([b'stream: OK\0',b'stream: Eicar FOUND\0'])
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(received[1],scanner.EICAR)
        self.assertFalse(result['startup_authorized'])

    def test_false_negative(self):
        result,_=self.run_server([b'stream: OK\0',b'stream: OK\0'])
        self.assertEqual(result['status'],'FAIL')

    def test_unavailable_response(self):
        result,_=self.run_server([b'stream: ERROR\0'])
        self.assertEqual(result['status'],'FAIL')

    def test_missing_socket(self):
        self.assertEqual(scanner.inspect()['status'],'FAIL')

    def test_wrong_environment(self):
        with patch.dict(os.environ,{'DSIG_ENV':'REC'}):
            self.assertEqual(scanner.inspect()['checks']['configuration'],'FAIL')

if __name__=='__main__':
    unittest.main()
