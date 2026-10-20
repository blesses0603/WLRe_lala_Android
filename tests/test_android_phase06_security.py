"""Phase06 hostile archive, AF_UNIX IPC framing and encrypted vault regression."""
from io import BytesIO
import json
from pathlib import Path
import os
import socket
import stat
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from android_app.runtime import MAX_FRAME, receive, send, _trusted_peer
from android_app.vault import AccountVault
from tools.android_archive_audit import MAX_DEPTH, audit_apk
from tools.android_hardening import check_apk, inspect_apk, report


def tar_bytes(entries):
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as stream:
        for name, data in entries.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            stream.addfile(item, BytesIO(data))
    return output.getvalue()


def zip_bytes(entries):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return output.getvalue()


class RecursiveArchiveSecurity(unittest.TestCase):
    @staticmethod
    def public_cert():
        # Generate test-only key in memory and include ONLY its public certificate.
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
        cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
            .not_valid_after(datetime.datetime(2040, 1, 1, tzinfo=datetime.timezone.utc))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
        return cert.public_bytes(serialization.Encoding.PEM)

    def test_public_certifi_ca_bundles_are_not_private_credentials(self):
        pem = b"# Trusted public CA\n" + self.public_cert()
        for path in (
            "certifi/cacert.pem",
            "site-packages/certifi/cacert.pem",
            "_python_bundle/site-packages/certifi/cacert.pem",
            "./_python_bundle/site-packages/certifi/cacert.pem",
        ):
            with self.subTest(path=path):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({
                    path: pem, "site-packages/safe.pyc": b"bytecode",
                })})
                info = inspect_apk(self.path)
                self.assertGreaterEqual(info["scanned_text_files"], 1)
                self.assertTrue(check_apk(self.path))

    def test_no_private_material_can_disguise_itself_as_certifi_ca(self):
        cert = self.public_cert()
        key_header = ("-----BEGIN " + "PRIVATE KEY-----").encode()
        for content in (
            key_header + b"\nredacted",
            cert + b"\n" + key_header,
            cert + b"\n-----BEGIN UNKNOWN-----\nAAAA\n-----END UNKNOWN-----",
            b"not PEM at all",
            b"# comments but no certificates",
            cert + b"\npassword=secret",
        ):
            with self.subTest(size=len(content)):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({
                    "site-packages/certifi/cacert.pem": content,
                })})
                with self.assertRaisesRegex(ValueError, "credential|Unsafe certifi"):
                    check_apk(self.path)

    def test_only_exact_certifi_path_is_exception(self):
        pem = self.public_cert()
        for path in (
            "site-packages/certifi/private.pem",
            "site-packages/certifi/cacert.key",
            "site-packages/other/cacert.pem",
            "android_app/certifi/cacert.pem",
            ".env",
            "credentials.json",
            "site-packages/secret.keystore",
            "_python_bundle/site-packages/certifi/private.pem",
            "_python_bundle/site-packages/other/cacert.pem",
            "prefix/_python_bundle/site-packages/certifi/cacert.pem",
            "_python_bundle/site-packages/certifi/nested/cacert.pem",
        ):
            with self.subTest(path=path):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({path: pem})})
                with self.assertRaisesRegex(ValueError, "credential"):
                    check_apk(self.path)

    def test_rejected_archive_name_diagnostics_are_safe_and_precise(self):
        # Exercise the actual libpybundle.so TAR scan. No sensitive member
        # basename or member contents may appear in GitHub Actions failures.
        cases = (
            ("unexpected/certifi/cacert.pem", "ca-bundle-location"),
            ("private_data/build_signer.p12", "restricted-extension"),
            ("private_data/credentials.json", "reserved-name"),
        )
        for member_name, rule in cases:
            with self.subTest(rule=rule):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({
                    member_name: b"synthetic-test-payload",
                })})
                with self.assertRaisesRegex(
                    ValueError, "Potential credential file in nested archive"
                ) as failure:
                    inspect_apk(self.path)
                message = str(failure.exception)
                self.assertIn("rule=" + rule, message)
                self.assertNotIn(member_name, message)
                self.assertNotIn(member_name.rsplit("/", 1)[-1], message)
                self.assertNotIn("synthetic-test-payload", message)

    def test_p4a_public_ca_path_still_rejects_secret_or_malformed_payloads(self):
        cert = self.public_cert()
        private_header = ("-----BEGIN " + "PRIVATE KEY-----").encode()
        p4a_path = "_python_bundle/site-packages/certifi/cacert.pem"
        for contents in (
            private_header,
            cert + private_header,
            cert + b"\npassword=secret",
            b"not a certificate",
            b"#" * (512 * 1024 + 1),
        ):
            with self.subTest(length=len(contents)):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({
                    p4a_path: contents,
                })})
                with self.assertRaisesRegex(ValueError, "credential|Unsafe certifi"):
                    check_apk(self.path)

    def test_public_ca_exception_preserves_size_and_path_limits(self):
        cert = self.public_cert()
        for path, content in (
            ("site-packages/certifi/cacert.pem", b"#" * (512 * 1024 + 1)),
            ("../certifi/cacert.pem", cert),
        ):
            with self.subTest(path=path):
                self.apk({"lib/arm64-v8a/libpybundle.so": tar_bytes({path: content})})
                with self.assertRaises(ValueError):
                    check_apk(self.path)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "test.apk"

    def apk(self, entries):
        with zipfile.ZipFile(self.path, "w") as z:
            for name, data in entries.items():
                z.writestr(name, data)
        return self.path

    def test_nested_zip_then_tar_secret_file_rejected(self):
        payload = zip_bytes({"sub/data.tar": tar_bytes({"nested/secret.keystore": b"x"})})
        self.apk({"assets/custom.zip": payload})
        with self.assertRaisesRegex(ValueError, "credential"):
            check_apk(self.path)

    def test_nested_application_python_rejected(self):
        self.apk({"assets/game.zip": zip_bytes({"android_app/vault.py": b"secret"})})
        with self.assertRaisesRegex(ValueError, "Uncompiled application Python"):
            check_apk(self.path)

    def test_private_header_in_small_nested_text_is_blocked_and_not_logged(self):
        marker = ("-----BEGIN " + "PRIVATE KEY-----").encode()
        self.apk({"assets/archive.zip": zip_bytes({"assets/readme.txt": b"hello " + marker})})
        with self.assertRaisesRegex(ValueError, "Private credential material") as err:
            check_apk(self.path)
        self.assertNotIn(marker.decode(), str(err.exception))

    def test_libpybundle_tar_cannot_hide_nested_credentials(self):
        payload = tar_bytes({"site-packages/stuff.zip": zip_bytes({"runtime/.env": b"hidden"})})
        self.apk({"lib/arm64-v8a/libpybundle.so": payload})
        with self.assertRaisesRegex(ValueError, "credential"):
            check_apk(self.path)

    def test_nested_zip_member_rejects_traversal(self):
        self.apk({"assets/safe.zip": zip_bytes({"../../escape.json": b"{}"})})
        with self.assertRaisesRegex(ValueError, "Unsafe nested"):
            check_apk(self.path)

    def test_nested_zip_duplicate_members_rejected(self):
        output = BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr("good.txt", b"a")
            z.writestr("good.TXT", b"b")
        self.apk({"assets/safe.zip": output.getvalue()})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            check_apk(self.path)

    def test_nested_tar_link_rejected(self):
        file = BytesIO()
        with tarfile.open(fileobj=file, mode="w:gz") as tar:
            m = tarfile.TarInfo("link.txt")
            m.type = tarfile.SYMTYPE
            m.linkname = "elsewhere"
            tar.addfile(m)
        self.apk({"assets/notes.tar": file.getvalue()})
        with self.assertRaisesRegex(ValueError, "Unsafe nested TAR"):
            check_apk(self.path)

    def test_normal_zip_tar_and_known_binary_do_not_false_positive(self):
        self.apk({
            "assets/private.tar": tar_bytes({"wlre/network/wire.pyc": b"bytecode",
                                             "assets/config.json": b'{"feature":true}'}),
            "lib/arm64-v8a/libpybundle.so": tar_bytes({"site-packages/module.so": b"\x7fELFfake"}),
            "assets/inner.zip": zip_bytes({"content/data.json": b'{"ready":true}'}),
        })
        result = inspect_apk(self.path)
        self.assertGreaterEqual(result["audited_containers"], 3)
        self.assertGreaterEqual(result["scanned_text_files"], 2)
        info = report(self.path).read_text()
        self.assertIn("Phase06 ZIP/TAR nesting and credential signature gate: PASSED", info)
        self.assertIn("PHASE05_ALL_CORES_INFO.txt", info)

    def test_unknown_unsafe_zip_content_fails_closed(self):
        self.apk({"assets/inner.zip": b"not a ZIP"})
        with self.assertRaisesRegex(ValueError, "Corrupt nested ZIP"):
            check_apk(self.path)


