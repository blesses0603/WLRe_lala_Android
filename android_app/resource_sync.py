"""Android-owned preparation for the same official runtime as desktop.

One worker per process. Only the service downloads. The UI independently
validates and activates the shared, private cache before exposing game pages.
"""
import copy
import os
import re
import time
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
    from android_app.tls import configure_tls
    configure_tls(root)
    return root



def resource_message(report):
    """Show bounded network failure categories without exposing raw payloads."""
    message = str(report.get('message', '官方資料尚未通過驗證'))[:350]
    if report.get('block_reason') == 'runtime_unavailable':
        failure = report.get('runtime_failure')
        if type(failure) is dict:
            labels = {
                'required_bundle_missing': '必要 Bundle 尚未下載或快取未通過驗證',
                'required_bundle_invalid': '必要 Bundle 完整性驗證失敗',
                'runtime_parse_failed': '官方資料結構或解析程序不相容',
                'runtime_data_invalid': '完整 Runtime 的資料交叉驗證失敗',
                'manifest_identity_mismatch': '官方 Manifest 與 Runtime 身分不一致',
                'manifest_asset_missing': '目前 Manifest 缺少必要資源',
                'download_limit': '必要資源超過單次下載額度',
                'official_version_changed': '檢查期間官方資源版本發生變更',
                'runtime_identity_mismatch': 'Runtime 與官方登入版本不一致',
                'manifest_download_failed': '官方 Manifest 下載失敗',
                'manifest_parser_missing': '此版缺少官方 Manifest 解碼功能',
                'manifest_parse_failed': '官方 Manifest 結構無法解析',
                'manifest_validation_failed': '官方 Manifest 格式或完整性驗證失敗',
                'bundle_download_failed': '必要 Bundle 下載或同步中斷',
                'bundle_integrity_failed': 'Bundle 校驗或本機快取不一致',
                'bundle_plan_failed': '官方 Bundle 依賴規劃未通過驗證',
                'runtime_catalog_unavailable': '此版無法載入目前官方資源的完整 Runtime',
                'runtime_check_superseded': '已有更新的官方 Runtime 檢查取代本次檢查',
                'resource_io_failed': '官方資源或私人快取讀寫失敗',
                'runtime_check_failed': 'Runtime 檢查發生未分類錯誤',
            }
            code = failure.get('code')
            if type(code) is str and code in labels:
                message += '\n檢查原因：' + labels[code]
                from wlre.services.world.bundle_runtime_1275 import _REQUIRED_TABLES
                table = failure.get('table')
                if type(table) is str and table in _REQUIRED_TABLES:
                    message += '（' + table + '）'
                if code == 'manifest_download_failed':
                    # Stage and reason come only from a fixed allowlist;
                    # untrusted exception text, URLs and device paths stay out.
                    stage = failure.get('manifest_stage')
                    reason = failure.get('manifest_reason')
                    if stage in ('DataPackage.hash', 'DataPackage.bytes',
                                 'MainPackage.hash', 'MainPackage.bytes'):
                        message += '\n失敗檔案：' + stage
                        reasons = {
                            'tls_verify': 'TLS 憑證驗證失敗',
                            'tls_handshake': 'TLS 握手失敗',
                            'dns': 'DNS 無法解析官方網域',
                            'timeout': '連線逾時',
                            'refused': '官方伺服器拒絕連線',
                            'https': 'HTTPS 連線失敗',
                        }
                        if type(reason) is str and reason in reasons:
                            message += '；' + reasons[reason]
                        elif type(reason) is str:
                            import re
                            match = re.fullmatch(r'http_([1-5][0-9]{2})', reason)
                            if match:
                                message += '；官方 CDN 回應 HTTP ' + match.group(1)
        return message
    remote = report.get('remote')
    if report.get('login_allowed') is True or type(remote) is not dict:
        return message
    stage = remote.get('failed_stage')
    if stage not in ('ResourcePath_PC.dat', 'DataPackage.version', 'MainPackage.version'):
        return message
    reason = remote.get('reason')
    if stage != 'ResourcePath_PC.dat':
        packages = remote.get('packages')
        row = packages.get(stage.removesuffix('.version')) if type(packages) is dict else None
        reason = row.get('reason') if type(row) is dict else None
    # Never echo arbitrary remote/error strings into the login page or IPC.
    categories = {
        'TLS 憑證驗證失敗': 'TLS 憑證驗證失敗，請確認手機日期與網路憑證',
        'TLS 握手失敗': 'TLS 握手失敗，請切換網路後重試；不代表憑證一定失效',
        'TLS CA 設定失敗': 'TLS 信任憑證載入失敗，請確認 APK 安裝版本',
        'DNS 無法解析官方網域': 'DNS 無法解析官方網域，請確認目前網路',
        '連線逾時': '連線逾時，請稍後重新檢查',
        '官方伺服器拒絕連線': '官方伺服器拒絕連線',
        'HTTPS 連線失敗': 'HTTPS 連線失敗，請確認目前網路',
    }
    detail = categories.get(reason) if type(reason) is str else None
    if detail is None and type(reason) is str:
        import re
        match = re.fullmatch(r'HTTP ([1-5][0-9]{2})（官方 CDN 拒絕或找不到檔案）', reason)
        if match:
            detail = '官方 CDN 回應 HTTP ' + match.group(1)
    return message + '\n檢查階段：' + stage + '；' + (detail or '官方回應無法解析或版本資料不完整')


