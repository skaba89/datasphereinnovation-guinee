import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from pra_caddy_stage import check_fragment, check_adapted, stage

HOST = "rec-dsig.example.org"
IMAGE = "sha256:" + "a"*64
FRAGMENT = (HOST + " {\n    reverse_proxy dsig-rec-dsig-1:8080\n}\n").encode()


def adapted():
    return {"apps": {"http": {"servers": {"srv0": {"routes": [
        {"match": [{"host": [HOST]}], "handle": [
            {"handler": "reverse_proxy", "upstreams": [{"dial": "dsig-rec-dsig-1:8080"}]}
        ]}
    ]}}}}}


class PraCaddyStageTests(unittest.TestCase):
    def test_fragment(self):
        check_fragment(FRAGMENT, HOST)

    def test_refuse_extra_site(self):
        with self.assertRaises(ValueError):
            check_fragment(FRAGMENT + b"other.example.org {\n}\n", HOST)

    def test_refuse_import(self):
        with self.assertRaises(ValueError):
            check_fragment(FRAGMENT.replace(b"reverse_proxy", b"import"), HOST)

    def test_refuse_env(self):
        with self.assertRaises(ValueError):
            check_fragment(FRAGMENT.replace(b"dsig-rec-dsig-1", b"{$UPSTREAM}"), HOST)

    def test_refuse_tls(self):
        with self.assertRaises(ValueError):
            check_fragment(FRAGMENT.replace(b"reverse_proxy", b"tls"), HOST)

    def test_refuse_prod(self):
        with self.assertRaises(ValueError):
            check_fragment(b"dsig.example.org {\n}\n", "dsig.example.org")

    def test_adapted(self):
        check_adapted(adapted(), HOST)

    def test_refuse_other_upstream(self):
        config = adapted()
        config["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["upstreams"][0]["dial"] = "other:8080"
        with self.assertRaises(ValueError):
            check_adapted(config, HOST)

    @patch("pra_caddy_stage.adapt", return_value=adapted())
    def test_stage(self, adapt):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/"src"
            parent = Path(tmp)/"out"
            source.mkdir(mode=0o700)
            parent.mkdir(mode=0o700)
            files = {"MANIFEST.txt": b"environment=REC\n", "dsig-rec.caddy": FRAGMENT}
            marker = "".join(hashlib.sha256(data).hexdigest()+"  "+name+"\n" for name,data in files.items())
            files["SHA256SUMS"] = marker.encode()
            for name,data in files.items():
                p = source/name
                p.write_bytes(data)
                p.chmod(0o600)
            report = stage(source, parent, HOST, IMAGE)
            self.assertFalse(report["activated"])
            self.assertFalse(report["tls_issued"])
            self.assertEqual((parent/report["stage"]/"dsig-rec.caddy").read_bytes(), FRAGMENT)
            adapt.assert_called_once_with(FRAGMENT, IMAGE)