class IPCFrameSecurity(unittest.TestCase):
    def payload(self, value):
        return BytesIO(value)

    def test_legal_request_and_reply_roundtrip(self):
        f = BytesIO()
        send(f, {"op": "poll", "data": {"hello": "世界"}})
        f.seek(0)
        self.assertEqual(receive(f)["op"], "poll")
        f = BytesIO()
        send(f, {"ok": True, "value": []})
        f.seek(0)
        self.assertTrue(receive(f)["ok"])

    def test_reject_non_object_trailing_invalid_and_oversized_json(self):
        bad = [b'[]\n', b'null\n', b'{"op":"poll"}',
               b'{"op":"poll","op":"shutdown"}\n',
               b'{"op":"poll","value":NaN}\n',
               b'{"op":"poll","data":{"x":1,"x":2}}\n',
               b'{"op":\xff}\n',
               b'{"op":"poll","a":"' + b"x" * MAX_FRAME + b'"}\n']
        for blob in bad:
            with self.subTest(blob=blob[:35]):
                with self.assertRaises(ValueError):
                    receive(self.payload(blob))

    def test_peer_same_uid_only(self):
        class Socket:
            def __init__(self, uid):
                self.uid = uid
            def getsockopt(self, *args):
                return struct.pack("3i", 4321, self.uid, 99)
        with patch("android_app.runtime.os.getuid", return_value=10023):
            self.assertTrue(_trusted_peer(Socket(10023)))
            self.assertFalse(_trusted_peer(Socket(10024)))
            with patch("android_app.runtime.socket.SO_PEERCRED", create=True, new=None):
                # There is no valid getsockopt selector in this case.
                self.assertFalse(_trusted_peer(Socket(10023))) if not hasattr(socket, "SO_PEERCRED") else None

    def test_ipc_send_rejects_nonfinite_json(self):
        with self.assertRaises(ValueError):
            send(BytesIO(), {"value": float("nan")})


