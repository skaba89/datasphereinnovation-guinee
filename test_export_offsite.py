import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('offsite', Path(__file__).parent / 'scripts' / 'export-offsite.py')
offsite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offsite)


class OffsiteTests(unittest.TestCase):
    def test_unmounted_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir(mode=0o700)
            mount = root / 'mount'
            mount.mkdir(mode=0o700)
            target = mount / 'dsig-rec'
            target.mkdir(mode=0o700)
            with self.assertRaises(ValueError):
                offsite.export(source, mount, target)
            self.assertEqual(list(target.iterdir()), [])

    def test_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'archive'
            path.write_bytes(b'abc')
            self.assertEqual(offsite.digest(path), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
