import os
import socket
import tempfile
import unittest
from pathlib import Path

import prod_startup
import test_prod_review


@unittest.skipIf(os.getuid() == 0 or os.getgid() == 0, 'non-root operator required')
class StartupPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.data=root/'data'
        self.data.mkdir(mode=0o700)
        self.scanner=root/'scanner.sock'
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.bind(str(self.scanner))
        self.fixture=test_prod_review.CombinedReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        self.args=dict(env=f.compose['services']['app']['environment'],
                       rec=f.rec,candidate=f.candidate,data_dir=self.data,
                       scanner_socket=self.scanner,expected_uid=os.getuid(),expected_gid=os.getgid())

    def inspect(self,**overrides):
        r=prod_startup.inspect(**dict(self.args,**overrides))
        self.assertFalse(r['production_authorized'])
        self.assertFalse(r['database_initialized'])
        return r

    def test_empty_private_directory(self):
        self.assertEqual(self.inspect()['status'],'PASS')
        self.assertEqual(list(self.data.iterdir()),[])

    def test_existing_data(self):
        for name in ('requests.sqlite3','requests.sqlite3-wal','hidden','demo.csv'):
            p=self.data/name
            p.write_text('synthetic')
            self.assertEqual(self.inspect()['checks']['empty_data_directory'],'FAIL')
            self.assertEqual(p.read_text(),'synthetic')
            p.unlink()

    def test_unsafe_permissions(self):
        self.data.chmod(0o755)
        self.assertEqual(self.inspect()['status'],'FAIL')

    def test_symlink_directory(self):
        link=self.data.with_name('link')
        link.symlink_to(self.data,target_is_directory=True)
        self.assertEqual(self.inspect(data_dir=link)['status'],'FAIL')

    def test_wrong_identity(self):
        self.assertEqual(self.inspect(expected_uid=os.getuid()+1)['status'],'FAIL')

    def test_invalid_scanner(self):
        file=self.data.with_name('regular')
        file.touch()
        self.assertEqual(self.inspect(scanner_socket=file)['checks']['scanner_socket'],'FAIL')

    def test_wrong_mode(self):
        env=dict(self.args['env'],DSIG_ENV='REC')
        self.assertEqual(self.inspect(env=env)['checks']['configuration'],'FAIL')
