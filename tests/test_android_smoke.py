"""Smoke tests: diagnostic adb errors must not conceal Android startup results."""
from contextlib import chdir
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import android_smoke


class AndroidSmokeDiagnosticsTests(unittest.TestCase):
    def test_android_15_logcat_255_is_nonfatal_and_uses_bounded_fallback(self):
        def execute(argv, **kwargs):
            if argv[1:4] == ['logcat', '-d', '-t']:
                return subprocess.CompletedProcess(
                    argv, 0, 'AndroidRuntime: retained last 300 lines\n', '')
            if argv[1:3] == ['logcat', '-d']:
                return subprocess.CompletedProcess(argv, 255, '', 'device offline')
            return subprocess.CompletedProcess(argv, 0, 'service present\n', '')

        with tempfile.TemporaryDirectory() as folder:
            with chdir(folder), patch('tools.android_smoke.subprocess.run',
                                     side_effect=execute), patch('tools.android_smoke.time.sleep'):
                android_smoke.collect_diagnostics()
            log = (Path(folder) / 'android-smoke-logcat.txt').read_text()
            services = (Path(folder) / 'android-smoke-services.txt').read_text()
        self.assertIn('full logcat unavailable', log)
        self.assertIn('AndroidRuntime: retained', log)
        self.assertIn('service present', services)

    def test_optional_diagnostics_all_fail_without_throwing(self):
        with tempfile.TemporaryDirectory() as folder:
            with chdir(folder), patch('tools.android_smoke.subprocess.run',
                                     return_value=subprocess.CompletedProcess(
                                         ['adb'], 255, '', 'device offline')), patch(
                                         'tools.android_smoke.time.sleep'):
                android_smoke.collect_diagnostics(failed=True)
            log = (Path(folder) / 'android-smoke-logcat.txt').read_text()
            services = (Path(folder) / 'android-smoke-services.txt').read_text()
        self.assertIn('diagnostic unavailable', log)
        self.assertIn('diagnostic unavailable', services)

    def test_smoke_success_survives_failure_to_collect_diagnostics(self):
        markers = '\n'.join(android_smoke.MARKERS)

        def fake_adb(*args, **kwargs):
            if args[:2] == ('logcat', '-d'):
                return markers
            if args[:2] == ('shell', 'pidof'):
                return '1234\n'
            return ''

        def failure(argv, **kwargs):
            if argv[:2] == ['adb', 'install']:
                return subprocess.CompletedProcess(argv, 0)
            return subprocess.CompletedProcess(argv, 255, '', 'transient offline')

        with tempfile.TemporaryDirectory() as folder:
            with chdir(folder):
                Path('bin').mkdir()
                Path('bin/app.apk').write_bytes(b'apk fixture')
                with patch.object(android_smoke, 'adb', side_effect=fake_adb), patch(
                        'tools.android_smoke.subprocess.run', side_effect=failure), patch(
                        'tools.android_smoke.time.sleep'):
                    self.assertIsNone(android_smoke.main())
                self.assertIn('diagnostic unavailable',
                              Path('android-smoke-logcat.txt').read_text())

    def test_genuine_startup_failure_remains_failing_even_if_diagnostics_fail(self):
        markers = '\n'.join(android_smoke.MARKERS)

        def fake_adb(*args, **kwargs):
            if args[:2] == ('logcat', '-d'):
                return markers
            if args[:3] == ('shell', 'pidof', android_smoke.PACKAGE):
                return ''
            return ''

        def failure(argv, **kwargs):
            if argv[:2] == ['adb', 'install']:
                return subprocess.CompletedProcess(argv, 0)
            return subprocess.CompletedProcess(argv, 255, '', 'transient offline')

        with tempfile.TemporaryDirectory() as folder:
            with chdir(folder):
                Path('bin').mkdir()
                Path('bin/app.apk').write_bytes(b'apk fixture')
                with patch.object(android_smoke, 'adb', side_effect=fake_adb), patch(
                        'tools.android_smoke.subprocess.run', side_effect=failure), patch(
                        'tools.android_smoke.time.sleep'):
                    with self.assertRaisesRegex(AssertionError, 'Activity process exited'):
                        android_smoke.main()
                self.assertTrue(Path('android-smoke-logcat.txt').exists())
