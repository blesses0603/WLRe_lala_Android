"""Minimal portrait, touch-operated Android login smoke-test UI."""
import queue
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

    def on_start(self):
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
            directory = Path(str(activity.getNoBackupFilesDir().getAbsolutePath()))
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
                self.saved_accounts = self.vault.load()
                self.saved.values = self.saved_names()
                self.remember.disabled = False
                print('WLRE_ANDROID_KEYSTORE_READY', flush=True)
            except Exception:
                self.vault_error = True
                self.vault = None
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
        from android_app.widgets import column, label, button, row, RoundedSpinnerOption
        from android_app.theme import BACKGROUND, MUTED, ACCENT, SURFACE, SOFT, surface, style_button, style_input, style_checkbox
        self.title = "WLRe_LaLa Android v" + ANDROID_VERSION
        Window.softinput_mode = "below_target"
        Window.clearcolor = BACKGROUND

        base = column()
        base.padding = [dp(16), dp(20), dp(16), dp(24)]
        base.spacing = dp(16)
        header = surface(BoxLayout(size_hint_y=None, height=dp(96), spacing=dp(12),
                                  padding=dp(12)), color=SURFACE, radius=24)
        icon = Image(source=str(Path(__file__).resolve().parent / 'assets/app.png'),
                     size_hint_x=None, width=dp(68))
        header.add_widget(icon)
        header_text = BoxLayout(orientation='vertical', spacing=dp(2))
        title = label('飄流 RE:LaLa', 42)
        title.font_size = '25sp'; title.color = ACCENT
        header_text.add_widget(title)
        subtitle = label('ANDROID  ·  v' + ANDROID_VERSION + '  /  多帳號管理', 26)
        subtitle.color = MUTED; subtitle.font_size = '12sp'
        header_text.add_widget(subtitle)
        header.add_widget(header_text)
        base.add_widget(header)

        login = surface(column(), radius=24); login.padding = dp(16); login.spacing = dp(12)
        heading = label('登入遊戲', 32); heading.font_size = '19sp'
        login.add_widget(heading)
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
        connect = button('新增連線並登入', self.connect_account, 52)
        style_button(connect, primary=True); login.add_widget(connect)
        self.message = label('選擇分流登入後，即可開啟角色功能。')
        self.message.color = MUTED
        if self.vault_error: self.message.text = '帳密解密失敗；原資料已保留，請重新輸入登入'
        login.add_widget(self.message)
        base.add_widget(login)

        base.add_widget(label('帳號連線', 32))
        self.empty_state = surface(BoxLayout(size_hint_y=None, height=dp(100), padding=dp(16)), radius=22)
        empty_text = label('尚未建立連線\n登入後，角色資訊與操作會顯示在這裡。')
        empty_text.color = MUTED
        self.empty_state.add_widget(empty_text)
        base.add_widget(self.empty_state)
        self.list_box = GridLayout(cols=1, spacing=dp(14), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        base.add_widget(self.list_box)

        monitor = surface(column(), radius=24); monitor.padding = dp(16); monitor.spacing = dp(12)
        monitor.add_widget(label('服務與資源', 30))
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
        Clock.schedule_interval(self.drain_events, 0.25)
        outer = ScrollView(do_scroll_x=False, bar_width=dp(3))
        outer.add_widget(base)
        return outer

    def update_empty_state(self, *_):
        empty = not self.list_box.children
        self.empty_state.opacity = 1 if empty else 0
        self.empty_state.height = dp(100) if empty else 0
        self.empty_state.size_hint_y = None

    def connect_account(self, *_):
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
            records = [r for r in self.saved_accounts if (r['server'], r['account']) != (self.server.text, account)]
            records.append(dict(server=self.server.text, account=account, password=password))
            try:
                self.vault.save(records)
                self.saved_accounts = records
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
        card.add_widget(mobile_button('開啟角色功能', lambda sid=session.session_id: self.open_dashboard(sid)))
        from android_app.automation_ui import attach
        attach(self, card, session.session_id)
        self.list_box.add_widget(card)
        self.cards[session.session_id] = (status, choices, title, stop, card)

    def open_dashboard(self, sid):
        if self.dashboard: self.dashboard.close()
        from android_app.dashboard import Dashboard
        self.dashboard = Dashboard(self, sid)

    def saved_names(self):
        return [r['account'] + ' | ' + r['server'] for r in self.saved_accounts]

    def switch_saved(self, _spinner, name):
        for record, label in zip(self.saved_accounts, self.saved_names()):
            if label == name:
                self.account.text = record['account']
                self.server.text = record['server']
                self.password.text = record['password']
                return

    def delete_saved(self, *_):
        if not self.vault: return
        records = [r for r, label in zip(self.saved_accounts, self.saved_names()) if label != self.saved.text]
        try: self.vault.save(records)
        except Exception:
            self.message.text = '安全刪除失敗，原資料已保留'
            return
        self.saved_accounts = records
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
        if getattr(self.manager, 'background', False):
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
                try:
                    self.render_metrics(metrics)
                except Exception:
                    self.resources.text = '資源監控暫時無法讀取（A06）；連線由服務管理'
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
        from android_app.automation_ui import refresh
        for sid in self.cards: refresh(self, sid)
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

    def on_resume(self):
        if hasattr(self.manager, 'set_paused'): self.manager.set_paused(False)
        if self.overlay_permission_pending:
            Clock.schedule_once(self.finish_overlay_permission, 0.7)

    def on_stop(self):
        self.password.text = ""
        if not getattr(self.manager, 'background', False): self.manager.stop_all()