class ResourceSync:
    def __init__(self, *, download=True, preparer=None, checker=None):
        self.download = download
        self.preparer = preparer
        self.checker = checker
        self.lock = threading.Lock()
        self.worker = None
        self.value = dict(status='idle', ready=False, message='等待官方資料檢查',
                          progress_phase=None, package_versions={}, checked_at=None,
                          revision=0)
        self._preparation_issue = None

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
            self.value.update(status='checking', ready=False,
                              message='核對官方版本、Manifest 與資料庫',
                              progress_phase=None, package_versions={}, checked_at=None)
            self._preparation_issue = None
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
            message = resource_message(report)
            # Official package IDs are display-only and never unlock login.
            # A version identifier is not proof of a verified Bundle/Runtime.
            reported = report.get('baseline')
            versions = {}
            if type(reported) is dict:
                for name in ('DataPackage', 'MainPackage'):
                    value = reported.get(name)
                    if type(value) is str:
                        number = value.split('_', 1)[0]
                        if re.fullmatch(r'[0-9]{1,6}', number):
                            versions[name] = number
            if (not ready and self._preparation_issue == 'download_limit'
                    and report.get('block_reason') == 'runtime_unavailable'):
                message += '\n準備階段：必要 Bundle 超過單次下載上限（32 MiB／24 檔）'
            self._update(status='ready' if ready else 'blocked', ready=ready,
                         catalog_token=list(current_catalog_token()),
                         message=message, checked_at=int(time.time()),
                         package_versions=versions,
                         counts=report.get('record_counts', {}))
        except Exception as exc:
            # Exception messages can expose device paths and remote payloads.
            self._update(status='error', ready=False, checked_at=int(time.time()),
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
        if phase == 'runtime_bundle_unavailable':
            self._preparation_issue = (
                'download_limit' if type(details) is dict
                and details.get('code') == 'download_limit' else 'prepare_failed')
        if phase in labels:
            self._update(message=labels[phase], progress_phase=phase)

    def reset(self):
        with self.lock:
            if self.worker is not None and self.worker.is_alive(): return False
            self.value.update(status='idle', ready=False,
                              message='等待背景服務重新驗證',
                              progress_phase=None, package_versions={}, checked_at=None)
            self.value['revision'] += 1
            return True

    def require_ready(self):
        status = self.snapshot()
        if not status['ready']:
            raise ValueError(status['message'])
