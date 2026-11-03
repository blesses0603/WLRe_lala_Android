"""No official asset data or network calls: synthetic Manifest fixtures only."""

import io
from pathlib import Path
from urllib.error import HTTPError, URLError
import ssl
import tempfile
import unittest
import zlib

from wlre.services.official_manifest_sync import (
    ManifestSpec, ManifestSyncError, fetch_official_manifest,
    read_verified_cached_manifest, spec_from_snapshot,
)


CONTENT = b'LaLa synthetic YooAsset test, NOT game content!'
CRC_LE = zlib.crc32(CONTENT).to_bytes(4, 'little').hex().encode('ascii')


def spec():
    return ManifestSpec('1.3.21', 'DataPackage', '1275_2026_10_21_18_27_33_84')


def parse_synthetic(data):
    if data != CONTENT:
        raise ValueError('Wrong input data')
    return {
        'header': {'file_version': '2.2.5', 'package_name': 'DataPackage',
                   'package_version': '1275_2026_10_21_18_27_33_84',
                   'output_name_style': 1},
        'assets': [], 'bundles': [],
    }


class Response(io.BytesIO):
    status = 200

    def __init__(self, url, body, *, returned_url=None, size_header=True):
        super().__init__(body)
        self.url = returned_url or url
        self.headers = {'Content-Length': str(len(body))} if size_header else {}

    def geturl(self):
        return self.url


def responder(*, manifest=CONTENT, hash_bytes=CRC_LE, returned_url=None, requests=None):
    def open_request(req, timeout):
        if requests is not None:
            requests.append(req.full_url)
        return Response(req.full_url, hash_bytes if req.full_url.endswith('.hash') else manifest,
                        returned_url=returned_url)
    return open_request


