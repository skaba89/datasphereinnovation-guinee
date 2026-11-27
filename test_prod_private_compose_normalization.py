import copy
import unittest
from test_prod_private_launch_topology import proposed, IMAGE
import prod_private_compose_normalization as normalization
import prod_private_launch_topology as topology


class ComposeNormalizationTests(unittest.TestCase):
    def test_missing_false_only(self):
        source = proposed()
        for bind in ({}, None, {'create_host_path': False}):
            rendered = copy.deepcopy(source)
            mount = rendered['services']['app']['volumes'][-1]
            if bind is None:
                del mount['bind']
            else:
                mount['bind'] = bind
            self.assertEqual(normalization.reconcile(source, rendered, IMAGE), source)

    def test_unsafe_drift(self):
        source = proposed()
        for k, v in [('bind', {'create_host_path': True}), ('read_only', False),
                     ('source', '/tmp'), ('bind', {'propagation': 'shared'})]:
            rendered = copy.deepcopy(source)
            rendered['services']['app']['volumes'][-1][k] = v
            with self.assertRaises(ValueError):
                normalization.reconcile(source, rendered, IMAGE)
        rendered = copy.deepcopy(source)
        del rendered['services']['app']['volumes'][-1]['bind']
        with self.assertRaises(ValueError):
            normalization.reconcile(rendered, rendered, IMAGE)

    def test_engine_mount(self):
        mount = dict(Type='bind', Source=topology.HOST_CHANNEL,
                     Target=topology.CHANNEL, ReadOnly=True)
        hc = {'Mounts': [mount]}
        self.assertTrue(normalization.inspect_channel(hc))
        mount['BindOptions'] = {'CreateMountpoint': False, 'Propagation': 'rprivate'}
        self.assertTrue(normalization.inspect_channel(hc))
        mount['BindOptions']['CreateMountpoint'] = True
        self.assertFalse(normalization.inspect_channel(hc))
        mount['BindOptions']['CreateMountpoint'] = False
        hc['Binds'] = ['/tmp:/tmp']
        self.assertFalse(normalization.inspect_channel(hc))

    def test_observed_prod_volume_and_two_api_binds(self):
        hc = {'Binds': ['dsig-prod_prod-data:/app/data:rw'],
              'Mounts': [
                  dict(Type='bind', Source='/run/clamav',
                       Target='/run/dsig-clamav', ReadOnly=True, BindOptions={}),
                  dict(Type='bind', Source=topology.HOST_CHANNEL,
                       Target=topology.CHANNEL, ReadOnly=True, BindOptions={})]}
        self.assertTrue(normalization.inspect_channel(hc))
        for binds in [
            ['dsig-prod_prod-data:/app/data:ro'],
            ['other:/app/data:rw'],
            ['/var/run/docker.sock:/var/run/docker.sock:rw'],
            ['/run/dsig-prod-launch:/run/dsig-private-launch:ro'],
            ['dsig-prod_prod-data:/app/data:rw', '/:/host:rw'],
            ['dsig-prod_prod-data:/app/data:rw'] * 2,
        ]:
            with self.subTest(binds=binds):
                altered = copy.deepcopy(hc)
                altered['Binds'] = binds
                self.assertFalse(normalization.inspect_channel(altered))
        hc['Mounts'][1]['BindOptions']['CreateMountpoint'] = True
        self.assertFalse(normalization.inspect_channel(hc))
