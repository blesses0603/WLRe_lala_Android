import copy
import json
from types import SimpleNamespace
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from android_app.widgets import RoundedSpinnerOption
from android_app.theme import surface, style_input, SOFT, MUTED, ACCENT
from kivy.core.clipboard import Clipboard
from android_app.pages.general import Page
from android_app.widgets import column, label, button, row, field, select, dialog, pick
from android_app.assets import item_image
from android_app.pages.production_visual import (
    AlchemyLevelBar, tiny_label, ProductionPanel, MaterialSlot,
    RecipeRow, IngredientRow, QueueEntry, action_button,
)
from wlre.services.items.combat_resources import item_name
from wlre.services.items.alchemy import modes, prepare, material_problem
from wlre.services.items.crafting import RECIPES, confirmed_unlocked, recipe_plan, effective_time, elapsed
from wlre.services.items.crafting_browser_model import availability, material_rows, owned_counts, tool_status
from wlre.services.items.crafting_plan import validate_rows
from wlre.core.efficiency import duration


class Alchemy(Page):
    def __init__(self, d, compact=False):
        super().__init__(d, embedded=compact)
        self.compact = compact
        self.material_icons = {}
        self.material_tiles = {}
        from android_app.pages.ui_components import feature_card, status_line
        self.materials = [None]*5

        workbench = (ProductionPanel(
            '煉金 (Alchemy)', '使用已核對的煉金術等級及背包材料',
            icon_name='煉金') if compact else None)
        if compact:
            setup = BoxLayout(
                orientation='vertical', spacing=dp(5), size_hint_y=None)
            setup.bind(minimum_height=setup.setter('height'))
        else:
            setup = feature_card('煉金設定',
                                 '模式與次數必須由原有煉金核心驗證')
        if compact:
            # The design's grade selector is NOT an unverified alchemy mode.
            # Keep the original protocol string in a nonvisual Spinner and
            # expose four independently gated Kivy buttons.
            self.mode = Spinner(text='無技能', values=['無技能'])
            setup.add_widget(tiny_label(
                '煉金術等級', height=23, font_size='12sp', color=MUTED))
            self.level_bar = AlchemyLevelBar(self._choose_level)
            setup.add_widget(self.level_bar)
            self.mode.bind(text=lambda *_: self.level_bar.set_available(
                modes(self.state), self.mode.text))
            count_box = BoxLayout(orientation='horizontal',
                                  size_hint_y=None, height=dp(48),
                                  spacing=dp(6))
            title = tiny_label('執行次數', height=42,
                               font_size='12sp', color=MUTED)
            title.size_hint_x = None
            title.width = dp(58)
            count_box.add_widget(title)
            self.runs = style_input(TextInput(
                text='1', multiline=False, input_filter='int',
                input_type='number', size_hint_x=1, font_size='13sp'))
            count_box.add_widget(self.runs)
            setup.add_widget(count_box)
            setup.add_widget(row(
                button('－', lambda: self.adjust_runs(-1)),
                button('＋', lambda: self.adjust_runs(1)),
                button('10 次', lambda: self.set_runs(10)),
                button('50 次', lambda: self.set_runs(50)),
                button('100 次', lambda: self.set_runs(100))))
        else:
            self.mode = select(setup, '煉金術', ['無技能'])
            self.runs = field(setup, '執行次數（1～999）', 1, True)
            self.add_widget(setup)

        if compact:
            materials = BoxLayout(
                orientation='vertical', spacing=dp(5), size_hint_y=None)
            materials.bind(minimum_height=materials.setter('height'))
            self.material_status = status_line('煉金材料：0／5 格')
            materials.add_widget(self.material_status)
        else:
            materials = feature_card(
                '材料槽位',
                '五個來源格位；僅使用已確認且未受限制的背包物品')
        self.slots = []
        if compact:
            # Show the actual material slots before setup inputs. Three
            # columns fit a 320dp viewport without five full nested forms.
            self.material_grid = GridLayout(
                cols=3, spacing=dp(5), size_hint_y=None,
                row_default_height=dp(156), row_force_default=True)
            self.material_grid.bind(
                minimum_height=self.material_grid.setter('height'))
            self.material_grid.bind(
                width=lambda grid, width: setattr(
                    grid, 'cols', (
                        2 if width < dp(245) else
                        3 if width < dp(342) else 5)))
            for index in range(5):
                tile = MaterialSlot(
                    index,
                    on_choose=lambda i=index: self.choose(i),
                    on_remove=lambda i=index: self.set_slot(i, None),
                    icon_factory=lambda sid: item_image(sid, size=36))
                self.material_tiles[index] = tile
                self.material_icons[index] = tile.icon_holder
                self.slots.append((tile.pick_button, tile.quantity))
                self.material_grid.add_widget(tile)
                self._show_material_icon(index, None)
            materials.add_widget(self.material_grid)
        else:
            for index in range(5):
                slot = feature_card('材料 {}'.format(index+1))
                control = button(
                    '材料 {}：選擇'.format(index+1),
                    lambda i=index: self.choose(i))
                slot.add_widget(control)
                count = field(slot, '每次數量', 1, True)
                self.slots.append((control, count))
                materials.add_widget(slot)
        if compact:
            # The reference shows a single alchemy panel with short controls,
            # a five-slot inventory tray, and actions—not three nested cards.
            workbench.add_widget(setup)
            workbench.add_widget(materials)
            self.add_widget(workbench)
        else:
            self.add_widget(materials)

        if compact:
            actions = BoxLayout(
                orientation='vertical', spacing=dp(7), size_hint_y=None)
            actions.bind(minimum_height=actions.setter('height'))
        else:
            actions = feature_card('煉金佇列與執行',
                                   '預覽本次總消耗，確認後才送出')
        self.info = status_line('等待煉金狀態同步')
        actions.add_widget(self.info)
        if compact:
            self.cost_preview = status_line('尚未預覽材料消耗')
            actions.add_widget(self.cost_preview)
            actions.add_widget(row(
                button('預覽消耗', self.preview_cost),
                button('開始連續煉金', self.begin)))
        else:
            actions.add_widget(button(
                '預覽消耗／開始連續煉金', self.begin, 56))
        actions.add_widget(row(
            button('停止後續煉金', lambda: d.send({'type':'stop_alchemy'})),
            button('清空材料', self.clear)))
        if compact:
            workbench.add_widget(actions)
            self.mode.bind(text=lambda *_: self._invalidate_preview())
            self.runs.bind(text=lambda *_: self._invalidate_preview())
            for _, count in self.slots:
                count.bind(text=lambda *_: self._invalidate_preview())
        else:
            self.add_widget(actions)

    def _invalidate_preview(self):
        if self.compact:
            self.cost_preview.text = '材料或設定有變更，請重新預覽消耗'

    def _show_material_icon(self, index, value):
        """Only a selected, server-sourced item receives an original sprite."""
        if not self.compact:
            return
        tile = self.material_tiles[index]
        tile.set_item(
            value, item_name(value['item_id']) if value is not None else None)

    def clear(self):
        self.materials = [None]*5
        for i, (b, _) in enumerate(self.slots):
            b.text = ('材料 {}'.format(i+1) if self.compact
                      else f'材料 {i+1}：選擇')
            self._show_material_icon(i, None)
        self._update_material_status()
        self._invalidate_preview()
    def _update_material_status(self):
        if self.compact:
            count = sum(value is not None for value in self.materials)
            self.material_status.text = '煉金材料：{}／5 格'.format(count)
    def choose(self, index):
        entries = [(None, '清除此格')] + [(dict(v), f"#{v['index']} {item_name(v['item_id'])} ×{v['count']}")
            for v in self.state.get('inventory', {}).get('items', {}).values() if not material_problem(v)]
        pick('選擇背包材料', entries, lambda value: self.set_slot(index, value))
    def set_slot(self, index, value):
        self.materials[index] = value
        if self.compact:
            self._show_material_icon(index, value)
            self._update_material_status()
            self._invalidate_preview()
        else:
            self.slots[index][0].text = f'材料 {index+1}：'+(f"#{value['index']} {item_name(value['item_id'])}" if value else '選擇')
    def _choose_level(self, core_mode):
        # Never enable a skill just because its design button is present.
        if (self.mode.disabled or core_mode not in modes(self.state)):
            return
        self.mode.text = core_mode
        self.level_bar.set_available(modes(self.state), core_mode)
        self._invalidate_preview()

    def set_runs(self, value):
        # A UI shortcut, never a server command. The original core still
        # validates 1–999 as part of prepare().
        if not self.runs.disabled:
            self.runs.text = str(max(1, min(999, int(value))))

    def adjust_runs(self, delta):
        try:
            count = int(self.runs.text)
        except (ValueError, TypeError):
            count = 1
        self.set_runs(count + delta)

    def _current_plan(self):
        command = dict(
            type='start_alchemy', mode=self.mode.text,
            runs=int(self.runs.text), materials=[
                dict(index=v['index'], item_id=v['item_id'],
                     count=int(self.slots[i][1].text))
                for i, v in enumerate(self.materials) if v])
        state = SimpleNamespace(**self.state)
        state.snapshot = lambda: self.state
        plan = prepare(state, command)
        summary = (
            f"{plan['mode']}煉金，共 {plan['runs']} 次\n" +
            '\n'.join(
                f"#{v['index']} {item_name(v['item_id'])} "
                f"每次 {v['count']}，共消耗 {v['count']*plan['runs']}"
                for v in plan['consumption']))
        return command, summary

    def preview_cost(self):
        try:
            _, summary = self._current_plan()
            if self.compact:
                self.cost_preview.text = summary + '\n僅供預覽，尚未發送'
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self.d.message.text = str(exc)

    def begin(self):
        try:
            command, text = self._current_plan()
            self.d.send(command, text+'\n\n確認消耗材料並開始？')
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self.d.message.text = str(exc)
    def refresh(self):
        options = modes(self.state); self.mode.values = options
        if self.mode.text not in options and options: self.mode.text = options[-1]
        a = self.state.get('alchemy', {}); busy = a.get('enabled') or a.get('pending')
        self.mode.disabled = self.runs.disabled = bool(busy)
        if self.compact:
            self.level_bar.set_available(options if not busy else (),
                                         self.mode.text)
        for i, (b, count) in enumerate(self.slots):
            b.disabled = count.disabled = bool(busy)
            if self.compact:
                tile = self.material_tiles[i]
                tile.remove_button.disabled = bool(busy) or (
                    self.materials[i] is None)
        self.info.text = a.get('status', '等待同步')+f"\n完成 {a.get('completed', 0)}/{a.get('requested', 0)}"+'\n'+'\n'.join(
            f"{v.get('name', item_name(v['item_id']))} ×{v['count']}" for v in a.get('history', [])[-10:])


