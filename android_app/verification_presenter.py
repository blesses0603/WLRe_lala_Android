"""Pure status presenter for the Android pre-login verification screen.

Never infer a green check from a version string or a downloaded file.
A final success requires the same strict service + local token gate as login.
"""
import re
from datetime import datetime

from android_app.login_gate import verified_for_login

CHECKS = (
    ('version', '官方版本', '確認官方遊戲與資源識別'),
    ('data', 'DataPackage', '驗證資料包版本與官方識別'),
    ('main', 'MainPackage', '驗證主程式資源識別'),
    ('manifest', 'Manifest', '核對主／資料雙 Manifest'),
    ('bundle', 'Bundle', '驗證必要資源與檔案完整性'),
    ('runtime', 'Runtime', '啟動並核對完整 Runtime'),
    ('sqlite', 'SQLite', '核對本機資料庫及 Catalog 身分'),
)

# Only documented preparer milestones are allowed to advance a row.
IDENTITY_PHASES = frozenset((
    'runtime_identity_verified', 'runtime_bundle_plan',
    'bundle_sync', 'bundle_verify', 'runtime_bundle_ready',
    'extract',
))
BUNDLE_PHASES = frozenset(('runtime_bundle_ready', 'extract'))
LOADING_PHASES = frozenset((
    'runtime_bundle_plan', 'bundle_sync', 'bundle_verify',
    'runtime_bundle_ready', 'extract',
))
CLOSED_STATUSES = frozenset(('blocked', 'error'))


def _versions(service):
    reported = service.get('package_versions')
    values = {}
    if type(reported) is not dict:
        return values
    for name in ('DataPackage', 'MainPackage'):
        value = reported.get(name)
        if type(value) is str and re.fullmatch(r'[0-9]{1,6}', value):
            values[name] = value
    return values


def verification_view_state(service, local, *, connected):
    """Return safe display-only statuses, with no raw exceptions or URLs."""
    service = service if type(service) is dict else {}
    local = local if type(local) is dict else {}
    connected = connected is True
    complete = verified_for_login(service, local, connected=connected)
    phase = service.get('progress_phase')
    stage_status = ['waiting'] * len(CHECKS)
    service_ready = (connected and service.get('status') == 'ready'
                     and service.get('ready') is True)

    if complete:
        stage_status = ['success'] * len(CHECKS)
    elif service_ready:
        # The background service verified the entire runtime/database; the
        # Activity still needs to match the catalog identity independently.
        stage_status = ['success'] * (len(CHECKS) - 1) + ['checking']
        if local.get('status') in CLOSED_STATUSES:
            stage_status[-1] = 'error'
    elif connected and service.get('status') in ('checking', 'blocked'):
        if phase in IDENTITY_PHASES:
            stage_status[:4] = ['success'] * 4
        if phase in BUNDLE_PHASES:
            stage_status[4] = 'success'
            stage_status[5] = 'checking'
        elif phase in LOADING_PHASES:
            stage_status[4] = 'checking'
        elif phase not in IDENTITY_PHASES:
            stage_status[0] = 'checking'
        if service.get('status') == 'blocked':
            # Do not blame a particular stage without a trusted failure
            # code. The overall result reports the failure below instead.
            stage_status = ['waiting' if v == 'checking' else v
                            for v in stage_status]
    elif connected and service.get('status') == 'error':
        pass

    checking = (connected and (service.get('status') == 'checking'
               or (service_ready and not complete
                   and local.get('status') not in CLOSED_STATUSES)))
    failed = (connected and (service.get('status') in CLOSED_STATUSES
              or (service_ready and local.get('status') in CLOSED_STATUSES)))
    if complete:
        overall = 'success'
        headline = '所有項目驗證通過'
    elif failed:
        overall = 'error'
        headline = '官方資源驗證未通過'
    elif checking:
        overall = 'checking'
        headline = '檢查中：正在核對官方資源'
    else:
        overall = 'waiting'
        headline = '等待背景服務與資源驗證'

    raw_message = (local.get('message') if service_ready and not complete
                   else service.get('message'))
    detail = (raw_message[:350] if type(raw_message) is str and raw_message
              else '等待官方資料檢查結果')
    when = service.get('checked_at')
    # Reject timestamps outside a bounded realistic range; do not forge time.
    if type(when) in (int, float) and 1600000000 <= when <= 4102444800:
        try:
            timestamp = datetime.fromtimestamp(when).strftime('%Y-%m-%d %H:%M:%S')
        except (OverflowError, OSError, ValueError):
            timestamp = '尚無紀錄'
    else:
        timestamp = '尚無紀錄'
    return {
        'steps': tuple(stage_status),
        'overall': overall,
        'headline': headline,
        'detail': detail,
        'versions': _versions(service),
        'checked_at': timestamp,
        'connected': connected,
        'complete': complete,
    }
