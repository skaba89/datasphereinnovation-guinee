import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import prod_private_http_transport as transport

class TransportTests(unittest.TestCase):
    def test_actual_http_transport(self):
        with patch.dict(os.environ,{'DSIG_ENV':'DEV'}):
            server=transport.create_isolated()
        self.addCleanup(server.server_close)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join,5)
        self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        for route in ('/api/health','/api/ready'):
            with urllib.request.urlopen(base+route,timeout=3) as response:
                body=json.load(response)
                self.assertTrue(body['qualification_only'])
                self.assertFalse(body['production_authorized'])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base+'/api/admin/accounts',timeout=3)
        self.assertEqual(exc.exception.code,404)

    def test_prod_and_rec_refused(self):
        for mode in ('PROD','REC',''):
            with patch.dict(os.environ,{'DSIG_ENV':mode}):
                with self.assertRaises(ValueError):
                    transport.create_isolated()

if __name__=='__main__':
    unittest.main()
