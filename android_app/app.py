"""Minimal portrait, touch-operated Android login smoke-test UI."""
import queue
import time
from pathlib import Path

from kivy.app import App
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.utils import platform

from android_app.credentials import public_accounts, saved_password, store_account, delete_account
from android_app.sessions import SessionManager
from android_app.version import ANDROID_VERSION


# SDL2's bundled Roboto does not contain Chinese glyphs. Register the included
# OFL font for Labels, Buttons, Spinners and TextInputs before creating widgets.
FONT = str(Path(__file__).resolve().parent / 'assets/fonts/NotoSansTC-Regular.ttf')
LabelBase.register(DEFAULT_FONT, fn_regular=FONT, fn_bold=FONT,
                   fn_italic=FONT, fn_bolditalic=FONT)


def text_label(text, height=32):
    return Label(text=text, size_hint_y=None, height=dp(height),
                 halign="left", valign="middle")


class LaLaApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.manager = SessionManager()
        self.catalog_sync = None
        self.cards = {}
        self.dashboard = None
        self.lines = []
        self.vault = None
        self.saved_accounts = []
        self.vault_error = False
        self.android_initializing = False
        self.android_ready_reported = False
        self.overlay_permission_pending = False
        self.overlay_permission_checks = 0
        self._ui_started = False
        self._ui_restoring = False
        self._resume_restore_event = None
        self._drain_timer = None
        self._last_metrics_render = float('-inf')
        self._last_automation_render = float('-inf')
        self._login_view = None
        self._login_host = None
        self._login_visible = False
        self._verification_view = None
        self._verification_panel = None
        self._verification_brand_header = None
        self._login_brand_header = None
        self._verification_status = None
        self._verification_detail = None
        self._verification_retry = None
        self._pending_dashboard_restore = None

    def on_start(self):
        self._ui_started = True
        print('WLRE_ANDROID_UI_READY', flush=True)
        if platform == 'android':
            Clock.schedule_once(self.prepare_android, 0.5)

    def prepare_android(self, *_):
        try:
            from jnius import autoclass
            from android.permissions import check_permission, request_permissions
            permission = 'android.permission.POST_NOTIFICATIONS'
            if autoclass('android.os.Build$VERSION').SDK_INT >= 33 and not check_permission(permission):
                request_permissions([permission], lambda *_: Clock.schedule_once(self.initialize_android, 0.5))
                return
        except Exception:
            self.message.text = '通知權限請由系統設定開啟（A05）'
        self.initialize_android()

    def initialize_android(self, *_):
        if self.android_initializing: return
        self.android_initializing = True
        stage = 'A01'
        try:
            from jnius import autoclass
            from android_app.runtime import ServiceManager
            from android_app.vault import AndroidCipher, AccountVault
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            # Check the installed certificate/package BEFORE starting any
            # foreground connection service or opening the account vault.
            stage = 'A07'
            from android_app.integrity import require_integrity
            require_integrity(activity)
            directory = Path(str(activity.getNoBackupFilesDir().getAbsolutePath()))
            from android_app.resource_sync import configure_paths, ResourceSync
            configure_paths(activity)
            if self.catalog_sync is None:
                self.catalog_sync = ResourceSync(download=False)
            stage = 'A02'
            service = autoclass('org.lala.client.wlrelala.ServiceConnections')
            service.start(activity, '')
            self.android_service, self.android_activity = service, activity
            if not getattr(self.manager, 'background', False):
                self.manager = ServiceManager(directory / 'runtime/sessions.sock')
            stage = 'A03'
            try:
                cipher = AndroidCipher()
                import os
                probe = os.urandom(32)
                if cipher.decrypt(cipher.encrypt(probe)) != probe:
                    raise ValueError('Keystore roundtrip failed')
                self.vault = AccountVault(directory / 'accounts.enc', cipher)
                self.saved_accounts = public_accounts(self.vault.load())
                if hasattr(self, 'saved'):
                    self.saved.values = self.saved_names()
                if hasattr(self, 'remember'):
                    self.remember.disabled = False
                print('WLRE_ANDROID_KEYSTORE_READY', flush=True)
            except Exception:
                self.vault_error = True
                self.vault = None
                if hasattr(self, 'remember'):
                    self.remember.disabled = True
                self.message.text = '帳密解密／金鑰初始化失敗；原資料已保留，可不保存帳密登入（A03）'
        except Exception as exc:
            # Never show exception text: it may include credentials or paths.
            self.message.text = 'Android 服務初始化失敗：' + stage + ' / ' + type(exc).__name__
            print('WLRE_ANDROID_STARTUP_ERROR ' + stage + ' ' + type(exc).__name__, flush=True)
        finally:
            self.android_initializing = False

    def overlay_permission_granted(self):
        if platform != 'android': return False
        try:
            from jnius import autoclass
            return bool(autoclass('android.provider.Settings').canDrawOverlays(
                autoclass('org.kivy.android.PythonActivity').mActivity))
        except Exception:
            return False

    def toggle_overlay(self, *_):
        if platform != 'android' or not getattr(self.manager, 'background', False):
            return
        if not self.manager.available:
            self.message.text = '背景服務尚未就緒，請稍候'
            return
        enabled = not bool(getattr(self.manager, 'overlay_enabled', False))
        if enabled and not self.overlay_permission_granted():
            self.overlay_permission_pending = True
            self.overlay_permission_checks = 0
            try:
                from jnius import autoclass
                activity = autoclass('org.kivy.android.PythonActivity').mActivity
                intent = autoclass('android.content.Intent')(
                    'android.settings.action.MANAGE_OVERLAY_PERMISSION')
                uri = autoclass('android.net.Uri').parse(
                    'package:' + str(activity.getPackageName()))
                intent.setData(uri)
                activity.startActivity(intent)
                self.message.text = '請在系統設定允許「顯示在其他應用程式上層」；返回後啟用'
            except Exception:
                self.overlay_permission_pending = False
                self.message.text = '無法開啟授權頁，請到系統的特殊應用程式權限手動允許'
            return
        if self.manager.set_overlay(enabled):
            self.message.text = '正在更新懸浮小球設定；背景連線不會中斷'
        else:
            self.message.text = '懸浮小球設定失敗，請確認背景服務'

    def stop_android_service(self, *_):
        try:
            self.android_service.stop(self.android_activity)
        except Exception as exc:
            self.message.text = '停止服務失敗（A04 / ' + type(exc).__name__ + '）'


    def build(self):
        from android_app.theme import BACKGROUND
        self.title = "WLRe_LaLa Android v" + ANDROID_VERSION
        Window.softinput_mode = "below_target"
        Window.clearcolor = BACKGROUND
        login_view = self._build_login_view()
        if platform != 'android':
            return login_view
        self._login_view = login_view
        self._login_visible = False
        self._login_host = BoxLayout(orientation='vertical')
        self._verification_view = self._build_verification_view()
        self._login_host.add_widget(self._verification_view)
        return self._login_host

    def _build_verification_view(self):
        """Real-state seven-check neon screen; never bypass the login gate."""
        from android_app.verification_ui import VerificationDashboard

        panel = VerificationDashboard(
            self._retry_verification, self.initialize_android)
        self._verification_panel = panel
        self._verification_brand_header = panel.hero
        self._verification_status = panel.status
        self._verification_detail = panel.detail
        self._verification_retry = panel.retry
        return panel

    def _retry_verification(self, *_):
        self.retry_resources()
        if self._verification_detail is not None:
            self._verification_detail.text = self.message.text

    def _login_ready(self):
        from android_app.login_gate import verified_for_login
        local = self.catalog_sync.snapshot() if self.catalog_sync is not None else {}
        return verified_for_login(
            getattr(self.manager, 'resource_status', {}), local,
            connected=bool(getattr(self.manager, 'background', False)
                           and getattr(self.manager, 'available', False)))

    def _update_verification_gate(self):
        if platform != 'android' or self._login_host is None or self._login_visible:
            return
        service = getattr(self.manager, 'resource_status', {})
        local = self.catalog_sync.snapshot() if self.catalog_sync is not None else {}
        connected = bool(getattr(self.manager, 'background', False)
                         and getattr(self.manager, 'available', False))
        if self._login_ready():
            self._login_host.clear_widgets()
            self._login_host.add_widget(self._login_view)
            self._login_visible = True
            if self._login_brand_header is not None:
                self._login_brand_header.set_verified(True)
            pending = self._pending_dashboard_restore
            self._pending_dashboard_restore = None
            if pending is not None and pending[0] in self.manager.sessions:
                # Reattach the existing role workspace; never log in again.
                self.drain_events()
                self.open_dashboard(pending[0])
                if (self.dashboard is not None and pending[1]
                        and pending[1] != self.dashboard.page_name):
                    self.dashboard.navigation.text = pending[1]
            print('WLRE_ANDROID_LOGIN_GATE_VERIFIED', flush=True)
            return
        if not connected:
            self._verification_status.text = '等待背景服務'
            message = getattr(self.message, 'text', '')
            detail = (message if message.startswith(('Android 服務初始化失敗',
                                                     '通知權限'))
                      else '背景服務尚未就緒。可按「啟動／重新連接背景服務」。')
        elif service.get('status') == 'checking':
            self._verification_status.text = '檢查中：下載並核對官方資源'
            detail = service.get('message', '正在檢查雙 Manifest 與 Runtime')
        elif service.get('ready') is True:
            self._verification_status.text = (
                '手機端 Runtime／資料庫驗證未通過'
                if local.get('status') in ('blocked', 'error')
                else '官方資源已完成，核對手機端 Runtime／資料庫')
            detail = local.get('message', '正在驗證 Runtime 與 SQLite 資料庫')
        else:
            self._verification_status.text = '官方資源尚未通過驗證'
            detail = service.get('message', '等待官方資源檢查結果')
        if type(detail) is not str:
            detail = '檢查狀態暫時無法讀取'
        self._verification_detail.text = detail[:550]
        self._verification_panel.apply_state(
            service, local, connected=connected, detail=detail,
            login_ready=False)
        self._verification_retry.disabled = (
            not connected or service.get('status') == 'checking'
            or local.get('status') == 'checking'
            or getattr(self.manager, '_resource_request_pending', False))

    def _build_login_view(self):
        from android_app.widgets import column, label, button, row, RoundedSpinnerOption
        from android_app.theme import BACKGROUND, MUTED, ACCENT, SURFACE, SOFT, surface, style_button, style_input, style_checkbox
        from android_app.ui_shell import BrandHeader, section_title
        self.title = "WLRe_LaLa Android v" + ANDROID_VERSION
        Window.softinput_mode = "below_target"
        Window.clearcolor = BACKGROUND

        base = column()
        base.padding = [dp(16), dp(20), dp(16), dp(24)]
        base.spacing = dp(16)
        self._login_brand_header = BrandHeader(
            subtitle='帳號與連線', verified=False)
        base.add_widget(self._login_brand_header)

        login = surface(column(), radius=24); login.padding = dp(16); login.spacing = dp(12)
        login.add_widget(section_title(
            '帳號登入／連線管理', '選擇分流並安全建立多帳號連線'))
        self.saved = style_button(Spinner(text='已保存帳號', values=self.saved_names(),
                                          option_cls=RoundedSpinnerOption))
        self.saved.bind(text=self.switch_saved)
        delete = button('刪除', self.delete_saved)
        delete.size_hint_x = None; delete.width = dp(64)
        login.add_widget(row(self.saved, delete))
        from wlre.storage.server_lines import load
        self.lines = load()
        self.lookup = {entry["name"]: entry for entry in self.lines}
        choices = list(self.lookup)
        login.add_widget(label('伺服器與分流', 26))
        self.server = style_button(Spinner(text=choices[0] if choices else '沒有伺服器',
            values=choices, option_cls=RoundedSpinnerOption,
            size_hint_y=None, height=dp(48)))
        login.add_widget(self.server)
        login.add_widget(label('帳號', 26))
        self.account = style_input(TextInput(hint_text='輸入遊戲帳號', multiline=False,
            size_hint_y=None, height=dp(48), font_size='15sp'))
        login.add_widget(self.account)
        login.add_widget(label('密碼', 26))
        self.password = style_input(TextInput(hint_text='輸入密碼', multiline=False, password=True,
            size_hint_y=None, height=dp(48), font_size='15sp'))
        login.add_widget(self.password)
        self.remember = style_checkbox(CheckBox(active=False, size_hint_x=None,
            width=dp(44), disabled=self.vault is None))
        remember_text = label('加密保存帳密', 48)
        login.add_widget(row(self.remember, remember_text))
        # Official resource/SQLite verification belongs to the pre-login gate.
        # Existing sessions can still inspect service status in the monitor card.
        connect = button('建立新連線', self.connect_account, 56)
        style_button(connect, primary=True); login.add_widget(connect)
        self.message = label('選擇分流登入後，即可開啟角色功能。')
        self.message.color = MUTED
        if self.vault_error: self.message.text = '帳密解密失敗；原資料已保留，請重新輸入登入'
        login.add_widget(self.message)
        base.add_widget(login)

        base.add_widget(section_title(
            '連線中的帳號', '每個帳號可獨立管理角色與自動化功能'))
        self.empty_state = surface(BoxLayout(size_hint_y=None, height=dp(100), padding=dp(16)), radius=22)
        empty_text = label('尚未建立連線\n登入後，角色資訊與操作會顯示在這裡。')
        empty_text.color = MUTED
        self.empty_state.add_widget(empty_text)
        base.add_widget(self.empty_state)
        self.list_box = GridLayout(cols=1, spacing=dp(14), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        base.add_widget(self.list_box)

        monitor = surface(column(), radius=24); monitor.padding = dp(16); monitor.spacing = dp(12)
        monitor.add_widget(section_title(
            '資源狀態與連線服務', '顯示背景服務回報的實際狀態'))
        self.resources = label('資源監控：等待服務取樣')
        self.resources.font_size = '12sp'; self.resources.color = MUTED
        monitor.add_widget(self.resources)
        if platform == 'android':
            monitor.add_widget(label('背景連線需允許通知；可在此管理服務。'))
            monitor.add_widget(button('啟動背景服務', self.initialize_android))
            self.overlay_button = button('開啟懸浮小球（需額外授權）', self.toggle_overlay)
            self.overlay_button.disabled = True
            monitor.add_widget(self.overlay_button)
            monitor.add_widget(label('懸浮小球顯示角色／夥伴、HP／SP、戰鬥、徘徊與事件；可隨時關閉。'))
            stop = button('停止全部連線與服務', self.stop_android_service)
            style_button(stop, danger=True); monitor.add_widget(stop)
        base.add_widget(monitor)
        self.list_box.bind(children=self.update_empty_state)
        if self._drain_timer is not None:
            self._drain_timer.cancel()
        self._drain_timer = Clock.schedule_interval(self.drain_events, 0.25)
        outer = ScrollView(do_scroll_x=False, bar_width=dp(3))
        outer.add_widget(base)
        self._main_content = base
        return outer

    def update_empty_state(self, *_):
        empty = not self.list_box.children
        self.empty_state.opacity = 1 if empty else 0
        self.empty_state.height = dp(100) if empty else 0
        self.empty_state.size_hint_y = None

    def retry_resources(self, *_):
        if not hasattr(self.manager, 'retry_resources'):
            return
        if any(s.active for s in self.manager.sessions.values()):
            self.message.text = '請先停止所有連線，再更新官方資料'
            return
        if (self.catalog_sync is not None
                and self.catalog_sync.snapshot()['status'] == 'checking'):
            self.message.text = '手機端正在驗證官方資源，請等待本次檢查完成'
            return
        if not self.manager.retry_resources():
            status = getattr(self.manager, 'resource_status', {}).get('status')
            self.message.text = (
                '背景服務正在核對官方資源，請等待本次檢查完成'
                if status == 'checking' else
                '背景服務尚未就緒或已有檢查請求排隊，請稍後重試')
            return
        if self.catalog_sync is not None:
            self.catalog_sync.reset()
        self.message.text = '已要求背景服務重新檢查官方資源'

    def connect_account(self, *_):
        if platform == 'android' and (not self._login_visible or not self._login_ready()):
            self.message.text = (self.catalog_sync.snapshot()['message']
                                 if self.catalog_sync is not None
                                 else '等待官方 Runtime 與資料庫驗證完成')
            return
        if getattr(self, 'catalog_sync', None) is not None and (not self.catalog_sync.snapshot()['ready']
                or not getattr(self.manager, 'resource_status', {}).get('ready')
                or self.catalog_sync.snapshot().get('catalog_token') != getattr(self.manager, 'resource_status', {}).get('catalog_token')):
            self.message.text = self.catalog_sync.snapshot()['message']; return
        if platform == 'android' and not getattr(self.manager, 'background', False):
            self.message.text = '背景服務未就緒，請點擊啟動背景服務'
            return
        record = self.lookup.get(self.server.text)
        account = self.account.text.strip()
        password = self.password.text
        if not record or not account or not password:
            self.message.text = "請選擇分流並輸入帳號、密碼"
            return
        self.password.text = ""
        if self.remember.active and self.vault:
            try:
                self.saved_accounts = store_account(
                    self.vault, self.server.text, account, password
                )
                self.saved.values = self.saved_names()
            except Exception:
                self.message.text = '安全保存失敗，未建立連線'
                return
        try:
            session = self.manager.start(
                label=self.server.text, host=record["host"], port=record["port"],
                account=account, password=password)
        except ValueError as exc:
            self.message.text = str(exc)
            return
        self.message.text = "已建立新連線；可繼續新增其他帳號"
        if session is not None: self.add_card(session)

    def add_card(self, session):
        account = session.account
        from android_app.widgets import column, label
        from android_app.theme import MUTED, surface, style_button
        card = surface(column(), radius=22)
        card.padding = dp(16); card.spacing = dp(10)
        title = label(account + "｜" + session.label)
        title.font_size = '17sp'
        status = label('準備連線')
        status.color = MUTED
        controls = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        choices = {}
        for index in (1, 2):
            choice = style_button(Button(text="角色 " + str(index), disabled=True))
            choice.bind(on_release=lambda _button, sid=session.session_id, n=index:
                        self.choose_role(sid, n))
            controls.add_widget(choice)
            choices[index] = choice
        stop = style_button(Button(text="停止"), danger=True)
        stop._lala_stop_callback = lambda _button, sid=session.session_id: self.manager.stop(sid)
        stop.bind(on_release=stop._lala_stop_callback)
        controls.add_widget(stop)
        card.add_widget(title)
        card.add_widget(status)
        card.add_widget(controls)
        from android_app.widgets import button as mobile_button
        launch = mobile_button(
            '開啟角色功能', lambda sid=session.session_id: self.open_dashboard(sid), 54)
        style_button(launch, primary=True)
        card.add_widget(launch)
        from android_app.automation_ui import attach
        attach(self, card, session.session_id)
        self.list_box.add_widget(card)
        self.cards[session.session_id] = (status, choices, title, stop, card)

    def open_dashboard(self, sid):
        if self.catalog_sync is not None and not self.catalog_sync.snapshot()['ready']:
            self.message.text = '等待手機介面完成官方資料驗證'; return
        if self.dashboard: self.dashboard.close()
        from android_app.dashboard import Dashboard
        self.dashboard = Dashboard(self, sid)

    def saved_names(self):
        return [r['account'] + ' | ' + r['server'] for r in self.saved_accounts]

    def switch_saved(self, _spinner, name):
        # Previously the Activity cached ALL decrypted passwords indefinitely.
        # Keep only the selected password inside the UI input until used/paused.
        self.password.text = ''
        for record, label in zip(self.saved_accounts, self.saved_names()):
            if label == name:
                if self.vault is None:
                    self.message.text = '帳密保管庫未就緒，請手動輸入密碼'
                    return
                try:
                    secret = saved_password(self.vault, record['server'], record['account'])
                except Exception:
                    self.message.text = '讀取保存帳密失敗，請手動輸入密碼'
                    return
                self.account.text = record['account']
                self.server.text = record['server']
                self.password.text = secret
                return

    def delete_saved(self, *_):
        if not self.vault: return
        chosen = next((r for r, label in zip(self.saved_accounts, self.saved_names())
                       if label == self.saved.text), None)
        if chosen is None: return
        try:
            self.saved_accounts = delete_account(
                self.vault, chosen['server'], chosen['account'])
        except Exception:
            self.message.text = '安全刪除失敗，原資料已保留'
            return
        self.saved.values = self.saved_names()
        self.saved.text = '已保存帳號'
        self.password.text = ''
        self.message.text = '已刪除保存的帳密；既有連線可個別停止'

    def choose_role(self, session_id, index):
        if self.manager.select_role(session_id, index):
            record = self.cards.get(session_id)
            if record:
                record[0].text = "正在登入角色"
                for button in record[1].values(): button.disabled = True

    def remove_card(self, session_id):
        if self.manager.remove(session_id):
            record = self.cards.pop(session_id, None)
            if record: self.list_box.remove_widget(record[4])

    def drain_events(self, *_):
        # Keep IPC event handling responsive (4 Hz), but avoid expensive
        # Android Debug.getMemoryInfo calls and card redraws on every tick.
        now = time.monotonic()
        if getattr(self.manager, 'background', False):
            resource = getattr(self.manager, 'resource_status', {})
            sync = self.catalog_sync
            if sync is not None:
                local = sync.snapshot()
                if (getattr(self.manager, 'available', False)
                        and resource.get('ready') and local['status'] == 'idle'):
                    sync.start()
            self._update_verification_gate()
            if hasattr(self, 'overlay_button'):
                self.overlay_button.disabled = not self.manager.available
                self.overlay_button.text = ('關閉懸浮小球' if
                    getattr(self.manager, 'overlay_enabled', False) else
                    '開啟懸浮小球（需額外授權）')
            for session in list(self.manager.sessions.values()):
                if session.session_id not in self.cards: self.add_card(session)
            metrics = self.manager.metrics
            if not self.manager.available:
                self.resources.text = '服務無回應／已停止；連線狀態未知，請重啟服務'
                for record in self.cards.values():
                    record[0].text = '服務無回應；連線狀態未知'
                    for button in record[1].values(): button.disabled = True
            elif metrics:
                if not self.android_ready_reported:
                    print('WLRE_ANDROID_SERVICE_CONNECTED', flush=True)
                    self.android_ready_reported = True
                if now - self._last_metrics_render >= 2.0:
                    try:
                        self.render_metrics(metrics)
                    except Exception:
                        self.resources.text = '資源監控暫時無法讀取（A06）；連線由服務管理'
                    finally:
                        self._last_metrics_render = now
        for _ in range(80):
            try:
                sid, kind, value = self.manager.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'error':
                self.message.text = value
                continue
            if kind == 'removed':
                record = self.cards.pop(sid, None)
                if record: self.list_box.remove_widget(record[4])
                continue
            record = self.cards.get(sid)
            if not record:
                continue
            session = self.manager.sessions.get(sid)
            if session is None: continue
            status, choices, title, stop, card = record
            if kind == 'chat_ack':
                if self.dashboard and self.dashboard.sid == sid: self.dashboard.chat_ack(value)
            elif kind == "notice":
                self.message.text = value
                if self.dashboard and self.dashboard.sid == sid: self.dashboard.message.text = value
            elif kind == "status":
                status.text = value
                if session.stop_event.is_set():
                    for button in choices.values(): button.disabled = True
            elif kind == "roles":
                for index, button in choices.items():
                    role = next((r for r in value if r["index"] == index), None)
                    button.disabled = (role is None or bool(role.get("locked")) or not session.active
                        or session.stop_event.is_set() or session.selection_pending
                        or session.phase != "role_selection")
                    suffix = "（無法使用）" if role and role.get("locked") else ""
                    level = role.get("level") if role else None
                    button.text = "角色 " + str(index) + (" Lv." + str(level) if level is not None else "") + suffix
            elif kind == "snapshot":
                if value["phase"] != "role_selection":
                    for button in choices.values(): button.disabled = True
                if value["character"]:
                    def known(key): return str(value[key]) if value.get(key) is not None else "—"
                    point = value.get("position")
                    location = (point.get("label", "角色位置") + "：" + str(point["x"]) + ", " + str(point["y"])) if point else "位置待同步"
                    status.text = ("角色 " + value["character"] + " Lv." + known("level") +
                        "\nHP " + known("hp") + "/" + known("max_hp") + "  SP " + known("sp") + "/" + known("max_sp") +
                        "\n地圖 " + known("scene") + "｜" + location)
            elif kind == "finished":
                status.text = value
                for button in choices.values(): button.disabled = True
                stop.unbind(on_release=stop._lala_stop_callback)
                stop.text = "移除"
                stop.bind(on_release=lambda _button, session_id=sid: self.remove_card(session_id))
        if now - self._last_automation_render >= 1.0:
            from android_app.automation_ui import refresh
            for sid in self.cards:
                refresh(self, sid)
            self._last_automation_render = now
        return True

    def render_metrics(self, metrics):
        if metrics.get('monitor_error'):
            self.resources.text = '裝置資源監控暫時失效，遊戲連線仍由背景服務管理'
            return
        import time
        from jnius import autoclass
        memory = autoclass('android.os.Debug$MemoryInfo')()
        autoclass('android.os.Debug').getMemoryInfo(memory)
        self.resources.text = ('在線 {online}／活動連線 {active}｜服務 PSS {service_pss_kib} KiB'.format(**metrics)
            + '\n畫面 PSS ' + str(memory.getTotalPss()) + ' KiB｜裝置電量 ' + str(metrics.get('battery_percent') if metrics.get('battery_percent') is not None else '未知')
            + '%｜裝置溫度 ' + str(metrics.get('device_temperature_c') if metrics.get('device_temperature_c') is not None else '未知') + '°C｜App 耗電未知｜' + time.strftime('%H:%M:%S', time.localtime(metrics['sample_time'])))

    def on_pause(self):
        if hasattr(self, 'password'):
            self.password.text = ""
        if hasattr(self.manager, 'set_paused'): self.manager.set_paused(True)
        if not getattr(self.manager, 'background', False): self.manager.stop_all()
        return True

    def finish_overlay_permission(self, *_):
        if not self.overlay_permission_pending: return
        if not self.overlay_permission_granted():
            self.overlay_permission_pending = False
            self.message.text = '未取得懸浮視窗權限，原有背景連線不受影響'
            return
        if (getattr(self.manager, 'background', False) and
                getattr(self.manager, 'available', False) and
                self.manager.set_overlay(True)):
            self.overlay_permission_pending = False
            self.message.text = '已送出懸浮小球啟用要求'
        elif self.overlay_permission_checks < 16:
            self.overlay_permission_checks += 1
            Clock.schedule_once(self.finish_overlay_permission, 0.5)
        else:
            self.overlay_permission_pending = False
            self.message.text = '服務尚未就緒，請稍後再開啟懸浮小球'

    def _restore_foreground_ui(self, *_):
        """Restore Kivy's visible widget tree; never restart game sessions."""
        self._resume_restore_event = None
        if not self._ui_started or self._ui_restoring or self.root is None:
            return
        self._ui_restoring = True
        old_root = self.root
        old_cards = self.cards
        old_dashboard = self.dashboard
        account = self.account.text
        server = self.server.text
        message = self.message.text
        remember = bool(self.remember.active)
        scroll_view = (self._login_view
                       if platform == 'android' and self._login_view is not None
                       else old_root)
        scroll_y = scroll_view.scroll_y if isinstance(scroll_view, ScrollView) else 1
        dashboard_sid = old_dashboard.sid if old_dashboard and not old_dashboard.closed else None
        dashboard_page = old_dashboard.page_name if dashboard_sid else None
        try:
            # A long background pause can leave SDL's foreground widget tree
            # detached or unpainted even while the independent service survives.
            if old_dashboard:
                old_dashboard.close()
                old_dashboard.dismissed()
            new_root = self.build()
            Window.add_widget(new_root)
            if old_root in Window.children:
                Window.remove_widget(old_root)
            self.root = new_root
            self.cards = {}
            if server in self.lookup:
                self.server.text = server
            self.account.text = account
            self.password.text = ''  # Never restore a password after backgrounding.
            self.remember.active = remember and not self.remember.disabled
            self.message.text = message
            if platform == 'android' and self._login_view is not None:
                self._login_view.scroll_y = scroll_y
                self._pending_dashboard_restore = (
                    (dashboard_sid, dashboard_page) if dashboard_sid else None)
                self._update_verification_gate()
            else:
                new_root.scroll_y = scroll_y
            # Recreate cards from the existing service snapshot, without login.
            self.drain_events()
            if (platform != 'android' and dashboard_sid in self.manager.sessions):
                self.open_dashboard(dashboard_sid)
                if dashboard_page and dashboard_page != self.dashboard.page_name:
                    self.dashboard.navigation.text = dashboard_page
            new_root.canvas.ask_update()
            Window.canvas.ask_update()
            print('WLRE_ANDROID_UI_RESTORED', flush=True)
        except Exception as exc:
            # Do not log credentials or exception messages.
            print('WLRE_ANDROID_UI_RESTORE_ERROR ' + type(exc).__name__, flush=True)
            if old_root not in Window.children and old_root.parent is None:
                Window.add_widget(old_root)
            if self.root is old_root:
                self.cards = old_cards
        finally:
            self._ui_restoring = False

    def on_resume(self):
        if hasattr(self.manager, 'set_paused'): self.manager.set_paused(False)
        if self._resume_restore_event is not None:
            self._resume_restore_event.cancel()
        # Wait for the Android GL surface to become usable before reattaching UI.
        self._resume_restore_event = Clock.schedule_once(self._restore_foreground_ui, 0.15)
        if self.overlay_permission_pending:
            Clock.schedule_once(self.finish_overlay_permission, 0.7)

    def on_stop(self):
        if hasattr(self, 'password'):
            self.password.text = ""
        if not getattr(self.manager, 'background', False): self.manager.stop_all()

