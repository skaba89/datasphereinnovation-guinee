import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('image_verifier',Path(__file__).parent/'verify-prod-image.py')
# The application Docker smoke suite copies root tests but not scripts.
# Test the verifier in the repository CI checkout only.
if not Path(spec.origin).is_file():
    raise unittest.SkipTest('repository verifier scripts are not packaged in runtime image')
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class QualificationImageTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40
        self.image='sha256:'+'b'*64
        self.files={'server.py':'digest'}
        self.info=[dict(Id=self.image,Config=dict(User='10001:10001'),RepoDigests=[])]
        self.manifest=patch.object(p.manifest,'source_manifest',return_value=self.files)
        self.manifest.start()
        self.addCleanup(self.manifest.stop)

    def verify(self,image=None,**kwargs):
        with patch.object(p,'invoke',side_effect=[json.dumps(self.info).encode(),json.dumps(self.files).encode()]):
            return p.verify(self.sha,image or self.image,**kwargs)

    def test_pinned_qualification(self):
        result=self.verify(qualification_local=True)
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['production_authorized'])

    def test_wrong_id(self):
        self.info[0]['Id']='sha256:'+'c'*64
        self.assertEqual(self.verify(qualification_local=True)['status'],'FAIL')

    def test_mutable_tag_rejected(self):
        self.assertEqual(self.verify('dsig-qualification:latest',qualification_local=True)['status'],'FAIL')

    def test_production_requires_registry_digest(self):
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_ci_tag_still_restricted(self):
        self.assertEqual(self.verify('dsig-qualification:latest',ci_local=True)['status'],'FAIL')

    def test_conflicting_modes(self):
        self.assertEqual(self.verify(ci_local=True,qualification_local=True)['status'],'FAIL')
