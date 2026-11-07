import tempfile
import unittest
from pathlib import Path
from tools.audit_repository import application_version, invalid_links


class AndroidRepositoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'README.md').write_text('[History](CHANGELOG.md)', encoding='utf-8')
        (self.root / 'CHANGELOG.md').write_text('# Existing history', encoding='utf-8')

    def test_android_history_name(self):
        self.assertEqual(invalid_links(self.root), (1, []))

    def test_missing_android_history_is_not_silently_skipped(self):
        (self.root / 'CHANGELOG.md').unlink()
        self.assertIn('CHANGELOG.md: missing document', invalid_links(self.root)[1])

    def test_broken_history_link_is_checked(self):
        (self.root / 'CHANGELOG.md').write_text('[Missing](missing.md)', encoding='utf-8')
        self.assertIn('CHANGELOG.md: missing.md', invalid_links(self.root)[1])

    def test_version_uses_android_source_and_requires_spec_match(self):
        (self.root / 'android_app').mkdir()
        (self.root / 'android_app/version.py').write_text('ANDROID_VERSION = "1.2.3"', encoding='utf-8')
        spec = self.root / 'buildozer.spec'
        spec.write_text('[app]\nversion = 1.2.3\n', encoding='utf-8')
        self.assertEqual(application_version(self.root), '1.2.3')
        spec.write_text('[app]\nversion = 1.2.4\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Version mismatch'):
            application_version(self.root)
