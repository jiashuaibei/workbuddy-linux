import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import io

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import publish_official as p

class Response(io.BytesIO):
    url = 'https://download.codebuddy.cn/test.deb'
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length)}

class PublisherTests(unittest.TestCase):
    def test_rejects_unsafe_sources_and_redirects(self):
        for url in ['http://download.codebuddy.cn/a', 'https://evil.com/a',
                    'https://download.codebuddy.cn.evil.com/a',
                    'https://user@download.codebuddy.cn/a', 'https://download.codebuddy.cn:444/a']:
            with self.assertRaises(ValueError): p.validate_url(url)
            with self.assertRaises(ValueError):
                p.OfficialRedirects().redirect_request(None, None, 302, '', {}, url)

    def test_original_bytes_preserved_and_hashed(self):
        data = b'!<arch>\n' + bytes(range(256)) * 30
        with tempfile.TemporaryDirectory() as d, patch.object(p, 'open_official', return_value=Response(data)):
            target = Path(d) / 'package.deb'
            digest, size, url = p.download(Response.url, target, 'deb')
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(digest, p.hashlib.sha256(data).hexdigest())
            self.assertEqual(size, len(data))

    def test_truncation_and_error_page_rejected(self):
        for data, size in [(b'!<arch>\ndata', 100), (b'<html>error</html>', 18)]:
            with tempfile.TemporaryDirectory() as d, patch.object(p, 'open_official', return_value=Response(data, size)):
                with self.assertRaises(ValueError):
                    p.download(Response.url, Path(d) / 'package.deb', 'deb')

    def test_identity_changes_when_upstream_revises_asset(self):
        r = dict(version='1.2', format='deb', url=Response.url, reportedSha256='a'*64)
        self.assertEqual(p.release_tag(r), p.release_tag(dict(r)))
        for changed in [dict(r, url=Response.url+'?new'), dict(r, reportedSha256='b'*64), dict(r, format='rpm')]:
            self.assertNotEqual(p.release_tag(r), p.release_tag(changed))

    def test_published_release_skips_download_and_writes(self):
        import json
        payload = json.dumps(dict(version='1.2', url=Response.url)).encode()
        names = ['WorkBuddy-1.2-linux-x86_64.deb', 'SHA256SUMS', 'provenance.json', 'upstream-response.json']
        old = dict(draft=False, assets=[dict(name=n) for n in names])
        with patch.object(p, 'open_official', return_value=Response(payload)), patch.object(p, 'existing_release', return_value=old), patch.object(p, 'download') as download, patch.object(p, 'gh') as gh:
            p.publish('deb', 'owner/repo', Path('/unused'))
            download.assert_not_called()
            gh.assert_not_called()

    def test_api_errors_are_not_absence(self):
        import subprocess
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 403')):
            with self.assertRaises(RuntimeError): p.existing_release('owner/repo', 'tag')
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 404')), patch.object(p, 'gh', return_value='[[]]'):
            self.assertIsNone(p.existing_release('owner/repo', 'tag'))

    def test_mismatch_is_disclosed_and_assets_precede_publication(self):
        import json
        payload = json.dumps(dict(version='1.2', url=Response.url, sha256hash='a'*64)).encode()
        data = b'!<arch>\noriginal package bytes'
        calls = []
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            def fake_gh(*args):
                calls.append(args)
                return ''
            def lookup(repo, tag):
                if not calls:
                    return None
                folder = output / tag
                names = ['WorkBuddy-1.2-linux-x86_64.deb', 'SHA256SUMS', 'provenance.json', 'upstream-response.json']
                return dict(draft=True, assets=[dict(name=n, size=(folder/n).stat().st_size,
                    digest='sha256:' + p.hashlib.sha256((folder/n).read_bytes()).hexdigest()) for n in names])
            with patch.object(p, 'open_official', side_effect=[Response(payload), Response(data)]), patch.object(p, 'existing_release', side_effect=lookup), patch.object(p, 'gh', side_effect=fake_gh), patch.dict(p.os.environ, {'GITHUB_SHA':'test-commit'}):
                p.publish('deb', 'owner/repo', output)
            folder = next(output.iterdir())
            record = json.loads((folder/'provenance.json').read_text())
            self.assertEqual(record['upstreamHashStatus'], 'mismatch')
            self.assertEqual(record['actualSha256'], p.hashlib.sha256(data).hexdigest())
            self.assertEqual((folder/'upstream-response.json').read_bytes(), payload)
            self.assertIn('不能宣称通过上游哈希验证', (folder/'release-notes.md').read_text())
            self.assertEqual([args[1] for args in calls], ['create', 'upload', 'edit'])
            self.assertIn('--draft', calls[0])
            self.assertIn('--draft=false', calls[-1])

    def test_draft_found_when_tag_endpoint_returns_404(self):
        import subprocess, json
        draft = dict(tag_name='tag', draft=True, assets=[])
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 404')), patch.object(p, 'gh', return_value=json.dumps([[], [draft]])):
            self.assertEqual(p.existing_release('owner/repo', 'tag'), draft)

    def test_saved_snapshot_is_reused_without_second_api_request(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            snapshot = Path(d)/'deb.json'
            snapshot.write_text(json.dumps(dict(version='1.2', url=Response.url)))
            names = ['WorkBuddy-1.2-linux-x86_64.deb', 'SHA256SUMS', 'provenance.json', 'upstream-response.json']
            old = dict(draft=False, assets=[dict(name=n) for n in names])
            with patch.object(p, 'open_official') as fetch, patch.object(p, 'existing_release', return_value=old):
                p.publish('deb', 'owner/repo', Path(d), metadata=snapshot)
                fetch.assert_not_called()
