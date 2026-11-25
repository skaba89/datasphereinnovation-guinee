import hashlib
import io
import tarfile
import unittest

from scripts.pra_verify import verify_tar


def kit(extra=(), checksum=None):
    data = b"environment=REC\n"
    marker = (hashlib.sha256(data).hexdigest() + "  ./MANIFEST.txt\n").encode()
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, content in [("./MANIFEST.txt", data), ("./SHA256SUMS", marker if checksum is None else checksum), *extra]:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    out.seek(0)
    return out


class PraVerificationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(verify_tar(kit()), 1)

    def test_unlisted_file(self):
        with self.assertRaises(ValueError):
            verify_tar(kit([("extra", b"x")]))

    def test_traversal(self):
        with self.assertRaises(ValueError):
            verify_tar(kit([("../outside", b"x")]))

    def test_absolute(self):
        with self.assertRaises(ValueError):
            verify_tar(kit([("/outside", b"x")]))

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            verify_tar(kit([("MANIFEST.txt", b"x")]))

    def test_bad_checksum(self):
        with self.assertRaises(ValueError):
            verify_tar(kit(checksum=b"0" * 64 + b"  MANIFEST.txt\n"))

    def test_link(self):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as tar:
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            tar.addfile(member)
        out.seek(0)
        with self.assertRaises(ValueError):
            verify_tar(out)
