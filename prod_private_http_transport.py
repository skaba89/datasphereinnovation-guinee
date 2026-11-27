"""Isolated transport qualification, never serves business routes in PROD."""
import os
import json
from http.server import BaseHTTPRequestHandler
from server import BoundedHTTPServer

class QualificationHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/api/health','/api/ready'):
            self.send_error(404)
            return
        body=json.dumps({'status':'ok','qualification_only':True,
                         'production_authorized':False}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):
        pass

def create_isolated():
    """Loopback only, ephemeral port, no database or business handler."""
    if os.environ.get('DSIG_ENV')!='DEV':
        raise ValueError('isolated DEV transport only')
    return BoundedHTTPServer(('127.0.0.1',0),QualificationHandler)
