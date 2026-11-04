"""Android touch-friendly paired feature workspaces.

Reuses established Kivy pages and their server-side safety
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
            # Production uses its existing compact presentation. Only the
            # explicitly opted-in reference sections use compact settings or
            # attributes; standalone pages and other pairs remain unchanged.
            compact = (self.pair_name == '煉金＋製作'
                       or section.get('compact', False))
            proxy = _SectionDashboard(
                self.d, '' if compact else section.get('page_heading', title))
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
    """The screenshot-matched chat plus party workspace, without nested pages.

    Each child is still the original Chat/Party controller and uses the
    established server-safe send, quote, invitation and acknowledgement paths.
    Both sections remain on the same scrollable page, not mutually exclusive.
    """

    def __init__(self, d):
        # Avoid the old three nested 'feature_card' shells. The two native
        # sections have dedicated, compact, editable live-state views.
        Page.__init__(self, d, embedded=True, show_title=False)
        from android_app.pages.social_visual import (
            SocialButton, heading, glass_card)
        self.pair_name = '聊天＋組隊'
        self.sections = {}
        self._initial_party_loaded = False
        self._focus_name = '聊天訊息'

        tabs=glass_card(bright=True,padding=4,gap=3,radius=14)
        tab_row=BoxLayout(size_hint_y=None,height=dp(41),spacing=dp(5))
        self.chat_tab=SocialButton('聊天',lambda:self._focus('聊天訊息'),
                                    icon='chat',primary=True,
                                    font='14sp',height=41)
        self.party_tab=SocialButton('組隊',lambda:self._focus('組隊管理'),
                                     icon='users',font='14sp',height=41)
        tab_row.add_widget(self.chat_tab)
        tab_row.add_widget(self.party_tab)
        tabs.add_widget(tab_row)
        self.add_widget(tabs)

        chat_slot=BoxLayout(orientation='vertical',size_hint_y=None,
                            spacing=dp(4))
        chat_slot.bind(minimum_height=chat_slot.setter('height'))
        self.add_widget(chat_slot)
        chat_toggle=SocialButton(
            '收合聊天',lambda:self.toggle('聊天訊息'),icon='chat',
            font='10sp',height=35)
        self.sections['聊天訊息']={
            'module':'social','class':'Chat','slot':chat_slot,
            'toggle':chat_toggle,'view':None,'expanded':False,
        }

        group=BoxLayout(orientation='vertical',size_hint_y=None,
                         spacing=dp(5))
        group.bind(minimum_height=group.setter('height'))
        group_title=BoxLayout(size_hint_y=None,height=dp(34),
                              spacing=dp(8))
        group_title.add_widget(heading('組隊管理',icon='users'))
        group_toggle=SocialButton(
            '展開組隊管理',lambda:self.toggle('組隊管理'),
            icon='chevron',font='11sp',height=34)
        group_toggle.size_hint_x=None
        group_toggle.width=dp(130)
        group_title.add_widget(group_toggle)
        group.add_widget(group_title)
        group_slot=BoxLayout(orientation='vertical',size_hint_y=None,
                             spacing=dp(5))
        group_slot.bind(minimum_height=group_slot.setter('height'))
        group.add_widget(group_slot)
        self.add_widget(group)
        self.party_group=group
        self.sections['組隊管理']={
            'module':'social','class':'Party','slot':group_slot,
            'toggle':group_toggle,'view':None,'expanded':False,
        }

        # Chat composer is immediately editable; the group is instantiated
        # during the first Dashboard refresh, avoiding expensive eager setup.
        self.expand('聊天訊息')

    def _focus(self, section):
        from android_app.theme import style_button
        if section not in self.sections:
            return
        self._focus_name=section
        if not self.sections[section]['expanded']:
            self.expand(section)
        style_button(self.chat_tab,primary=section=='聊天訊息',radius=12)
        style_button(self.party_tab,primary=section=='組隊管理',radius=12)
        views=getattr(self.d,'views',{})
        attached=views.get('聊天＋組隊') if isinstance(views,dict) else None
        if attached is not None:
            _page,scroll=attached
            target=(self.party_group if section=='組隊管理'
                    else self.sections['聊天訊息']['slot'])
            scroll.scroll_to(target,padding=dp(6),animate=False)

    def refresh(self):
        # In the actual Dashboard, both panels should be visible initially,
        # as in the reference. The original lazy test/controller API remains
        # stable for embedded or otherwise detached widget construction.
        if not self._initial_party_loaded:
            self._initial_party_loaded=True
            if hasattr(self.d,'views'):
                self.expand('組隊管理')
        super().refresh()


class ExpeditionAndInstances(PairedFeatures):
    def __init__(self, d):
        super().__init__(d, '遠征＋副本')


class AlchemyAndCrafting(Page):
    """Alchemy, recipe browser, detail preview and server queue on one page.

    This is a single scrolling workspace, as in the supplied reference
    design. No tabs hide one of the two functions. Both reuse their verified
    controllers; choosing ingredients and previewing recipes sends nothing.
    """

    WORK_AREAS = (
        ('煉金', 'Alchemy'),
        ('製作工坊', 'Crafting'),
    )

    def __init__(self, d):
        # Dashboard already displays the selected feature name. Retain only
        # one shell so the full workbench is visible without nested frames.
        super().__init__(d, show_title=False)
        self.pair_name = '煉金＋製作'
        self.sections = {}
        self.workbench = BoxLayout(
            orientation='vertical', spacing=dp(10), size_hint_y=None)
        self.workbench.bind(
            minimum_height=self.workbench.setter('height'))
        self.add_widget(self.workbench)

        module = import_module('android_app.pages.production')
        for title, cls_name in self.WORK_AREAS:
            proxy = _SectionDashboard(self.d, '')
            view = getattr(module, cls_name)(proxy, compact=True)
            self.sections[title] = {
                'class': cls_name, 'view': view, 'expanded': True,
            }
            # Alchemy above, crafting catalog/details/queue below.
            self.workbench.add_widget(view)
        self.refresh()

    def refresh(self):
        for section in self.sections.values():
            section['view'].refresh()

    def expand(self, title):
        # Both work areas are already visible; retain a safe compatibility
        # method for any previously wired navigation callback.
        if title not in self.sections:
            raise KeyError(title)

    def close(self):
        for section in self.sections.values():
            close = getattr(section['view'], 'close', None)
            if callable(close):
                close()


class _ReferenceWorkspace(PairedFeatures):
    """Retained original controllers inside one vertical phone workspace.

    Navigation and expansion are presentation only. In particular, opening a
    tool must never issue its gameplay command or imply server readiness.
    """

    def __init__(self, dashboard, name):
        Page.__init__(self, dashboard, embedded=True, show_title=False)
        self.pair_name = name
        self.sections = {}

    def add_section(self, module, cls_name, title, subtitle='', *,
                    visible=False, compact=False):
        # Visible controllers already contain their own feature headings and
        # surfaces. Avoid adding another card around those same controls.
        panel = (BoxLayout(orientation='vertical', size_hint_y=None,
                           spacing=dp(8)) if visible
                 else feature_card(title, subtitle))
        panel.bind(minimum_height=panel.setter('height'))
        toggle = button('展開' + title, lambda: self.toggle(title), 52)
        if not visible:
            panel.add_widget(toggle)
        slot = BoxLayout(orientation='vertical', size_hint_y=None,
                         height=0, spacing=dp(8))
        slot.bind(minimum_height=slot.setter('height'))
        panel.add_widget(slot)
        self.sections[title] = {
            'module': module, 'class': cls_name, 'slot': slot,
            'toggle': toggle, 'view': None, 'expanded': False,
            'page_heading': '', 'compact': compact,
        }
        self.add_widget(panel)
        if visible:
            self.expand(title)

    def pause_render(self):
        # Dashboard calls this on navigation away. Forward cancellation only
        # to materialized views; never instantiate tools during cleanup.
        for section in self.sections.values():
            pause = getattr(section['view'], 'pause_render', None)
            if callable(pause):
                pause()


class CompanionsAndAttributes(_ReferenceWorkspace):
    """Live companion deployment followed by the real attribute draft editor.

    The sample artwork's names, maximum party size and affinity scale are not
    protocol facts. All values and action restrictions stay with the original
    controllers; allocation drafts survive refresh and returning to this page.
    """

    def __init__(self, d):
        super().__init__(d, '夥伴＋能力')
        self.add_section('companions', 'Companions', '夥伴出戰', visible=True)
        self.add_section('attributes', 'Attributes', '角色能力',
                         visible=True, compact=True)


class SettingsAndTools(_ReferenceWorkspace):
    """Account settings and expandable, server-backed utilities in one place."""

    def __init__(self, d):
        super().__init__(d, '設定與工具')
        guide = feature_card(
            '設定與工具中心',
            '設定依帳號保存；工具展開後才載入，操作仍需伺服器確認',
            variant='highlight')
        self.add_widget(guide)
        self.add_section('settings', 'SettingsPage', 'AI與補給設定',
                         visible=True, compact=True)
        self.add_section(
            'npc', 'NPC', 'NPC 互動與對話',
            '查看目前場景、對話選項與已驗證商店資訊')
        self.add_section(
            'storage', 'Storage', '儲藏存取',
            '儲藏室／雜物櫃；選取物品後核對庫存並確認存取')
        self.add_section(
            'benefits', 'Benefits', '福利／魔方',
            '查看實際魔方次數、倒數與背景服務排程')
