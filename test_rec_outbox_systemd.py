"""Static contracts for the optional REC outbox units."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent / "deploy/systemd"


class OutboxSystemdTests(unittest.TestCase):
    def unit(self, name):
        return (ROOT / ("dsig-rec-outbox-" + name)).read_text()

    def test_private_shared_state(self):
        for name in ("observe.service", "deliver.service"):
            text = self.unit(name)
            for directive in ("User=ubuntu", "StateDirectory=dsig-rec-outbox",
                              "StateDirectoryMode=0700", "UMask=0077",
                              "NoNewPrivileges=yes", "ProtectSystem=strict",
                              "ProtectHome=read-only", "PrivateTmp=yes"):
                self.assertIn(directive + "\n", text)
            self.assertIn("--state-dir /var/lib/dsig-rec-outbox", text)

    def test_credentials_only_in_delivery(self):
        observe = self.unit("observe.service")
        deliver = self.unit("deliver.service")
        self.assertNotIn("EnvironmentFile=", observe)
        self.assertIn("EnvironmentFile=/etc/dsig-rec-alert.env\n", deliver)
        self.assertIn("--observe\n", observe)
        self.assertIn("--deliver\n", deliver)
        self.assertNotIn("--deliver", observe)
        self.assertNotIn("--observe", deliver)

    def test_no_recursive_alerts(self):
        for name in ("observe.service", "deliver.service"):
            self.assertNotIn("OnFailure=", self.unit(name))

    def test_schedule(self):
        for kind, interval in (("observe", "5min"), ("deliver", "1min")):
            text = self.unit(kind + ".timer")
            self.assertIn("OnUnitInactiveSec=" + interval + "\n", text)
            self.assertIn("Unit=dsig-rec-outbox-" + kind + ".service\n", text)
            self.assertIn("WantedBy=timers.target\n", text)

    def test_legacy_monitor_unchanged_contract(self):
        text = (ROOT / "dsig-rec-monitor.service").read_text()
        self.assertIn("scripts/monitor-rec.py", text)
        self.assertNotIn("rec_alert_outbox", text)
