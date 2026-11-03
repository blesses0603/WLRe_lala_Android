"""One account's mobile workspace, reattaches to foreground service state."""
from importlib import import_module
import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from android_app.widgets import button, label, select, column, GameIconTab, RoundedSpinnerOption
from android_app.theme import TEXT, SURFACE, ACCENT, MUTED, SOFT, surface, style_button
from android_app.refresh_policy import RefreshPolicy

PAGES = ('角色概況', '包包與特技', '小地圖', '戰場陣形', '聊天', '組隊',
         '夥伴出戰', '遠征', '副本資料', '角色能力', '煉金', '製作', '經驗效率', '事件紀錄', 'AI與補給設定', 'NPC', '儲藏存取', '福利')

# Lazy imports: importing every page on the first tab switch pulls in maps,
# resource catalogs and image helpers on the Kivy UI thread.
_PAGE_IMPL = {
    '角色概況': ('general', 'Overview'),
    '包包與特技': ('resources', 'Resources'),
    '小地圖': ('map', 'MapPage'),
    '戰場陣形': ('resources', 'Battle'),
    '聊天': ('social', 'Chat'),
    '組隊': ('social', 'Party'),
    '夥伴出戰': ('companions', 'Companions'),
    '遠征': ('expedition', 'Expedition'),
    '副本資料': ('instances', 'InstanceCatalog'),
    '角色能力': ('attributes', 'Attributes'),
    '煉金': ('production', 'Alchemy'),
    '製作': ('production', 'Crafting'),
    '經驗效率': ('general', 'Efficiency'),
    '事件紀錄': ('general', 'Events'),
    'AI與補給設定': ('settings', 'SettingsPage'),
    'NPC': ('npc', 'NPC'),
    '儲藏存取': ('storage', 'Storage'),
    '福利': ('benefits', 'Benefits'),
}
if set(_PAGE_IMPL) != set(PAGES):
    raise RuntimeError('Android page mapping is incomplete')


