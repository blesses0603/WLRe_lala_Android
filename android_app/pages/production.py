import copy
import json
from types import SimpleNamespace
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from android_app.theme import surface, style_input, SOFT, MUTED, ACCENT
from kivy.core.clipboard import Clipboard
from android_app.pages.general import Page
from android_app.widgets import column, label, button, row, field, select, dialog, pick
from android_app.assets import item_image
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
        from android_app.pages.ui_components import feature_card, status_line
        self.materials = [None]*5

        setup = feature_card('煉金設定',
                             '模式與次數必須由原有煉金核心驗證',
                             show_icon=not compact)
        if compact:
            # Adjacent controls consume one short row instead of two stacked
            # full-width forms on an actual narrow phone.
            controls = BoxLayout(
                orientation='horizontal', spacing=dp(8),
                size_hint_y=None, height=dp(94))
            mode_box = BoxLayout(orientation='vertical')
            count_box = BoxLayout(orientation='vertical')
            self.mode = select(mode_box, '煉金術', ['無技能'])
            self.runs = field(count_box, '執行次數', 1, True)
            self.mode.font_size = self.runs.font_size = '13sp'
            controls.add_widget(mode_box)
            controls.add_widget(count_box)
            setup.add_widget(controls)
        else:
            self.mode = select(setup, '煉金術', ['無技能'])
            self.runs = field(setup, '執行次數（1～999）', 1, True)
            self.add_widget(setup)

        materials = feature_card(
            '材料槽位',
            '五格顯示背包已選材料；每次數量為本地草稿，確認後才送出',
            show_icon=not compact)
        self.slots = []
        if compact:
            # Show the actual material slots before setup inputs. Three
            # columns fit a 320dp viewport without five full nested forms.
            self.material_grid = GridLayout(
                cols=3, spacing=dp(5), size_hint_y=None,
                row_default_height=dp(148), row_force_default=True)
            self.material_grid.bind(
                minimum_height=self.material_grid.setter('height'))
            self.material_grid.bind(
                width=lambda grid, width: setattr(
                    grid, 'cols', 2 if width < dp(245) else 3))
            for index in range(5):
                tile = surface(BoxLayout(
                    orientation='vertical', spacing=dp(3),
                    padding=[dp(5), dp(5), dp(5), dp(5)],
                    size_hint_y=None, height=dp(148)),
                    color=SOFT, radius=13)
                icon = AnchorLayout(size_hint_y=None, height=dp(48))
                self.material_icons[index] = icon
                tile.add_widget(icon)
                control = button('材料 {}'.format(index+1),
                                 lambda i=index: self.choose(i), 38)
                control.font_size = '11sp'
                control.shorten = True
                tile.add_widget(control)
                tile.add_widget(Label(
                    text='每次數量', color=MUTED, font_size='10sp',
                    size_hint_y=None, height=dp(16)))
                count = style_input(TextInput(
                    text='1', multiline=False, input_filter='int',
                    input_type='number', font_size='14sp',
                    size_hint_y=None, height=dp(36)))
                tile.add_widget(count)
                self.slots.append((control, count))
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
        self.add_widget(materials)
        if compact:
            # The original order buried the material tray below a long
            # settings form. Keep five actionable slots visible first.
            self.add_widget(setup)

        actions = feature_card('煉金佇列與執行',
                               '預覽本次總消耗，確認後才送出',
                               show_icon=not compact)
        self.info = status_line('等待煉金狀態同步')
        actions.add_widget(self.info)
        actions.add_widget(button('預覽消耗／開始連續煉金', self.begin, 56))
        actions.add_widget(row(
            button('停止後續煉金', lambda: d.send({'type':'stop_alchemy'})),
            button('清空材料', self.clear)))
        self.add_widget(actions)
    def _show_material_icon(self, index, value):
        """Only a selected, server-sourced item receives an original sprite."""
        if not self.compact:
            return
        holder = self.material_icons[index]
        holder.clear_widgets()
        if value is None:
            holder.add_widget(Label(
                text='＋', color=ACCENT, font_size='28sp'))
        else:
            holder.add_widget(item_image(value['item_id'], size=42))

    def clear(self):
        self.materials = [None]*5
        for i, (b, _) in enumerate(self.slots):
            b.text = ('材料 {}'.format(i+1) if self.compact
                      else f'材料 {i+1}：選擇')
            self._show_material_icon(i, None)
    def choose(self, index):
        entries = [(None, '清除此格')] + [(dict(v), f"#{v['index']} {item_name(v['item_id'])} ×{v['count']}")
            for v in self.state.get('inventory', {}).get('items', {}).values() if not material_problem(v)]
        pick('選擇背包材料', entries, lambda value: self.set_slot(index, value))
    def set_slot(self, index, value):
        self.materials[index] = value
        if self.compact:
            self.slots[index][0].text = (
                '格位 #{}'.format(value['index']) if value
                else '材料 {}'.format(index+1))
            self._show_material_icon(index, value)
        else:
            self.slots[index][0].text = f'材料 {index+1}：'+(f"#{value['index']} {item_name(value['item_id'])}" if value else '選擇')
    def begin(self):
        try:
            command = dict(type='start_alchemy', mode=self.mode.text, runs=int(self.runs.text), materials=[
                dict(index=v['index'], item_id=v['item_id'], count=int(self.slots[i][1].text))
                for i, v in enumerate(self.materials) if v])
            state = SimpleNamespace(**self.state); state.snapshot = lambda: self.state
            plan = prepare(state, command)
            text = f"{plan['mode']}煉金，共 {plan['runs']} 次\n"+'\n'.join(
                f"#{v['index']} {item_name(v['item_id'])} 每次 {v['count']}，共消耗 {v['count']*plan['runs']}" for v in plan['consumption'])
            self.d.send(command, text+'\n\n確認消耗材料並開始？')
        except (ValueError, KeyError, TypeError, AttributeError) as exc: self.d.message.text = str(exc)
    def refresh(self):
        options = modes(self.state); self.mode.values = options
        if self.mode.text not in options and options: self.mode.text = options[-1]
        a = self.state.get('alchemy', {}); busy = a.get('enabled') or a.get('pending')
        self.mode.disabled = self.runs.disabled = bool(busy)
        for b, count in self.slots: b.disabled = count.disabled = bool(busy)
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

        browse = feature_card('製作工坊 · 配方目錄',
                              '只列已確認開放配方，可依設備與收藏篩選',
                              show_icon=not compact)
        browse.add_widget(row(
            button('自訂清單', self.plan),
            button('進入自家帳篷',
                   lambda: d.send(dict(type='craft', action='enter')))))
        self.query = field(browse, '搜尋配方名稱／ID')
        self.tool = select(browse, '工作設備／收藏', ['全部', '我的最愛'])
        self.only_owned = select(
            browse, '顯示配方', ['全部已確認開放配方', '只列小屋已擺設備'])
        if compact:
            self.catalog_status = status_line('等待已確認配方')
            browse.add_widget(self.catalog_status)
            self.catalog = GridLayout(
                cols=2, spacing=dp(7), size_hint_y=None,
                row_default_height=dp(156), row_force_default=True)
            self.catalog.bind(
                minimum_height=self.catalog.setter('height'))
        else:
            self.catalog = column()
            self.catalog.spacing = dp(9)
        browse.add_widget(self.catalog)
        browse.add_widget(row(
            button('‹ 上一頁', lambda: self.move(-1)),
            button('下一頁 ›', lambda: self.move(1))))
        self.add_widget(browse)

        if compact:
            # One in-page recipe detail panel; the existing verified recipe
            # dialog remains the only way to add to the server queue.
            preview = feature_card(
                '目前選取配方', '點選配方先檢視已核對的設備與材料，送出需再次確認',
                show_icon=False)
            self.preview_image = AnchorLayout(
                anchor_x='left', size_hint_y=None, height=dp(70))
            preview.add_widget(self.preview_image)
            self.preview_info = status_line('點選上方配方以查看需求')
            preview.add_widget(self.preview_info)
            self.preview_action = button(
                '開啟配方詳情／加入排程', self.open_preview, 56)
            self.preview_action.disabled = True
            preview.add_widget(self.preview_action)
            self.add_widget(preview)

        execution = feature_card('伺服器製作佇列',
                                 '順序、用料與剩餘時間由已同步狀態確認',
                                 variant='highlight',
                                 show_icon=not compact)
        self.queue_info = status_line('等待排程同步')
        execution.add_widget(self.queue_info)
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
                # Two-column icon catalog for the paired screen. The full
                # standalone list and original recipe confirmation stay intact.
                card = surface(BoxLayout(
                    orientation='vertical', spacing=dp(3),
                    padding=[dp(7), dp(6), dp(7), dp(6)],
                    size_hint_y=None, height=dp(156)),
                    color=SOFT, radius=13)
                header = BoxLayout(
                    orientation='horizontal', spacing=dp(5),
                    size_hint_y=None, height=dp(58))
                header.add_widget(item_image(sid, 48))
                name = label(
                    ('♥ ' if sid in favorites else '') + item_name(sid), 50)
                name.font_size = '12sp'
                header.add_widget(name)
                card.add_widget(header)
                state_line = label(
                    status + ' · ' + item_name(recipe['tool_id']), 31)
                state_line.font_size = '10sp'
                state_line.color = MUTED
                card.add_widget(state_line)
                card.add_widget(button(
                    '預覽配方', lambda r=recipe: self.preview_recipe(r),
                    44))
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
        lines.extend(
            '{}：可用 {}／需求 {}'.format(
                r['name'], r['usable'] if r['usable'] is not None
                else '待同步', r['required'])
            for r in requirements)
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

