import importlib.util
from pathlib import Path
import unittest
import copy
import json
import tempfile
from unittest.mock import patch

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
        self.assertEqual(data['current']['deb']['firstSeen'], self.record()['firstSeen'])
        self.assertEqual(data['lastChanged'], 'one')
        self.assertNotIn('errors', data)
        self.assertEqual(len(data['history']),1)

    def test_rejects_untrusted_url(self):
        for url in ['http://download.codebuddy.cn/a.deb','https://download.codebuddy.cn.evil.com/a.deb','https://evil.com/a.deb','https://user@download.codebuddy.cn/a.deb']:
            with self.assertRaises(ValueError): t.normalize({'version':'1.2','url':url},'deb','now')

    def test_unchanged_check_and_failure_do_not_change_release_data(self):
        data = t.merge({}, [self.record()], 'one', {})
        expected = copy.deepcopy(data)
        t.merge(data, [self.record()], 'two', {})
        self.assertEqual(data, expected)
        t.merge(data, [], 'three', {'deb': 'timeout'})
        self.assertEqual(data, expected)

    def test_migration_removes_check_state_without_losing_history(self):
        r = self.record()
        data = dict(schemaVersion=1, current={'deb':dict(r, lastSuccessfulCheck='old')},
                    history=[r], lastAttempt='old', errors={'rpm':'timeout'})
        t.merge(data, [], 'now', {})
        self.assertEqual(data['schemaVersion'], 2)
        self.assertEqual(data['history'], [r])
        self.assertEqual(data['current']['deb'], r)
        self.assertEqual(data['lastChanged'], r['firstSeen'])
        self.assertNotIn('lastAttempt', data)
        self.assertNotIn('errors', data)

    def test_old_version_becomes_current_without_duplicate_history(self):
        r = self.record()
        data = t.merge({}, [r], 'one', {})
        t.merge(data, [dict(r, version='6.0')], 'two', {})
        t.merge(data, [r], 'three', {})
        self.assertEqual(data['current']['deb']['version'], r['version'])
        self.assertEqual(data['lastChanged'], 'three')
        self.assertEqual(len(data['history']), 2)

    def test_repeated_cli_check_keeps_file_and_saves_errors_separately(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(t.os.environ, {}, clear=True):
            root = Path(d)
            output, status = root/'releases.json', root/'status.json'
            args = ['tracker', '--output', str(output), '--status', str(status), '--snapshot-dir', str(root/'upstream')]
            r = self.record()
            with patch('sys.argv', args), patch.object(t, 'fetch', side_effect=lambda fmt, *args: dict(r, format=fmt, url='https://download.codebuddy.cn/test.' + fmt)):
                self.assertFalse(t.main())
                first = output.read_bytes(), output.stat().st_mtime_ns
                self.assertFalse(t.main())
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), first)
            with patch('sys.argv', args), patch.object(t, 'fetch', side_effect=OSError('offline')):
                self.assertTrue(t.main())
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), first)
            self.assertEqual(json.loads(status.read_text())['errors'], {'deb':'offline', 'rpm':'offline'})

    def test_partial_failure_updates_only_successful_format(self):
        deb = self.record()
        rpm = dict(deb, format='rpm', url='https://download.codebuddy.cn/test.rpm')
        data = t.merge({}, [deb, rpm], 'one', {})
        t.merge(data, [dict(deb, version='6.0')], 'two', {'rpm':'offline'})
        self.assertEqual(data['current']['rpm'], rpm)
        self.assertEqual(data['current']['deb']['version'], '6.0')
