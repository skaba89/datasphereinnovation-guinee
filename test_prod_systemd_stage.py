"""Staged units must not acquire a production execution path."""
import unittest
from configparser import ConfigParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent/'deploy/systemd/staged-prod'
TASKS={'backup':'01:15','b2':'02:05','backup-audit':'03:00'}


class StagedUnitsTests(unittest.TestCase):
    def read_unit(self,name):
        cfg=ConfigParser(interpolation=None,strict=True)
        cfg.optionxform=str
        with (ROOT/name).open() as handle:
            cfg.read_file(handle)
        return cfg

    def test_exact_units(self):
        self.assertEqual({p.name for p in ROOT.iterdir()},
                         {f'dsig-prod-{n}.{suffix}' for n in TASKS for suffix in ('service','timer')})

    def test_services_fail_closed(self):
        for name in TASKS:
            cfg=self.read_unit(f'dsig-prod-{name}.service')
            self.assertEqual(set(cfg.sections()),{'Unit','Service'})
            self.assertEqual(dict(cfg['Unit']).keys(),{'Description'})
            self.assertEqual(set(cfg['Service']),{'Type','User','WorkingDirectory','Environment','UMask',
                'NoNewPrivileges','PrivateTmp','ProtectSystem','ProtectHome','ExecStart','TimeoutStartSec',
                'StandardOutput','StandardError','SyslogIdentifier'})
            self.assertEqual(cfg['Service']['ExecStart'],'/usr/bin/false')
            self.assertEqual(cfg['Service']['User'],'ubuntu')
            self.assertEqual(cfg['Service']['UMask'],'0077')
            self.assertEqual(cfg['Service']['NoNewPrivileges'],'true')
            self.assertEqual(cfg['Service']['ProtectSystem'],'strict')
            self.assertEqual(cfg['Service']['ProtectHome'],'read-only')

    def test_schedule_not_enableable_by_install(self):
        for name,when in TASKS.items():
            cfg=self.read_unit(f'dsig-prod-{name}.timer')
            self.assertEqual(set(cfg.sections()),{'Unit','Timer'})
            self.assertEqual(set(cfg['Timer']),{'OnCalendar','Persistent','AccuracySec','Unit'})
            self.assertEqual(cfg['Timer']['OnCalendar'],f'*-*-* {when}:00 UTC')
            self.assertEqual(cfg['Timer']['Persistent'],'false')
            self.assertEqual(cfg['Timer']['Unit'],f'dsig-prod-{name}.service')
