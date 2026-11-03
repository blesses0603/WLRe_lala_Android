"""Real CA parsing and Android trust-store selection regression tests."""
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import HTTPRedirectHandler, HTTPSHandler

import certifi
from android_app.tls import configure_tls, verified_https_opener
from android_app.resource_sync import configure_paths


class AndroidTlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.system = self.root / "system"
        self.system.mkdir()
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        bundle = Path(certifi.where()).read_text(encoding="ascii")
        start = bundle.index("-----BEGIN CERTIFICATE-----")
        end = bundle.index("-----END CERTIFICATE-----", start) + len("-----END CERTIFICATE-----")
        self.ca = bundle[start:end].encode("ascii")

    def assert_verified_context(self):
        context = ssl.create_default_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_verified_urllib_handler_uses_explicit_android_ca(self):
        # The Android version downloader already passes cafile explicitly.
        # The Manifest/Bundle path must not rely on OpenSSL's default paths.
        selected = configure_tls(self.root, system_dirs=[])
        redirect = HTTPRedirectHandler()
        with patch('android_app.tls.ssl.create_default_context',
                   wraps=ssl.create_default_context) as create, \
             patch('android_app.tls.build_opener') as build:
            opener = verified_https_opener(redirect)
        create.assert_called_once_with(cafile=str(selected))
        self.assertIs(opener, build.return_value.open)
        self.assertEqual(len(build.call_args.args), 2)
        self.assertIs(build.call_args.args[0], redirect)
        handler = build.call_args.args[1]
        self.assertIsInstance(handler, HTTPSHandler)
        self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(handler._context.check_hostname)
        self.assertGreater(handler._context.cert_store_stats()['x509_ca'], 0)

    def test_verified_urllib_handler_fails_closed_for_invalid_explicit_ca(self):
        os.environ['SSL_CERT_FILE'] = str(self.root / 'missing-ca.pem')
        with self.assertRaises((OSError, ssl.SSLError)):
            verified_https_opener(HTTPRedirectHandler())
        self.assertEqual(os.environ['SSL_CERT_FILE'],
                         str(self.root / 'missing-ca.pem'))

    def test_stale_inherited_paths_are_replaced_with_valid_bundle(self):
        os.environ["SSL_CERT_FILE"] = "/missing/build-machine/cacert.pem"
        os.environ["REQUESTS_CA_BUNDLE"] = "/missing/requests.pem"
        selected = configure_tls(self.root, system_dirs=[])
        self.assertEqual(selected, Path(certifi.where()))
        self.assertEqual(os.environ["SSL_CERT_FILE"], str(selected))
        self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], str(selected))
        self.assert_verified_context()

    def test_system_ca_is_merged_and_duplicate_roots_are_deduplicated(self):
        (self.system / "0123abcd.0").write_bytes(self.ca)
        (self.system / "0123abcd.1").write_bytes(self.ca)
        selected = configure_tls(self.root, system_dirs=[self.system])
        self.assertEqual(selected, self.root / "tls/cacert.pem")
        original = Path(certifi.where()).read_bytes()
        self.assertEqual(selected.read_bytes(), original + b"\n" + self.ca + b"\n")
        self.assert_verified_context()
        self.assertFalse(list(selected.parent.glob(".ca-*")))

    def test_der_encoded_system_root_is_parsed_and_merged(self):
        der = ssl.PEM_cert_to_DER_cert(self.ca.decode("ascii"))
        (self.system / "0123abcd.0").write_bytes(der)
        selected = configure_tls(self.root, system_dirs=[self.system])
        self.assertEqual(selected, self.root / "tls/cacert.pem")
        self.assertIn(ssl.DER_cert_to_PEM_cert(der).encode("ascii"), selected.read_bytes())
        self.assert_verified_context()

    def test_non_system_filename_is_not_imported(self):
        (self.system / "user-added.pem").write_bytes(b"not a certificate")
        selected = configure_tls(self.root, system_dirs=[self.system])
        self.assertEqual(selected, Path(certifi.where()))
        self.assert_verified_context()

    def test_invalid_system_certificate_does_not_select_a_partial_bundle(self):
        (self.system / "0123abcd.0").write_bytes(b"invalid certificate")
        os.environ["SSL_CERT_FILE"] = "original"
        with self.assertRaises(ssl.SSLError):
            configure_tls(self.root, system_dirs=[self.system])
        self.assertEqual(os.environ["SSL_CERT_FILE"], "original")
        self.assertFalse((self.root / "tls/cacert.pem").exists())

    def test_missing_bundled_ca_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            configure_tls(self.root, cafile=self.root / "missing.pem", system_dirs=[])
        self.assertNotIn("SSL_CERT_FILE", os.environ)

    def test_atomic_replace_failure_preserves_existing_bundle(self):
        (self.system / "0123abcd.0").write_bytes(self.ca)
        target = self.root / "tls/cacert.pem"
        target.parent.mkdir()
        target.write_bytes(b"old")
        with patch("android_app.tls.os.replace", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                configure_tls(self.root, system_dirs=[self.system])
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse(list(target.parent.glob(".ca-*")))
        self.assertNotIn("SSL_CERT_FILE", os.environ)

    def test_activity_and_service_path_configuration_initializes_tls(self):
        context = Mock()
        context.getNoBackupFilesDir.return_value.getAbsolutePath.return_value = str(self.root)
        with patch("android_app.tls.configure_tls") as configure:
            self.assertEqual(configure_paths(context), self.root)
        configure.assert_called_once_with(self.root)
        self.assertEqual(os.environ["LOCALAPPDATA"], str(self.root))

    def test_non_android_host_has_no_configuration_side_effects(self):
        self.assertIsNone(configure_paths())
        self.assertNotIn("SSL_CERT_FILE", os.environ)


if __name__ == "__main__":
    unittest.main()