class Dashboard:
    def __init__(self, app, sid):
        self.app, self.sid = app, sid
        self.data = {}; self.page = None; self.page_name = None; self.signature = None
        self.closed = False
        self.last_npc_effect = None
        self.views = {}
        self._refresh_policy = RefreshPolicy()
        self._local_data_revision = 0
        session = app.manager.sessions[sid]
        base = surface(BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(12)),
                       color=SURFACE, radius=24)
        self.status = surface(label('等待服務同步'), color=SOFT, radius=12)
        self.status.color = MUTED; base.add_widget(self.status)
        # Compact function chooser avoids a tall overlapping selector.
        nav = surface(BoxLayout(orientation='horizontal', size_hint_y=None,
                      height=dp(58), spacing=dp(8), padding=[dp(10), dp(7)]),
                      color=SOFT, radius=16)
        heading = label('功能', 44)
        heading.size_hint_x = None; heading.width = dp(48)
        nav.add_widget(heading)
        self.navigation = style_button(Spinner(text=PAGES[0], values=PAGES,
            option_cls=RoundedSpinnerOption, size_hint_y=None, height=dp(44)))
        nav.add_widget(self.navigation); base.add_widget(nav)
        # Original game icons replace desktop multi-window navigation with a
        # horizontally scrollable, one-hand-friendly Android quick launcher.
        shortcuts = ('角色概況', '包包與特技', '組隊', '夥伴出戰',
                     '遠征', '副本資料', '角色能力', '煉金', '製作', '經驗效率', 'AI與補給設定')
        shortcut_scroll = ScrollView(
            do_scroll_y=False, do_scroll_x=True,
            bar_width=dp(2), size_hint_y=None, height=dp(73))
        shortcut_row = BoxLayout(
            size_hint_x=None, width=dp(80)*len(shortcuts),
            size_hint_y=None, height=dp(70), spacing=dp(4))
        for title in shortcuts:
            shortcut_row.add_widget(GameIconTab(
                title, lambda name: setattr(self.navigation, 'text', name)))
        shortcut_scroll.add_widget(shortcut_row)
        base.add_widget(shortcut_scroll)
        self.content = BoxLayout(orientation='vertical'); base.add_widget(self.content)
        self.message = label(); self.message.color = MUTED; base.add_widget(self.message)
        base.add_widget(button('返回帳號列表', self.close))
        self.popup = Popup(title=session.account+'｜'+session.label, content=base,
                           size_hint=(.98, .97), background='', background_color=(0, 0, 0, 0),
                           title_color=TEXT, separator_color=ACCENT)
        self.popup.bind(on_dismiss=lambda *_: self.dismissed())
        self.navigation.bind(text=lambda _, value: self.show(value))
        if hasattr(app.manager, 'watch'): app.manager.watch(sid)
        self.timer = Clock.schedule_interval(self.tick, .5)
        self.show(PAGES[0]); self.popup.open(); self.tick()

    @property
    def state(self): return self.data.get('state', {})

    @property
    def catalog_ready(self):
        sync = getattr(self.app, 'catalog_sync', None)
        return sync is None or (sync.snapshot()['ready'] and getattr(self.app.manager, 'resource_status', {}).get('ready')
                                and sync.snapshot().get('catalog_token') == getattr(self.app.manager, 'resource_status', {}).get('catalog_token'))

    @property
    def live(self):
        s = self.app.manager.sessions.get(self.sid)
        return bool(s and s.active and not s.stop_event.is_set() and s.phase == 'world_ready'
                    and self.catalog_ready
                    and getattr(self.app.manager, 'available', True))

    def send(self, command, question=None):
        try:
            if not self.live or not self.app.manager.game_command(self.sid, command): raise ValueError('請先完成角色登入，並確認背景服務正常')
            self.message.text = '已排入操作佇列，等待核心與伺服器回覆'
            return True
        except (ValueError, OSError) as exc: self.message.text = str(exc); return False

    def preferences(self, value):
        try:
            if not self.app.manager.save_preferences(self.sid, value): raise ValueError('背景服務未就緒')
            self.message.text = '偏好已送出保存，等待服務確認'; return True
        except (ValueError, OSError) as exc: self.message.text = str(exc); return False

    def show(self, name):
        self.page_name = name
        if name not in self.views:
            module, cls = _PAGE_IMPL[name]
            # Construct only the requested page; preserve all visited pages,
            # their drafts, scroll positions and any active popup state.
            page_type = getattr(import_module('android_app.pages.' + module), cls)
            page = page_type(self)
            scroll = ScrollView(do_scroll_x=False)
            scroll.add_widget(page)
            self.views[name] = (page, scroll)
        self.page, scroll = self.views[name]
        self.content.clear_widgets()
        self.content.add_widget(scroll)
        # Immediate feedback on navigation. Later ticks are coalesced.
        self.page.refresh()

    def tick(self, *_):
        if self.closed: return False
        session = self.app.manager.sessions.get(self.sid)
        if not session: self.close(); return False
        if not getattr(self.app.manager, 'available', True):
            self.status.text = '服務失聯，資料為最後同步內容；操作已停用'
            if self.page_name == '聊天' and self.page:
                self.page.refresh()  # Clear pending without discarding draft.
            return True
        manager = self.app.manager
        revisions = getattr(manager, 'detail_revisions', None)
        # Read the revision before the snapshot: if an IPC update races us,
        # the next tick still sees its newer revision.
        revision = revisions.get(self.sid, 0) if isinstance(revisions, dict) else None
        try: data = manager.session_detail(self.sid)
        except ValueError: return True
        if data:
            if revision is None:
                # Non-background preview mode does not have IPC revisions.
                if data != self.data:
                    self._local_data_revision += 1
                revision = self._local_data_revision
            self.data = data
            npc = self.state.get('npc_dialogue', {})
            effect = (npc.get('scene'), npc.get('npc_index'), npc.get('effect_packet'))
            if (npc.get('active') and npc.get('phase') == 'choice_unavailable'
                    and self.state.get('automation', {}).get('enabled', True)
                    and effect != self.last_npc_effect):
                self.last_npc_effect = effect
                self.navigation.text = 'NPC'
            connected = self.live
            self.status.text = '已連線' if connected else '連線已停止／等待角色登入；以下為最後同步資料'
            if (self.page and self._refresh_policy.should_refresh(
                    self.page_name, revision, connected, time.monotonic())):
                self.page.refresh()
        return True

    def chat_ack(self, value):
        if '聊天' in self.views: self.views['聊天'][0].ack(value)

    def close(self): self.popup.dismiss()

    def dismissed(self):
        if self.closed: return
        self.closed = True; self.timer.cancel()
        for page, _ in self.views.values():
            if hasattr(page, 'close'): page.close()
        if hasattr(self.app.manager, 'watch'): self.app.manager.watch(None)
        self.app.dashboard = None