class Crafting(Page):
    def __init__(self, d, compact=False):
        super().__init__(d, embedded=compact)
        self.compact = compact
        self.preview_icon_id = None
        from android_app.pages.ui_components import feature_card, status_line
        self.selected = None
        self.offset = 0

        if compact:
            browse = ProductionPanel(
                '配方目錄', '只列已核對開放的製作配方',
                icon_name='製作')
            self.query = style_input(TextInput(
                text='', hint_text='搜尋配方名稱／ID',
                multiline=False, size_hint_y=None,
                height=dp(42), font_size='13sp'))
            browse.add_widget(self.query)
            filters = BoxLayout(
                orientation='horizontal', spacing=dp(6),
                size_hint_y=None, height=dp(42))
            self.tool = Spinner(
                text='全部', values=['全部', '我的最愛'],
                option_cls=RoundedSpinnerOption, size_hint_y=None,
                height=dp(42))
            self.only_owned = Spinner(
                text='全部已確認開放配方',
                values=['全部已確認開放配方', '只列小屋已擺設備'],
                option_cls=RoundedSpinnerOption,
                size_hint_y=None, height=dp(42))
            from android_app.theme import style_button
            filters.add_widget(style_button(self.tool))
            filters.add_widget(style_button(self.only_owned))
            browse.add_widget(filters)
        else:
            browse = feature_card(
                '製作工坊 · 配方目錄',
                '只列已確認開放配方，可依設備與收藏篩選')
            browse.add_widget(row(
                button('自訂清單', self.plan),
                button('進入自家帳篷',
                       lambda: d.send(dict(type='craft', action='enter')))))
            self.query = field(browse, '搜尋配方名稱／ID')
            self.tool = select(browse, '工作設備／收藏', ['全部', '我的最愛'])
            self.only_owned = select(
                browse, '顯示配方',
                ['全部已確認開放配方', '只列小屋已擺設備'])
        if compact:
            self.catalog_status = status_line('等待已確認配方')
            browse.add_widget(self.catalog_status)
            # The target screenshot shows a vertical recipe list on the
            # left and in-page details on the right (not a six-card grid).
            self.catalog = GridLayout(
                cols=1, spacing=dp(5), size_hint_y=None,
                row_default_height=dp(68), row_force_default=True)
            self.catalog.bind(
                minimum_height=self.catalog.setter('height'))
        else:
            self.catalog = column()
            self.catalog.spacing = dp(9)
        browse.add_widget(self.catalog)
        browse.add_widget(row(
            button('‹ 上一頁', lambda: self.move(-1)),
            button('下一頁 ›', lambda: self.move(1))))
        if compact:
            browse.add_widget(row(
                button('自訂清單', self.plan),
                button('進入自家帳篷',
                       lambda: d.send(dict(type='craft', action='enter')))))
        if not compact:
            self.add_widget(browse)

        if compact:
            # One in-page recipe detail panel; the existing verified recipe
            # dialog remains the only way to add to the server queue.
            preview = ProductionPanel(
                '配方詳情', '設備、材料與時間以實際同步資料為準')
            header = BoxLayout(
                orientation='horizontal', size_hint_y=None,
                spacing=dp(8), height=dp(95))
            self.preview_image = AnchorLayout(
                anchor_x='center', size_hint_x=None,
                width=dp(65))
            header.add_widget(self.preview_image)
            self.preview_info = status_line('選取左側配方查看詳情')
            header.add_widget(self.preview_info)
            self.preview_info.bind(height=lambda _, h: setattr(
                header, 'height', max(dp(95), h)))
            preview.add_widget(header)
            preview.add_widget(tiny_label(
                '所需材料', height=24, color=ACCENT))
            self.preview_ingredients = BoxLayout(
                orientation='vertical', spacing=dp(3),
                size_hint_y=None)
            self.preview_ingredients.bind(
                minimum_height=self.preview_ingredients.setter('height'))
            preview.add_widget(self.preview_ingredients)
            self.preview_action = action_button(
                '加入製作佇列（確認）', self.open_preview,
                height=48, primary=True)
            self.preview_action.disabled = True
            preview.add_widget(self.preview_action)
            self.crafting_panes = GridLayout(
                cols=2, spacing=dp(8), size_hint_y=None)
            self.crafting_panes.bind(
                minimum_height=self.crafting_panes.setter('height'))
            self.crafting_panes.bind(
                width=lambda panel, width: setattr(
                    panel, 'cols', 1 if width < dp(390) else 2))
            self.crafting_panes.add_widget(browse)
            self.crafting_panes.add_widget(preview)
            self.add_widget(self.crafting_panes)

        execution = (ProductionPanel(
            '製作佇列', '製作進度與順序由伺服器同步確認',
            icon_name='製作') if compact else feature_card(
                '伺服器製作佇列',
                '順序、用料與剩餘時間由已同步狀態確認',
                variant='highlight'))
        self.queue_info = status_line('等待排程同步')
        execution.add_widget(self.queue_info)
        if compact:
            self.queue = BoxLayout(
                orientation='vertical', spacing=dp(5),
                size_hint_y=None)
            self.queue.bind(
                minimum_height=self.queue.setter('height'))
        else:
            self.queue = column()
        execution.add_widget(self.queue)
        execution.add_widget(row(
            button('開始／接續製作',
                   lambda: d.send(dict(type='craft', action='start'))),
            button('暫停製作',
                   lambda: d.send(dict(type='craft', action='pause')))))
        execution.add_widget(button(
            '停止後續自動接續',
            lambda: d.send(dict(type='craft', action='stop_auto'))))
        self.add_widget(execution)
        self.tool.bind(text=lambda *_: self.find())
        self.only_owned.bind(text=lambda *_: self.find())
        self.query.bind(text=lambda *_: self.find())
        self.tools = {}
    def find(self): self.offset = 0; self.key = None; self.refresh()
    def move(self, delta): self.offset = max(0, self.offset+delta); self.key = None; self.refresh()
    def refresh(self):
        favorites = self.d.data.get('preferences', {}).get('favorites', [])
        s = self.state; craft = s.get('crafting', {})
        tools = {item_name(r['tool_id'])+f"（{r['tool_id']}）": r['tool_id'] for r in RECIPES.values() if confirmed_unlocked(r)}
        self.tools = tools; self.tool.values = ['全部', '我的最愛', *sorted(tools)]
        key = (str(s.get('inventory')), str(s.get('furniture')), str(craft), str(favorites), self.query.text, self.tool.text, self.only_owned.text, self.offset)
        if key == self.key: return
        self.key = key; self.catalog.clear_widgets(); self.queue.clear_widgets()
        q = self.query.text.casefold(); selected_tool = tools.get(self.tool.text)
        recipes = [r for sid, r in RECIPES.items() if confirmed_unlocked(r)
            and q in (item_name(int(sid))+sid).casefold()
            and (self.tool.text != '我的最愛' or int(sid) in favorites)
            and (selected_tool is None or r['tool_id'] == selected_tool)
            and (self.only_owned.text != '只列小屋已擺設備' or tool_status(s, r['tool_id']) == '已擺放')]
        pages = max(1, (len(recipes)+5)//6); self.offset = min(self.offset, pages-1)
        counter = label(f'{self.offset+1}/{pages} 頁 · {len(recipes)} 項配方 · 收藏 {len(favorites)}/100', 35)
        if self.compact:
            self.catalog_status.text = counter.text
        else:
            counter.color = MUTED
            self.catalog.add_widget(counter)
        if not recipes:
            self.catalog.add_widget(label(
                '沒有符合條件的配方，請調整搜尋或設備篩選。',
                60 if self.compact else None))
        for recipe in recipes[self.offset*6:self.offset*6+6]:
            sid = recipe['item_id']; status, _ = availability(s, recipe)
            if self.compact:
                card = RecipeRow(
                    recipe, item_name(sid),
                    status + ' · ' + item_name(recipe['tool_id']),
                    self.preview_recipe, favorite=sid in favorites,
                    icon_factory=lambda item_id:
                        item_image(item_id, size=45))
                card.set_selected(sid == self.selected)
            else:
                # Standalone production list retains its original full rows.
                card = surface(BoxLayout(
                    orientation='horizontal', spacing=dp(10),
                    padding=[dp(10), dp(8), dp(10), dp(8)],
                    size_hint_y=None, height=dp(88)), color=SOFT,
                    radius=16)
                card.add_widget(item_image(sid, 52))
                info = BoxLayout(orientation='vertical', size_hint_x=1)
                name = label(
                    ('♥ ' if sid in favorites else '') + item_name(sid), 32)
                name.font_size = '14sp'
                state_line = label(
                    status + ' · ' + item_name(recipe['tool_id']), 32)
                state_line.font_size = '11sp'
                state_line.color = MUTED
                info.add_widget(name)
                info.add_widget(state_line)
                card.add_widget(info)
                action = button(
                    '詳情 ›', lambda r=recipe: self.recipe(r), 48)
                action.size_hint_x = None
                action.width = dp(74)
                card.add_widget(action)
            self.catalog.add_widget(card)
        self.queue_info.text = craft.get('status', '等待排程同步')+f"\n完成 {craft.get('completed',0)} 項｜伺服器排程 {len(craft.get('queue',{}))} 項"
        for value in sorted(craft.get('queue', {}).values(), key=lambda r: r['index']):
            sid = value['item_id']; index = value['index']
            seconds = effective_time(s, value)
            remaining = max(0, seconds*value['count']-elapsed(craft, value, __import__('time').monotonic())) if seconds is not None else None
            if self.compact:
                done = None
                if (craft.get('running') and craft.get('active') == index
                        and seconds and value.get('count')):
                    total = seconds * value['count']
                    done = max(0., min(1., 1 - remaining / total))
                self.queue.add_widget(QueueEntry(
                    sid, item_name(sid), value['count'], index,
                    duration(remaining) if remaining is not None
                    else '待同步', done, self.queue_action,
                    icon_factory=lambda item_id:
                        item_image(item_id, size=36)))
            else:
                self.queue.add_widget(label(f"#{index} {item_name(sid)} ×{value['count']} · 剩餘 {duration(remaining)}"))
                self.queue.add_widget(row(*(button(text, lambda action=action, i=index: self.queue_action(action, i))
                    for text, action in (('上移','up'),('下移','down'),('刪除','delete')))))
        if self.compact and self.selected is not None:
            self._render_preview()

    def preview_recipe(self, recipe):
        """Preview only. Never sends a craft/add/plan command."""
        self.selected = recipe['item_id']
        self._render_preview()

    def _render_preview(self):
        if not self.compact:
            return
        recipe = RECIPES.get(str(self.selected))
        if recipe is None or not confirmed_unlocked(recipe):
            self.selected = None
            self.preview_icon_id = None
            self.preview_image.clear_widgets()
            self.preview_info.text = '未選取已確認開放的配方'
            self.preview_action.disabled = True
            self.preview_ingredients.clear_widgets()
            return
        sid = recipe['item_id']
        status, reason = availability(self.state, recipe)
        requirements = material_rows(self.state, recipe, 1)
        lines = [
            '{}（ID {}）'.format(item_name(sid), sid),
            '產量 {}｜製作時間 {}'.format(
                recipe['output'], duration(recipe['seconds'])),
            '設備：{} · {}'.format(
                item_name(recipe['tool_id']),
                tool_status(self.state, recipe['tool_id'])),
            '{}：{}'.format(status, reason),
        ]
        # Render source-backed material rows, rather than a long text block.
        self.preview_ingredients.clear_widgets()
        for requirement in requirements:
            self.preview_ingredients.add_widget(IngredientRow(
                requirement,
                icon_factory=lambda item_id:
                    item_image(item_id, size=27)))
        self.preview_info.text = '\n'.join(lines)
        if self.preview_icon_id != sid:
            self.preview_image.clear_widgets()
            self.preview_image.add_widget(item_image(sid, 58))
            self.preview_icon_id = sid
        self.preview_action.disabled = False

    def open_preview(self):
        recipe = RECIPES.get(str(self.selected))
        if recipe is None or not confirmed_unlocked(recipe):
            self._render_preview()
            self.d.message.text = '此配方已更新或尚未確認開放，請重新選取'
            return
        self.recipe(recipe)

    def queue_action(self, action, index):
        self.d.send(dict(type='craft', action=action, index=index, revision=self.state.get('crafting', {}).get('revision')),
                    '確認移除排程？材料是否退還依伺服器規則。' if action == 'delete' else None)
    def recipe(self, recipe):
        sid = recipe['item_id']; body = column(); body.add_widget(item_image(sid, 64))
        status, reason = availability(self.state, recipe)
        counts = owned_counts(self.state, sid)
        body.add_widget(label(item_name(sid)+f"\n產量 {recipe['output']}｜時間 {duration(recipe['seconds'])}\n"+
            f"設備：{item_name(recipe['tool_id'])} · {tool_status(self.state, recipe['tool_id'])}\n"+
            '背包 {}｜已擺 {}｜保管 {}｜排程產出 {}'.format(*(counts[k] if counts[k] is not None else '待同步' for k in ('bag','placed','stored','queued')))+
            '\n'+status+'：'+reason))
        count = field(body, '批數', 1, True); materials = label(); body.add_widget(materials)
        def refresh(*_):
            try:
                number = int(count.text)
                if number < 1: raise ValueError()
                materials.text = '\n'.join(f"{r['name']}：可用 {r['usable'] if r['usable'] is not None else '待同步'}／需求 {r['required']}" for r in material_rows(self.state, recipe, number))
            except ValueError: materials.text = '請輸入有效批數'
        count.bind(text=refresh); refresh()
        def favorite():
            prefs = copy.deepcopy(self.d.data.get('preferences') or {'favorites': [], 'plan': []})
            ids = prefs['favorites']; prefs['favorites'] = [i for i in ids if i != sid] if sid in ids else ids+[sid]
            if self.d.preferences(prefs): popup.dismiss()
        def add():
            try:
                number = int(count.text)
                state = SimpleNamespace(**self.state)
                r, allocations, _ = recipe_plan(state, sid, number)
                text = item_name(sid)+f" ×{r['output']*number}\n"+'\n'.join(f"{item_name(a['item_id'])} ×{a['count']}" for a in allocations)
                self.d.send(dict(type='craft', action='add', item_id=sid, count=number), text+'\n\n確認消耗背包材料並加入排程？')
            except (ValueError, KeyError, TypeError, AttributeError) as exc: self.d.message.text = str(exc)
        def plan_add():
            try:
                prefs = copy.deepcopy(self.d.data.get('preferences') or {'favorites': [], 'plan': []})
                prefs['plan'] = validate_rows(prefs['plan']+[dict(item_id=sid, count=int(count.text))])
                if self.d.preferences(prefs): popup.dismiss()
            except (ValueError, TypeError) as exc: self.d.message.text = str(exc)
        body.add_widget(row(button('切換收藏', favorite), button('加入自訂清單', plan_add)))
        body.add_widget(button('加入伺服器製作排程', add))
        popup = dialog('配方詳情', body)
    def plan(self): PlanEditor(self.d)


class PlanEditor:
    def __init__(self, d):
        from android_app.pages.ui_components import feature_card, status_line
        self.d = d
        self.rows = copy.deepcopy(
            d.data.get('preferences', {}).get('plan', []))
        self.offset = 0
        self.body = column()

        intro = feature_card(
            '自訂製作清單',
            '本地草稿不會自動開始製作，需手動保存及啟動')
        self.message = status_line(
            '編輯本地自訂清單；保存不會自動開始製作。')
        intro.add_widget(self.message)
        self.body.add_widget(intro)

        entries = feature_card('清單項目', '點選項目可修改批數與順序')
        self.list = column()
        entries.add_widget(self.list)
        entries.add_widget(row(
            button('上一頁', lambda: self.move(-1)),
            button('下一頁', lambda: self.move(1))))
        self.body.add_widget(entries)

        controls = feature_card('清單保存與交換',
                                '匯入和修改只更新草稿，需明確保存')
        controls.add_widget(row(
            button('保存清單', self.save),
            button('複製方案', self.export)))
        controls.add_widget(button('貼上匯入', self.import_plan))
        controls.add_widget(row(
            button('清空草稿', self.clear),
            button('取回服務剩餘清單', self.from_runtime)))
        self.body.add_widget(controls)

        execution = feature_card(
            '背景製作排程',
            '未確認的結果不直接重送；各項操作仍由服務核對')
        execution.add_widget(row(
            button('開始清單', self.start),
            button('暫停清單',
                   lambda: d.send(dict(type='craft', action='plan_pause')))))
        self.runtime_status = status_line('等待服務排程同步')
        execution.add_widget(self.runtime_status)
        self.body.add_widget(execution)
        self.popup = dialog('自訂製作清單', self.body)
        self.render()
        from kivy.clock import Clock
        self.timer = Clock.schedule_interval(self.runtime_refresh, 1)
        self.popup.bind(on_dismiss=lambda *_: self.timer.cancel())
        self.runtime_refresh()

    def runtime_refresh(self, *_):
        if self.d.closed: return False
        runtime = self.d.state.get('crafting', {}).get('local_plan', {})
        self.runtime_status.text = '服務清單狀態：'+runtime.get('status','尚未啟動')+f"\n待送出 {len(runtime.get('rows', []))} 項 · 已送入 {runtime.get('sent',0)} 項"
    def clear(self):
        from android_app.widgets import confirm
        def apply(): self.rows = []; self.render()
        apply()
    def from_runtime(self):
        self.rows = copy.deepcopy(self.d.state.get('crafting', {}).get('local_plan', {}).get('rows', []))
        self.render(); self.message.text = '已讀取服務剩餘清單到草稿，尚未保存'
    def move(self, delta): self.offset = max(0, self.offset+delta); self.render()
    def render(self):
        self.list.clear_widgets(); pages = max(1, (len(self.rows)+9)//10); self.offset = min(self.offset, pages-1)
        self.list.add_widget(label(f'{self.offset+1}/{pages} 頁 · {len(self.rows)} 項'))
        for i in range(self.offset*10, min(len(self.rows), self.offset*10+10)):
            value = self.rows[i]
            self.list.add_widget(button(f"{i+1}. {item_name(value['item_id'])} · {value['count']} 批（點選修改）", lambda n=i: self.edit(n)))
            self.list.add_widget(row(button('上移', lambda n=i: self.swap(n, -1)), button('下移', lambda n=i: self.swap(n, 1)), button('移除', lambda n=i: self.remove(n))))
    def swap(self, i, delta):
        if 0 <= i+delta < len(self.rows): self.rows[i], self.rows[i+delta] = self.rows[i+delta], self.rows[i]; self.render()
    def remove(self, i): self.rows.pop(i); self.render()
    def edit(self, i):
        body = column(); value = field(body, '批數', self.rows[i]['count'], True)
        popup = None
        def commit():
            try:
                rows = copy.deepcopy(self.rows); rows[i]['count'] = int(value.text); self.rows = validate_rows(rows)
                self.render(); popup.dismiss()
            except ValueError as exc: self.message.text = str(exc)
        body.add_widget(button('套用', commit)); popup = dialog('編輯批數', body, .5)
    def save(self):
        prefs = copy.deepcopy(self.d.data.get('preferences') or {'favorites': [], 'plan': []}); prefs['plan'] = self.rows
        if self.d.preferences(prefs): self.message.text = '已送出保存，等待服務確認'
    def export(self):
        Clipboard.copy(json.dumps(dict(format='wlre-crafting-plan', version=1, rows=self.rows), ensure_ascii=False, indent=2))
        self.message.text = '方案已複製，可貼到檔案保存或傳給電腦版'
    def import_plan(self):
        try:
            text = Clipboard.paste()
            if len(text) > 65536: raise ValueError('方案內容過長')
            data = json.loads(text)
            if not isinstance(data, dict) or data.get('format') != 'wlre-crafting-plan' or data.get('version') != 1: raise ValueError('方案格式不支援')
            self.rows = validate_rows(data['rows']); self.render(); self.message.text = '已載入草稿，尚未保存或執行'
        except (ValueError, KeyError, TypeError) as exc: self.message.text = str(exc)
    def start(self):
        try: rows = validate_rows(self.rows)
        except ValueError as exc: self.message.text = str(exc); return
        if not rows: self.message.text = '清單為空'; return
        revision = self.d.state.get('crafting', {}).get('local_plan', {}).get('revision', 0)
        from android_app.widgets import confirm
        def begin():
            if self.d.send(dict(type='craft', action='plan_set', rows=rows, revision=revision)):
                self.d.send(dict(type='craft', action='plan_start', revision=revision+1))
        begin()

