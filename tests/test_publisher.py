from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import io
import json
import subprocess

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import publish_official as p

VERSION = '5.6.2.40046327'
PACKAGES = {'deb': b'!<arch>\noriginal deb bytes',
            'rpm': b'\xed\xab\xee\xdboriginal rpm bytes'}


class Response(io.BytesIO):
    url = 'https://download.codebuddy.cn/test.deb'

    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length)}


def payload(fmt):
    return dict(version=VERSION, productVersion='5.6.2',
                url=f'https://download.codebuddy.cn/test.{fmt}',
                sha256hash=p.hashlib.sha256(PACKAGES[fmt]).hexdigest())


def snapshots(folder, mismatch=False):
    records = {}
    for fmt in p.FORMATS:
        data = payload(fmt)
        if mismatch and fmt == 'deb':
            data['sha256hash'] = 'a' * 64
        (folder / f'{fmt}.json').write_text(json.dumps(data))
        records[fmt] = p.normalize(data, fmt, 'now')
    return p.release_tag(records)


def public_release(tag):
    return dict(draft=False, tag_name=tag, name=f'WorkBuddy {VERSION}',
                assets=[dict(name=n, state='uploaded', size=100)
                        for n in p.required_assets(VERSION)])


class PublisherTests(unittest.TestCase):
    def test_rejects_unsafe_sources_and_redirects(self):
        for url in ['http://download.codebuddy.cn/a', 'https://evil.com/a',
                    'https://download.codebuddy.cn.evil.com/a',
                    'https://user@download.codebuddy.cn/a', 'https://download.codebuddy.cn:444/a']:
            with self.assertRaises(ValueError):
                p.validate_url(url)
            with self.assertRaises(ValueError):
                p.OfficialRedirects().redirect_request(None, None, 302, '', {}, url)

    def test_original_bytes_preserved_and_hashed(self):
        for fmt, data in PACKAGES.items():
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d, \
                    patch.object(p, 'open_official', return_value=Response(data)):
                target = Path(d) / ('package.' + fmt)
                digest, size, url = p.download(Response.url, target, fmt)
                self.assertEqual(target.read_bytes(), data)
                self.assertEqual(digest, p.hashlib.sha256(data).hexdigest())
                self.assertEqual(size, len(data))

    def test_truncation_and_error_page_rejected(self):
        for data, size in [(b'!<arch>\ndata', 100), (b'<html>error</html>', 18)]:
            with tempfile.TemporaryDirectory() as d, patch.object(p, 'open_official', return_value=Response(data, size)):
                with self.assertRaises(ValueError):
                    p.download(Response.url, Path(d) / 'package.deb', 'deb')

    def test_identity_changes_when_either_upstream_asset_changes(self):
        records = {fmt: p.normalize(payload(fmt), fmt, 'now') for fmt in p.FORMATS}
        tag = p.release_tag(records)
        self.assertTrue(tag.startswith('official-' + VERSION + '-'))
        for fmt in p.FORMATS:
            for field in ['url', 'reportedSha256', 'version']:
                revised = {key: dict(value) for key, value in records.items()}
                revised[fmt][field] += '1'
                self.assertNotEqual(tag, p.release_tag(revised))

    def test_published_pair_reuses_snapshots_without_download_or_writes(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            old = public_release(snapshots(folder))
            with patch.object(p, 'open_official') as fetch, \
                    patch.object(p, 'existing_release', return_value=old), \
                    patch.object(p, 'get_release', return_value=old), \
                    patch.object(p, 'download') as download, patch.object(p, 'gh') as gh:
                p.publish('owner/repo', folder, metadata_dir=folder)
                fetch.assert_not_called()
                download.assert_not_called()
                gh.assert_not_called()

    def test_existing_complete_pair_repairs_latest_and_title_without_reupload(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            tag = snapshots(folder)
            old = public_release(tag)
            old['name'] = 'Overly long title'
            with patch.object(p, 'existing_release', return_value=old), \
                    patch.object(p, 'get_release', return_value={'tag_name': 'v5.4.5'}), \
                    patch.object(p, 'download') as download, patch.object(p, 'gh') as gh:
                p.publish('owner/repo', folder, metadata_dir=folder)
                download.assert_not_called()
                gh.assert_called_once_with('release', 'edit', tag, '--repo', 'owner/repo',
                                           '--title', f'WorkBuddy {VERSION}', '--latest=true')

    def test_incomplete_public_pair_is_never_promoted_or_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            old = public_release(snapshots(folder))
            old['assets'] = [a for a in old['assets'] if not a['name'].endswith('.rpm')]
            with patch.object(p, 'existing_release', return_value=old), \
                    patch.object(p, 'download') as download, patch.object(p, 'gh') as gh:
                with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                    p.publish('owner/repo', folder, metadata_dir=folder)
                download.assert_not_called()
                gh.assert_not_called()

    def test_missing_or_different_full_versions_stop_before_download(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            snapshots(folder)
            data = payload('rpm')
            data['version'] = '5.6.2.40046328'
            (folder / 'rpm.json').write_text(json.dumps(data))
            with patch.object(p, 'download') as download, patch.object(p, 'gh') as gh:
                with self.assertRaisesRegex(RuntimeError, 'full versions differ'):
                    p.publish('owner/repo', folder, metadata_dir=folder)
                (folder / 'rpm.json').unlink()
                with self.assertRaises(FileNotFoundError):
                    p.publish('owner/repo', folder, metadata_dir=folder)
                download.assert_not_called()
                gh.assert_not_called()

    def test_api_errors_are_not_absence(self):
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 403')):
            with self.assertRaises(RuntimeError):
                p.existing_release('owner/repo', 'tag')
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 404')), \
                patch.object(p, 'gh', return_value='[[]]'):
            self.assertIsNone(p.existing_release('owner/repo', 'tag'))

    def test_draft_found_when_tag_endpoint_returns_404(self):
        draft = dict(tag_name='tag', draft=True, assets=[])
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'HTTP 404')), \
                patch.object(p, 'gh', return_value=json.dumps([[], [draft]])):
            self.assertEqual(p.existing_release('owner/repo', 'tag'), draft)

    def run_publication(self, output, tag, corrupt=None, recovering=False):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            return ''

        def lookup(repo, lookup_tag):
            if not calls:
                return dict(draft=True, assets=[]) if recovering else None
            folder = output / tag
            assets = [dict(name=n, state='uploaded', size=(folder / n).stat().st_size,
                           digest='sha256:' + p.hashlib.sha256((folder / n).read_bytes()).hexdigest())
                      for n in p.required_assets(VERSION)]
            if corrupt == 'missing':
                assets = [a for a in assets if not a['name'].endswith('.rpm')]
            if corrupt == 'digest':
                assets[0]['digest'] = 'sha256:' + '0' * 64
            return dict(draft=True, assets=assets)

        with patch.object(p, 'open_official', side_effect=[Response(PACKAGES[f]) for f in p.FORMATS]) as fetch, \
                patch.object(p, 'existing_release', side_effect=lookup), \
                patch.object(p, 'gh', side_effect=fake_gh), \
                patch.dict(p.os.environ, {'GITHUB_SHA': 'test-commit', 'GITHUB_RUN_ID': '123'}, clear=True):
            if corrupt:
                with self.assertRaisesRegex(RuntimeError, 'Uploaded asset .* mismatch'):
                    p.publish('owner/repo', output, metadata_dir=output)
            else:
                p.publish('owner/repo', output, metadata_dir=output)
            self.assertEqual([c.args[0] for c in fetch.call_args_list],
                             [payload(f)['url'] for f in p.FORMATS])
        return calls

    def test_pair_full_version_evidence_and_latest_after_both_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            tag = snapshots(output, mismatch=True)
            calls = self.run_publication(output, tag)
            folder = output / tag
            checksums = (folder / 'SHA256SUMS').read_text().splitlines()
            self.assertEqual(len(checksums), 2)
            for fmt in p.FORMATS:
                record = json.loads((folder / f'provenance-{fmt}.json').read_text())
                self.assertEqual(record['version'], VERSION)
                self.assertEqual(record['upstreamHashStatus'], 'mismatch' if fmt == 'deb' else 'match')
                self.assertEqual(record['actualSha256'], p.hashlib.sha256(PACKAGES[fmt]).hexdigest())
                self.assertEqual((folder / record['filename']).read_bytes(), PACKAGES[fmt])
                self.assertEqual((folder / f'upstream-response-{fmt}.json').read_bytes(),
                                 (output / f'{fmt}.json').read_bytes())
                self.assertIn(record['actualSha256'] + '  ' + record['filename'], checksums)
            self.assertIn('不能宣称通过上游哈希验证', (folder / 'release-notes.md').read_text())
            self.assertEqual([args[1] for args in calls], ['create', 'upload', 'edit'])
            self.assertIn('--draft', calls[0])
            self.assertEqual({Path(n).name for n in calls[1][3:-3]}, p.required_assets(VERSION))
            self.assertIn('--draft=false', calls[-1])
            self.assertIn('--latest=true', calls[-1])
            self.assertEqual(calls[-1][calls[-1].index('--title') + 1], f'WorkBuddy {VERSION}')

    def test_upload_integrity_failures_never_publish_partial_pair(self):
        for corrupt in ('missing', 'digest'):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as d:
                output = Path(d)
                calls = self.run_publication(output, snapshots(output), corrupt=corrupt)
                self.assertEqual([args[1] for args in calls], ['create', 'upload'])

    def test_interrupted_draft_recovers_as_one_release(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            calls = self.run_publication(output, snapshots(output), recovering=True)
            self.assertEqual([args[1] for args in calls], ['upload', 'edit'])
            self.assertIn('--latest=true', calls[-1])

    def test_dry_run_downloads_both_without_github_mutations(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            responses = [Response(json.dumps(payload(f)).encode()) for f in p.FORMATS]
            responses += [Response(PACKAGES[f]) for f in p.FORMATS]
            with patch.object(p, 'open_official', side_effect=responses), \
                    patch.object(p, 'existing_release') as lookup, patch.object(p, 'gh') as gh:
                p.publish('owner/repo', output, dry_run=True)
                lookup.assert_not_called()
                gh.assert_not_called()
            folder = next(output.iterdir())
            self.assertTrue(p.required_assets(VERSION).issubset({f.name for f in folder.iterdir()}))