class VaultFSProtection(unittest.TestCase):
    class Cipher:
        def encrypt(self, data):
            return {"payload": data.decode()}
        def decrypt(self, record):
            return record["payload"].encode()

    def test_vault_mode_and_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "private"
            root.mkdir(mode=0o755)
            vault = AccountVault(root / "account.enc", self.Cipher())
            vault.save([{"account": "fixture-user"}])
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(vault.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(vault.load(), [{"account": "fixture-user"}])
            vault.save([])
            self.assertEqual(vault.load(), [])

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "Requires POSIX no-follow")
    def test_vault_load_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vault.enc"
            target = Path(d) / "target.json"
            target.write_text('{"payload":"secret"}')
            path.symlink_to(target)
            with self.assertRaises(OSError):
                AccountVault(path, self.Cipher()).load()
            self.assertEqual(json.loads(target.read_text())["payload"], "secret")

    def test_vault_refuses_preplanted_temporary_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vault.enc"
            victim = Path(d) / "victim"
            victim.write_text("sensitive")
            path.with_suffix(".tmp").symlink_to(victim)
            with self.assertRaises(FileExistsError):
                AccountVault(path, self.Cipher()).save([])
            self.assertEqual(victim.read_text(), "sensitive")


if __name__ == "__main__":
    unittest.main()
