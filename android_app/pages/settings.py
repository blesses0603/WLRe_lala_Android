from android_app.pages.general import Page
from android_app.widgets import button, label
from android_app.settings_ui import SettingsEditor

class SettingsPage(Page):
    def __init__(self, d):
        super().__init__(d)
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

    def open(self, tab):
        if 'ai_settings' not in self.d.data:
            self.d.message.text = '等待本帳號設定與已學特技同步，請稍候再試'
            return
        SettingsEditor(self.d.app,self.d.sid,tab)
