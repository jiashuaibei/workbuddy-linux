import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('tracker', Path(__file__).parents[1] / 'scripts/track_official.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

class TrackerTests(unittest.TestCase):
    def record(self):
        return t.normalize({'version':'5.5.3.37748631','url':'https://download.codebuddy.cn/test.deb','sha256hash':'a'*64}, 'deb', '2026-09-12T00:00:00+00:00')

    def test_repeated_check_and_changed_asset(self):
        r=self.record(); data=t.merge({},[r],'one',{})
        t.merge(data,[r],'two',{})
        self.assertEqual(len(data['history']),1)
        changed=dict(r,reportedSha256='b'*64)
        t.merge(data,[changed],'three',{})
        self.assertEqual(len(data['history']),2)
        self.assertEqual(data['current']['deb']['reportedSha256'],'b'*64)

    def test_failure_preserves_history(self):
        data=t.merge({},[self.record()],'one',{})
        t.merge(data,[],'two',{'deb':'timeout'})
        self.assertEqual(data['current']['deb']['lastSuccessfulCheck'],'one')
        self.assertEqual(len(data['history']),1)

    def test_rejects_untrusted_url(self):
        for url in ['http://download.codebuddy.cn/a.deb','https://download.codebuddy.cn.evil.com/a.deb','https://evil.com/a.deb','https://user@download.codebuddy.cn/a.deb']:
            with self.assertRaises(ValueError): t.normalize({'version':'1.2','url':url},'deb','now')
