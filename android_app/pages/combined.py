"""Android touch-friendly paired feature workspaces.

Reuses the exact six established Kivy pages and their server-side safety
checks; expanding a section never dispatches a gameplay command. Section
widgets are created only on demand and retained, so drafts survive collapse.
"""
from importlib import import_module

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from android_app.pages.general import Page
from android_app.pages.ui_components import feature_card, status_line
from android_app.widgets import button, row
from android_app.theme import style_button


# module, class, heading, explanation. These are existing feature pages.
PAIRS = {
    '聊天＋組隊': (
        ('social', 'Chat', '聊天訊息',
         '頻道、引用、表情與發送狀態，均以伺服器回覆為準'),
        ('social', 'Party', '組隊管理',
         '附近玩家、隊伍成員、邀請與申請的原有操作'),
    ),
    '遠征＋副本': (
        ('expedition', 'Expedition', '星之方舟／遠征',
         '任務與派遣狀態由已同步資料判斷，不自動開始'),
        ('instances', 'InstanceCatalog', '副本／協力',
         '官方資料與即時房間分開；開房、入場和領獎需確認'),
    ),
    '煉金＋製作': (
        ('production', 'Alchemy', '煉金',
         '五格材料、模式與批數保留在同一個操作區塊'),
        ('production', 'Crafting', '製作工坊',
         '配方搜尋、佇列與已確認的製作狀態'),
    ),
}


class _SectionDashboard:
    """Presentation-name override without duplicating live account state.

    In the paired expedition view, avoid the standalone instance screen's
    periodic room query: room retrieval must remain a manual user action.
    """
    def __init__(self, dashboard, heading):
        self._dashboard = dashboard
        self.page_name = heading

    def __getattr__(self, name):
        return getattr(self._dashboard, name)


class PairedFeatures(Page):
    """Single scrollable page containing independently collapsible controls."""

    def __init__(self, dashboard, pair_name):
        super().__init__(dashboard)
        if pair_name not in PAIRS:
            raise ValueError('未知功能整合頁：' + pair_name)
        self.pair_name = pair_name
        self.sections = {}

        if pair_name == '煉金＋製作':
            guide = feature_card(
                '煉金／製作工作台',
                '先選材料或配方，再明確確認消耗與排程',
                variant='highlight')
            self.hint = status_line(
                '材料為本地草稿；可查看製作配方，所有操作仍等伺服器確認')
        else:
            guide = feature_card(
                '功能整合操作',
                '同頁管理兩個原有功能；點選展開，不自動發送遊戲指令',
                variant='highlight')
            self.hint = status_line(
                '每個區塊的操作結果仍由遊戲服務與伺服器確認')
        guide.add_widget(self.hint)
        self.add_widget(guide)

        for module, cls_name, title, subtitle in PAIRS[pair_name]:
            panel = feature_card(title, subtitle)
            toggle = button('展開' + title, lambda name=title: self.toggle(name),
                            56)
            panel.add_widget(toggle)
            slot = BoxLayout(orientation='vertical', spacing=dp(8),
                             size_hint_y=None)
            slot.bind(minimum_height=slot.setter('height'))
            panel.add_widget(slot)
            self.sections[title] = {
                'module': module, 'class': cls_name, 'slot': slot,
                'toggle': toggle, 'view': None, 'expanded': False,
            }
            self.add_widget(panel)

        # The first set of controls is ready immediately; the second
        # (potentially expensive expedition/recipe catalog) stays lazy.
        first = PAIRS[pair_name][0][2]
        self.expand(first)

    def expand(self, title):
        section = self.sections[title]
        if section['expanded']:
            return
        if section['view'] is None:
            module = import_module('android_app.pages.' + section['module'])
            page_type = getattr(module, section['class'])
            # "副本／協力" is deliberately not "副本資料": the standalone
            # InstanceCatalog.refresh() auto-query must not run here.
            # Only this one paired screen uses the new compact production
            # presentation. Standalone Alchemy/Crafting and the other two
            # paired screens retain their existing widget trees.
            compact = self.pair_name == '煉金＋製作'
            proxy = _SectionDashboard(self.d, '' if compact else title)
            section['view'] = (page_type(proxy, compact=True)
                               if compact else page_type(proxy))
        section['slot'].add_widget(section['view'])
        section['expanded'] = True
        section['toggle'].text = '收合' + title
        section['view'].refresh()

    def collapse(self, title):
        section = self.sections[title]
        if not section['expanded']:
            return
        view = section['view']
        pause = getattr(view, 'pause_render', None)
        if callable(pause):
            pause()
        section['slot'].remove_widget(view)
        section['expanded'] = False
        section['toggle'].text = '展開' + title

    def toggle(self, title):
        if self.sections[title]['expanded']:
            self.collapse(title)
        else:
            self.expand(title)

    def refresh(self):
        for title, section in self.sections.items():
            view = section['view']
            if view is None:
                continue
            # A pending chat acknowledgement must also handle disconnection
            # when the chat card is collapsed.
            if section['expanded'] or (
                    title == '聊天訊息' and getattr(view, 'pending', False)):
                view.refresh()

    def chat_ack(self, receipt):
        """Forward the actual server receipt to the paired chat instance."""
        section = self.sections.get('聊天訊息')
        if section is not None and section['view'] is not None:
            section['view'].ack(receipt)

    def close(self):
        for section in self.sections.values():
            view = section['view']
            if view is not None:
                close = getattr(view, 'close', None)
                if callable(close):
                    close()


