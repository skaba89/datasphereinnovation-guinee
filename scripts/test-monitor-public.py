import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock

spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('monitor-public.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
alert_spec = importlib.util.spec_from_file_location('alert', Path(__file__).with_name('notify-public.py'))
alert = importlib.util.module_from_spec(alert_spec)
alert_spec.loader.exec_module(alert)

class MonitorTests(unittest.TestCase):
    def test_alert(self):
        env = {'DSIG_PUBLIC_ALERT_'+k:v for k,v in {'SMTP_HOST':'smtp.example.org','FROM':'a@example.org','TO':'b@example.org','SMTP_USER':'fixture','SMTP_PASSWORD':'fixture'}.items()}
        factory = MagicMock()
        smtp = factory.return_value.__enter__.return_value
        smtp.send_message.return_value = {}
        alert.notify(env,factory)
        smtp.login.assert_called_once_with('fixture','fixture')
        self.assertNotIn('fixture',smtp.send_message.call_args.args[0].get_content())
        smtp.send_message.return_value = {'b@example.org':'rejected'}
        with self.assertRaises(ValueError): alert.notify(env,factory)
        with self.assertRaises(KeyError): alert.notify({},factory)

    def test_probes(self):
        bodies = {'/healthz':'ok','/':'rel="canonical" href="https://dsig-consulting.com/" content="index,follow,max-image-preview:large"','/robots.txt':'Sitemap: https://dsig-consulting.com/sitemap.xml','/sitemap.xml':'https://dsig-consulting.com/en.html'}
        def good(path): return 200, bodies[path], 30*86400, 100, ''
        self.assertEqual(module.monitor(good, now=0)['status'],'PASS')
        for status, expiry, elapsed, robots in [(503,30,100,''),(200,20,100,''),(200,30,5001,''),(200,30,100,'noindex')]:
            with self.subTest(status=status,expiry=expiry,elapsed=elapsed,robots=robots):
                self.assertEqual(module.monitor(lambda p:(status,bodies[p],expiry*86400,elapsed,robots), now=0)['status'],'FAIL')
        def offline(path): raise OSError('offline')
        self.assertEqual(module.monitor(offline, now=0)['status'],'FAIL')
        self.assertEqual(module.monitor(lambda p:(200,'wrong',30*86400,100,''),now=0)['status'],'FAIL')

if __name__ == '__main__': unittest.main()
