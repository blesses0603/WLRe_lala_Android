from android_app.pages.general import Page
from android_app.widgets import button, label
from android_app.settings_ui import SettingsEditor

class SettingsPage(Page):
    def __init__(self, d, *, compact=False):
        self.compact = compact
        super().__init__(d, embedded=compact, show_title=not compact)
        if compact:
            self._build_compact()
            return
        from android_app.pages.ui_components import feature_card, status_line

        info = feature_card('AI 與戰後補給',
                            '每帳號／伺服器個別設定；草稿只在明確保存後生效',
                            variant='highlight')
        info.add_widget(status_line(
            '編輯規則不會立即套用到戰鬥；'
            '下次啟動自動戰鬥時才依核心驗證設定生效。'))
        self.add_widget(info)

        groups = (
            ('基本與戰鬥規則',
             ('一般設定', '角色規則', '夥伴規則')),
            ('補給與隊伍安全',
             ('HP／SP補給', '必要成員')),
            ('維護與資料交換',
             ('修理／整理', '匯入／匯出')),
        )
        for title, tabs in groups:
            panel = feature_card(title, '點選進入可編輯的設定面板')
            for name in tabs:
                panel.add_widget(button(
                    name, lambda tab=name: self.open(tab), 52))
            self.add_widget(panel)

    def _build_compact(self):
        from kivy.metrics import dp
        from kivy.uix.gridlayout import GridLayout
        from android_app.pages.ui_components import feature_card, status_line

        panel = feature_card('AI 與戰後補給', '點選分類編輯；只有明確保存才生效')
        grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        self.setting_buttons = {}
        for tab in SettingsEditor.TABS:
            control = button(tab, lambda name=tab: self.open(name), 52)
            self.setting_buttons[tab] = control
            grid.add_widget(control)
        panel.add_widget(grid)
        panel.add_widget(status_line('設定依帳號保存，下次啟動自動戰鬥時套用'))
        self.add_widget(panel)

    def open(self, tab):
        if 'ai_settings' not in self.d.data:
            self.d.message.text = '等待本帳號設定與已學特技同步，請稍候再試'
            return
        SettingsEditor(self.d.app,self.d.sid,tab)