class ChatAndParty(PairedFeatures):
    def __init__(self, d):
        super().__init__(d, '聊天＋組隊')


class ExpeditionAndInstances(PairedFeatures):
    def __init__(self, d):
        super().__init__(d, '遠征＋副本')


class AlchemyAndCrafting(Page):
    """One actual workbench, not two complete pages inside nested cards.

    Switching between the two functional areas does not recreate the Kivy
    controls: local material selections, counts and recipe filters survive.
    Only the selected area refreshes on dashboard polling.
    """

    WORK_AREAS = (
        ('煉金', 'Alchemy'),
        ('製作工坊', 'Crafting'),
    )

    def __init__(self, d):
        # Dashboard already shows the selected feature name in its chooser.
        # Avoid repeating that heading inside another bordered feature page.
        super().__init__(d, show_title=False)
        self.pair_name = '煉金＋製作'
        self.active = None
        self.sections = {}

        self.switcher = row(
            button('煉金材料', lambda: self.select('煉金'), 48),
            button('製作配方', lambda: self.select('製作工坊'), 48))
        self.tab_buttons = dict(zip(
            ('煉金', '製作工坊'), reversed(self.switcher.children)))
        self.add_widget(self.switcher)
        self.note = status_line(
            '選取材料與配方不會自動送出；消耗及排程需明確確認')
        self.note.font_size = '12sp'
        self.add_widget(self.note)

        self.workbench = BoxLayout(
            orientation='vertical', spacing=dp(6), size_hint_y=None)
        self.workbench.bind(
            minimum_height=self.workbench.setter('height'))
        self.add_widget(self.workbench)

        for title, cls_name in self.WORK_AREAS:
            slot = BoxLayout(
                orientation='vertical', size_hint_y=None)
            slot.bind(minimum_height=slot.setter('height'))
            self.sections[title] = {
                'class': cls_name, 'slot': slot,
                'view': None, 'expanded': False,
            }

        self.select('煉金')

    def select(self, title):
        """Switch panels locally without triggering a gameplay command."""
        if title == self.active:
            return
        previous = self.active
        if previous is not None:
            old = self.sections[previous]
            pause = getattr(old['view'], 'pause_render', None)
            if callable(pause):
                pause()
            self.workbench.remove_widget(old['slot'])
            old['expanded'] = False

        section = self.sections[title]
        if section['view'] is None:
            module = import_module('android_app.pages.production')
            page_type = getattr(module, section['class'])
            # These controllers have the original alchemy/crafting validation.
            # Embedded mode only changes visual framing, not command behavior.
            proxy = _SectionDashboard(self.d, '')
            section['view'] = page_type(proxy, compact=True)
            section['slot'].add_widget(section['view'])

        self.workbench.add_widget(section['slot'])
        section['expanded'] = True
        self.active = title
        for key, control in self.tab_buttons.items():
            style_button(control, primary=key == title)
        self.note.text = (
            '五格材料及每次數量；送出前預覽消耗'
            if title == '煉金' else
            '已確認配方與材料需求；加入排程需再次確認')
        section['view'].refresh()

    def expand(self, title):
        self.select(title)

    def toggle(self, title):
        self.select(title)

    def refresh(self):
        if self.active is not None:
            self.sections[self.active]['view'].refresh()

    def close(self):
        for section in self.sections.values():
            view = section['view']
            if view is not None:
                close = getattr(view, 'close', None)
                if callable(close):
                    close()
