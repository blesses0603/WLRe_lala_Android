"""Android-owned preparation for the same official runtime as desktop.

One worker per process. Only the service downloads. The UI independently
validates and activates the shared, private cache before exposing game pages.
"""
import copy
import os
from pathlib import Path
import threading


def configure_paths(context=None):
    if context is None:
        if 'ANDROID_ARGUMENT' not in os.environ:
            return None
        from jnius import autoclass
        context = autoclass('org.kivy.android.PythonService').mService
        if context is None:
            context = autoclass('org.kivy.android.PythonActivity').mActivity
    if context is None:
        raise RuntimeError('Android 私人資料目錄尚未就緒')
    root = Path(str(context.getNoBackupFilesDir().getAbsolutePath()))
    os.environ['LOCALAPPDATA'] = str(root)
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    return root


class ResourceSync:
    def __init__(self, *, download=True, preparer=None, checker=None):
        self.download = download
        self.preparer = preparer
        self.checker = checker
        self.lock = threading.Lock()
        self.worker = None
        self.value = dict(status='idle', ready=False, message='等待官方資料檢查', revision=0)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def _update(self, **values):
        with self.lock:
            self.value.update(values)
            self.value['revision'] += 1

    def start(self):
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                return False
            self.value.update(status='checking', ready=False, message='核對官方版本、Manifest 與資料庫')
            self.value['revision'] += 1
            self.worker = threading.Thread(target=self._run, name='official-resource-sync', daemon=True)
            self.worker.start()
            return True

    def _run(self):
        try:
            if self.download:
                if self.preparer is None:
                    from wlre.services.world.launcher_catalog import prepare_on_launch
                    self.preparer = prepare_on_launch
                self.preparer(progress=self._progress)
            if self.checker is None:
                from wlre.services.game_version_gate import run_prelogin_check
                self.checker = run_prelogin_check
            report = self.checker()
            # A version string or a launcher receipt cannot unlock login.
            ready = (report.get('login_allowed') is True and
                     report.get('database_verified') is True and
                     report.get('blocked') is False)
            from wlre.services.world.dynamic_bundle_runtime import current_catalog_token
            self._update(status='ready' if ready else 'blocked', ready=ready,
                         catalog_token=list(current_catalog_token()),
                         message=str(report.get('message', '官方資料尚未通過驗證'))[:500],
                         counts=report.get('record_counts', {}))
        except Exception as exc:
            # Exception messages can expose device paths and remote payloads.
            self._update(status='error', ready=False,
                         message='官方資料準備失敗（'+type(exc).__name__+'）；請重新檢查')

    def _progress(self, phase, details):
        labels = {
            'runtime_identity_verified': '官方版本與雙 Manifest 已核對',
            'runtime_bundle_plan': '準備官方功能資源',
            'runtime_bundle_ready': '官方 Runtime 已載入，繼續核對資料庫',
            'extract': '解析官方功能資料',
            'bundle_sync': '下載及校驗必要資源',
            'bundle_verify': '驗證官方資源內容',
        }
        if phase in labels:
            self._update(message=labels[phase])

    def reset(self):
        with self.lock:
            if self.worker is not None and self.worker.is_alive(): return False
            self.value.update(status='idle', ready=False, message='等待背景服務重新驗證')
            self.value['revision'] += 1
            return True

    def require_ready(self):
        status = self.snapshot()
        if not status['ready']:
            raise ValueError(status['message'])
