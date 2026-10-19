"""Phase08 credential-residency and CI diagnostic privacy regression cases."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from android_app.credentials import (
    public_accounts, saved_password, store_account, delete_account,
)
from android_app.runtime import Runtime, ServiceManager
from tools.android_diagnostic_redaction import (
    summarize_logcat, summarize_services,
)


class FakeVault:
    def __init__(self, rows=()):
        self.rows = copy.deepcopy(list(rows))
        self.loads = 0
    def load(self):
        self.loads += 1
        return copy.deepcopy(self.rows)
    def save(self, rows):
        self.rows = copy.deepcopy(rows)


class CredentialResidencyTests(unittest.TestCase):
    def test_public_index_contains_no_decrypted_password(self):
        vault = FakeVault([
            {"server": "壹", "account": "alpha", "password": "SUPERSECRET"},
            {"server": "貳", "account": "beta", "password": "TOPSECRET"},
        ])
        metadata = public_accounts(vault.load())
        self.assertEqual(metadata, [
            {"server": "壹", "account": "alpha"},
            {"server": "貳", "account": "beta"},
        ])
        self.assertNotIn("SUPERSECRET", str(metadata))
        self.assertNotIn("TOPSECRET", str(metadata))
        self.assertEqual(vault.loads, 1)
        self.assertEqual(saved_password(vault, "貳", "beta"), "TOPSECRET")
        self.assertEqual(vault.loads, 2)

    def test_store_and_delete_keep_encrypted_vault_contract(self):
        vault = FakeVault([
            {"server": "A", "account": "alpha", "password": "old"},
            {"server": "B", "account": "beta", "password": "other"},
        ])
        index = store_account(vault, "A", "alpha", "new-pass")
        self.assertEqual(len(index), 2)
        self.assertFalse(any("password" in r for r in index))
        self.assertEqual(saved_password(vault, "A", "alpha"), "new-pass")
        self.assertEqual(saved_password(vault, "B", "beta"), "other")
        remaining = delete_account(vault, "A", "alpha")
        self.assertEqual(remaining, [{"server": "B", "account": "beta"}])
        with self.assertRaises(ValueError):
            saved_password(vault, "A", "alpha")

    def test_bad_record_and_missing_password_fail_closed_without_cache(self):
        for value in ("invalid", {}, {"server": "A", "account": None}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    public_accounts([value])
        vault = FakeVault([{"server": "A", "account": "alpha", "password": ""}])
        with self.assertRaisesRegex(ValueError, "Invalid saved credential"):
            saved_password(vault, "A", "alpha")
        with self.assertRaises(ValueError):
            store_account(vault, "A", "alpha", "")

    def test_kivy_saved_selection_on_demand_and_delete(self):
        from android_app.app import LaLaApp
        vault = FakeVault([{"server": "伺服器一", "account": "甲", "password": "private-one"}])
        holder = SimpleNamespace(
            saved_accounts=public_accounts(vault.load()),
            vault=vault, password=SimpleNamespace(text="OLD"),
            account=SimpleNamespace(text=""), server=SimpleNamespace(text=""),
            message=SimpleNamespace(text=""),
            saved=SimpleNamespace(text="甲 | 伺服器一", values=[]),
        )
        holder.saved_names = lambda: LaLaApp.saved_names(holder)
        self.assertEqual(vault.loads, 1)
        LaLaApp.switch_saved(holder, None, "甲 | 伺服器一")
        self.assertEqual(holder.password.text, "private-one")
        self.assertEqual(vault.loads, 2)
        self.assertFalse(any("password" in r for r in holder.saved_accounts))
        LaLaApp.delete_saved(holder)
        self.assertEqual(holder.saved_accounts, [])
        self.assertEqual(holder.password.text, "")
        self.assertEqual(vault.rows, [])

    def test_failed_decrypt_clears_password_field(self):
        from android_app.app import LaLaApp
        class BrokenVault:
            def load(self):
                raise ValueError("PRIVATE_DECRYPTION_DETAILS")
        holder = SimpleNamespace(
            saved_accounts=[{"server": "S", "account": "A"}],
            vault=BrokenVault(), password=SimpleNamespace(text="stale-secret"),
            account=SimpleNamespace(text=""), server=SimpleNamespace(text=""),
            message=SimpleNamespace(text=""),
        )
        holder.saved_names = lambda: LaLaApp.saved_names(holder)
        LaLaApp.switch_saved(holder, None, "A | S")
        self.assertEqual(holder.password.text, "")
        self.assertNotIn("PRIVATE_DECRYPTION_DETAILS", holder.message.text)

    def test_connect_remembers_encrypted_record_but_only_metadata_in_ui(self):
        from android_app.app import LaLaApp
        vault = FakeVault()
        starts = []
        holder = SimpleNamespace(
            manager=SimpleNamespace(background=True, start=lambda **kwargs: starts.append(kwargs)),
            lookup={"A": {"host": "localhost", "port": 1111}},
            server=SimpleNamespace(text="A"),
            account=SimpleNamespace(text="alice"),
            password=SimpleNamespace(text="sent-once"),
            remember=SimpleNamespace(active=True),
            vault=vault, saved_accounts=[],
            saved=SimpleNamespace(values=[]),
            message=SimpleNamespace(text=""),
        )
        holder.saved_names = lambda: LaLaApp.saved_names(holder)
        with patch("android_app.app.platform", "android"):
            LaLaApp.connect_account(holder)
        self.assertEqual(starts[0]["password"], "sent-once")
        self.assertEqual(holder.password.text, "")
        self.assertEqual(holder.saved_accounts, [{"server": "A", "account": "alice"}])
        self.assertEqual(vault.rows[0]["password"], "sent-once")
        self.assertNotIn("sent-once", str(holder.saved_accounts))


class IPCSecretLifetimeTests(unittest.TestCase):
    def test_service_start_consumes_password_even_on_failure(self):
        class Manager:
            def start(self, **kwargs):
                self.password = kwargs["password"]
                return SimpleNamespace(session_id="123")
        manager = Manager()
        service = Runtime(manager)
        command = {"op": "start", "args": {"label": "A", "password": "ONCE"}}
        self.assertEqual(service.dispatch(command), {"id": "123"})
        self.assertNotIn("password", command["args"])

        class BrokenManager:
            def start(self, **kwargs):
                raise ValueError("PRIVATE_LOGIN_DATA")
        failed = Runtime(BrokenManager())
        another = {"op": "start", "args": {"password": "NEVER_PERSIST"}}
        with self.assertRaises(ValueError):
            failed.dispatch(another)
        self.assertNotIn("password", another["args"])

    def test_ipc_client_clears_queued_password_on_connection_failure(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.path = "/tmp/nonexistent/lala.sock"
        queued = {"op": "start", "args": {"password": "NOT_KEPT"}}
        with patch("android_app.runtime.socket.socket", side_effect=OSError("connection refused")):
            with self.assertRaises(OSError):
                manager.call(queued)
        self.assertNotIn("password", queued["args"])


class DiagnosticPrivacyTests(unittest.TestCase):
    def test_logcat_summary_never_includes_secret_even_on_known_marker_line(self):
        raw = (
            "WLRE_ANDROID_UI_READY password=VERY_PRIVATE\n"
            "WLRE_ANDROID_SERVICE_CONNECTED Authorization: Bearer abcDEFGH\n"
            "WLRE_ANDROID_KEYSTORE_READY account=TOP_SECRET\n"
            "AndroidRuntime: FATAL EXCEPTION token=hidden\n"
            "WLRE_ANDROID_STARTUP_ERROR A03 RuntimeError password=MORE_SECRET\n"
            "python traceback /data/user/0/secret/files/account\n"
        )
        safe = summarize_logcat(raw)
        for private in ("VERY_PRIVATE", "abcDEFGH", "TOP_SECRET",
                        "hidden", "MORE_SECRET", "/data/user/0/secret"):
            self.assertNotIn(private, safe)
        self.assertIn("WLRE_ANDROID_UI_READY", safe)
        self.assertIn("android_fatal_exception: 1", safe)
        self.assertIn("WLRE_ANDROID_STARTUP_ERROR A03 RuntimeError", safe)

    def test_service_dump_is_status_only_and_unknown_errors_are_censored(self):
        dump = "Service Intent extra PASSWORD=SHOULD_NOT_PUBLISH UID=10000"
        self.assertNotIn("SHOULD_NOT_PUBLISH", summarize_services(dump))
        safe = summarize_logcat(
            "WLRE_ANDROID_STARTUP_ERROR Z99 CryptoSecretPassword leaked=abc123"
        )
        self.assertNotIn("CryptoSecretPassword", safe)
        self.assertNotIn("abc123", safe)
        self.assertIn("WLRE_ANDROID_STARTUP_ERROR UNKNOWN Other", safe)
        self.assertIn("diagnostic unavailable", summarize_logcat("[diagnostic unavailable: exit 255]"))


if __name__ == "__main__":
    unittest.main()