class OfficialManifestSyncTests(unittest.TestCase):
    def test_exact_official_paths_not_version_suffixed(self):
        for package in ('DataPackage', 'MainPackage'):
            with self.subTest(package=package):
                value = ManifestSpec('1.3.21', package, spec().package_version)
                prefix = ('https://wlreftp.chinesegamer.net/WLN/TW/1.3.21/'
                          'ResourcesPC/AssetBundle/' + package)
                self.assertEqual(value.url('bytes'), prefix + '.bytes')
                self.assertEqual(value.url('hash'), prefix + '.hash')
                for unsupported in ('json', 'report', 'version', '../report'):
                    with self.assertRaises(ManifestSyncError):
                        value.url(unsupported)

    def test_download_and_reuse_verified_local_manifest(self):
        requests = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = fetch_official_manifest(spec(), cache_root=root,
                                            opener=responder(requests=requests),
                                            parser=parse_synthetic)
            self.assertTrue(first.downloaded)
            self.assertEqual(first.cache_path.read_bytes(), CONTENT)
            second = fetch_official_manifest(spec(), cache_root=root,
                                             opener=responder(requests=requests),
                                             parser=parse_synthetic)
            self.assertFalse(second.downloaded)
            self.assertEqual(requests, [spec().url('hash'), spec().url('bytes'),
                                        spec().url('hash')])
            historical = read_verified_cached_manifest(spec(), cache_root=root,
                                                        parser=parse_synthetic)
            self.assertEqual(historical.index, second.index)

    def test_historical_manifest_receipt_rejects_tampering_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch_official_manifest(spec(), cache_root=tmp,
                                    opener=responder(), parser=parse_synthetic)
            receipt = spec().receipt_path(tmp)
            self.assertTrue(receipt.is_file())
            receipt.write_bytes(receipt.read_bytes().replace(b'1275_', b'1262_'))
            with self.assertRaises(ManifestSyncError):
                read_verified_cached_manifest(spec(), cache_root=tmp,
                                              parser=parse_synthetic)

    def test_corrupt_local_cache_redownloads_after_official_hash_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = spec().cache_path(tmp)
            target.parent.mkdir(parents=True)
            target.write_bytes(b'corrupted cache')
            result = fetch_official_manifest(spec(), cache_root=tmp,
                                             opener=responder(), parser=parse_synthetic)
            self.assertTrue(result.downloaded)
            self.assertEqual(target.read_bytes(), CONTENT)

    def test_http_404_uses_one_bounded_same_origin_numeric_retry(self):
        requests = []
        def cdn(req, timeout):
            url = req.full_url
            requests.append(url)
            if '?' not in url:
                raise HTTPError(url, 404, 'not found', {}, None)
            return Response(url, CRC_LE if '.hash?' in url else CONTENT)
        with tempfile.TemporaryDirectory() as tmp:
            verified = fetch_official_manifest(
                spec(), cache_root=tmp, opener=cdn, parser=parse_synthetic)
            self.assertTrue(verified.downloaded)
            self.assertEqual(verified.cache_path.read_bytes(), CONTENT)
        self.assertEqual(len(requests), 4)
        canonical_hash, retried_hash, canonical_bytes, retried_bytes = requests
        self.assertEqual(canonical_hash, spec().url('hash'))
        self.assertEqual(canonical_bytes, spec().url('bytes'))
        for canonical, retried in ((canonical_hash, retried_hash),
                                   (canonical_bytes, retried_bytes)):
            self.assertEqual(retried.split('?', 1)[0], canonical)
            self.assertTrue(retried.startswith(canonical + '?'))
            self.assertRegex(retried.split('?', 1)[1],
                             r'\A[0-9]+(?:\.[0-9]+)?\Z')

    def test_repeated_http_404_reports_fixed_manifest_stage(self):
        requested = []
        def missing(req, timeout):
            requested.append(req.full_url)
            raise HTTPError(req.full_url, 404, 'PRIVATE remote value', {}, None)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, 'download failed') as caught:
                fetch_official_manifest(spec(), cache_root=tmp, opener=missing)
            self.assertEqual(caught.exception.stage, 'DataPackage.hash')
            self.assertIsInstance(caught.exception.__cause__, HTTPError)
            self.assertEqual(caught.exception.__cause__.code, 404)
            self.assertEqual(len(requested), 2)
            self.assertFalse(spec().cache_path(tmp).exists())

    def test_manifest_tls_failure_is_not_downgraded_or_retried(self):
        requested = []
        def bad_tls(req, timeout):
            requested.append(req.full_url)
            raise URLError(ssl.SSLCertVerificationError('PRIVATE trust detail'))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ManifestSyncError) as caught:
                fetch_official_manifest(spec(), cache_root=tmp, opener=bad_tls)
            self.assertEqual(caught.exception.stage, 'DataPackage.hash')
            self.assertEqual(len(requested), 1)
            self.assertFalse(spec().cache_path(tmp).exists())

    def test_bad_remote_hash_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, 'CRC32 mismatch'):
                fetch_official_manifest(spec(), cache_root=tmp,
                                        opener=responder(hash_bytes=b'deadbeef'),
                                        parser=parse_synthetic)
            self.assertFalse(spec().cache_path(tmp).exists())

    def test_invalid_hash_length_rejected_before_download(self):
        requests = []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, '8 hex'):
                fetch_official_manifest(spec(), cache_root=tmp,
                                        opener=responder(hash_bytes=b'wrong', requests=requests),
                                        parser=parse_synthetic)
            self.assertEqual(requests, [spec().url('hash')])

    def test_remote_redirect_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, 'location/status'):
                fetch_official_manifest(spec(), cache_root=tmp,
                                        opener=responder(returned_url='https://evil.example/'),
                                        parser=parse_synthetic)

    def test_package_revision_mismatch_rejected_without_cache(self):
        def wrong_revision(data):
            value = parse_synthetic(data)
            value['header']['package_version'] = '1262_2026_10_21_18_27_33_84'
            return value
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, 'identity'):
                fetch_official_manifest(spec(), cache_root=tmp,
                                        opener=responder(), parser=wrong_revision)
            self.assertFalse(spec().cache_path(tmp).exists())

    def test_invalid_manifest_and_parser_failure_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ManifestSyncError, 'parse failed'):
                fetch_official_manifest(spec(), cache_root=tmp,
                                        opener=responder(),
                                        parser=lambda data: (_ for _ in ()).throw(ValueError('bad')))

    def test_no_arbitrary_hosts_versions_or_extensions(self):
        for data_ver in ('../1.3.21', 'https://example.net', '1.3.21?x=1'):
            with self.subTest(data_ver=data_ver), self.assertRaises(ManifestSyncError):
                ManifestSpec(data_ver, 'DataPackage', spec().package_version)
        with self.assertRaises(ManifestSyncError):
            ManifestSpec('1.3.21', '../MainPackage', spec().package_version)
        with self.assertRaises(ManifestSyncError):
            spec().url('report')

    def test_snapshot_requires_validated_official_metadata(self):
        snapshot = {
            'schema_version': 1, 'origin': 'official_pc_version_endpoint',
            'data_ver': '1.3.21', 'exe_version': '1.3.21',
            'packages': {'DataPackage': spec().package_version,
                         'MainPackage': '1275_2026_10_21_18_29_38_49'},
            'checked_at_utc': '2026-10-24T09:00:00+00:00', 'assets_ready': False,
        }
        self.assertEqual(spec_from_snapshot(snapshot, 'DataPackage'), spec())
        snapshot['assets_ready'] = True
        with self.assertRaises(ValueError):
            spec_from_snapshot(snapshot, 'DataPackage')


if __name__ == '__main__':
    unittest.main()
