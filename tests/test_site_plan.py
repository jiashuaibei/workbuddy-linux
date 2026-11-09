from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import plan_site as p


class SitePlanTests(unittest.TestCase):
    def test_no_change_skips_and_new_version_or_page_edit_deploys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'releases.json').write_text('{"version":"1"}')
            original, needed = p.needs_deploy(root, {})
            self.assertTrue(needed)
            marker = {'digest': original}
            self.assertFalse(p.needs_deploy(root, marker)[1])
            (root/p.MARKER).write_text('generated marker does not affect hash')
            self.assertFalse(p.needs_deploy(root, marker)[1])
            (root/'releases.json').write_text('{"version":"2"}')
            self.assertTrue(p.needs_deploy(root, marker)[1])
            # The deployment failed: same old remote marker still requests a retry.
            self.assertTrue(p.needs_deploy(root, marker)[1])
            marker = {'digest': p.fingerprint(root)}
            self.assertFalse(p.needs_deploy(root, marker)[1])
            (root/'index.html').write_text('website edit')
            self.assertTrue(p.needs_deploy(root, marker)[1])
