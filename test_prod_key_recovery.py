import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import prod_key_recovery as p


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        # Reduce KDF cost only in unit tests; production remains fixed at 2**17.
        cost=patch.object(p,'N',2**12)
        cost.start()
        self.addCleanup(cost.stop)
        self.keys=p.generate()
        self.password=b'unit-test-only-recovery-passphrase'
        self.forbidden={'a'*64,'b'*64}

    def pack(self):
        return p.pack(self.keys,passphrase=self.password,forbidden=self.forbidden)

    def restore(self,blob,pins,password=None):
        return p.unpack(blob,passphrase=password or self.password,
                        forbidden=self.forbidden,expected_pins=pins)

    def test_roundtrip(self):
        blob,pins=self.pack()
        self.assertEqual(self.restore(blob,pins),self.keys)
        self.assertNotEqual(blob,self.pack()[0])

    def test_wrong_passphrase(self):
        blob,pins=self.pack()
        with self.assertRaises(ValueError):self.restore(blob,pins,b'another-long-test-passphrase')

    def test_tampered_ciphertext(self):
        blob,pins=self.pack()
        with self.assertRaises(ValueError):self.restore(blob[:-1]+bytes([blob[-1]^1]),pins)

    def test_wrong_pin(self):
        blob,pins=self.pack()
        pins['backup_id']='c'*64
        with self.assertRaises(ValueError):self.restore(blob,pins)

    def test_reused_key(self):
        self.keys['mfa']=self.keys['backup']
        with self.assertRaises(ValueError):self.pack()

    def test_reference_collision(self):
        import hashlib
        self.forbidden.add(hashlib.sha256(p.raw_fernet(self.keys['backup'])).hexdigest())
        with self.assertRaises(ValueError):self.pack()

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'kit.enc'
            args=dict(passphrase=self.password,forbidden=self.forbidden)
            result=p.write_kit(path,self.keys,**args)
            old=path.read_bytes()
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertFalse(result['external_recovery_verified'])
            self.assertFalse(result['production_authorized'])
            with self.assertRaises(FileExistsError):p.write_kit(path,self.keys,**args)
            self.assertEqual(path.read_bytes(),old)

    def test_short_passphrase(self):
        with self.assertRaises(ValueError):p.pack(self.keys,passphrase=b'short',forbidden=self.forbidden)
