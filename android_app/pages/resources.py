from kivy.metrics import dp
from kivy.clock import Clock
from kivy.uix.gridlayout import GridLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from android_app.pages.general import Page
from android_app.widgets import column, label, button, row, field, select, pick, dialog
from android_app.assets import item_image, prefetch_item_icons
from android_app.bag_model import visible_items, item_details, PAGE_SIZE, COLUMNS, ICON_SIZE
from android_app.theme import surface, SURFACE, TEXT
from wlre.services.items.combat_resources import (CAT, item_name, available, heal_effects,
    field_context, food_command, skill_rows, learned_command)
from wlre.services.battle.battle_commands import owned_units, slot, action_command, ACTIONS


def actors(state, include_inactive=False):
    if state.get('battle', {}).get('active'): return owned_units(state, False)
    context, actor = field_context(state)
    result = list(context.get('battle_units', {}).values()) if state.get('player', {}).get('role_id') else []
    if include_inactive:
        existing = {a.get('npc_index') for a in result}
        for profile in state.get('knowledge', {}).get('companions', {}).values():
            if profile.get('index') in existing: continue
            result.append(dict(col=0, row=0, pid=profile.get('npc_id'), master_id=state.get('player', {}).get('role_id'),
                npc_index=profile.get('index'), name=CAT['npcs'].get(str(profile.get('npc_id')), {}).get('name','夥伴'),
                equips=profile.get('equips', []), **profile.get('stats', {})))
    return result


def actor_label(actor): return actor.get('name') or ('夥伴' if actor.get('master_id') else '角色')


def battle_guard(command, state):
    return dict(command, battle_count=state.get('battle_count'), round=state.get('battle', {}).get('round'))


ITEM_RENDER_BATCH = 6  # At most six icon widgets / decode operations per UI frame.


class IconBagCell(ButtonBehavior, BoxLayout):
    """Original item sprite with rounded touch target and stack count."""
    def __init__(self, index, record, name, callback, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         height=dp(112), spacing=dp(1), padding=(dp(3), dp(5)), **kwargs)
        surface(self, color=SURFACE, radius=13)
        image = AnchorLayout(size_hint_y=None, height=dp(75),
                             anchor_x='center', anchor_y='center')
        image.add_widget(item_image(record["item_id"], size=ICON_SIZE))
        self.add_widget(image)
        title = Label(text="×{} · {}".format(record.get("count", 0), name),
                      color=TEXT, font_size='10sp', size_hint_y=None,
                      height=dp(26), halign='center', valign='middle',
                      shorten=True, shorten_from='right')
        title.bind(width=lambda widget, width: setattr(
            widget, 'text_size', (max(1, width-dp(6)), widget.height)))
        self.add_widget(title)
        self.index = index
        self.bind(on_release=lambda *_: callback(index, record))


class Resources(Page):
    def __init__(self, d):
        super().__init__(d)
        from android_app.pages.ui_components import feature_card, status_line
        self.offset = 0
        self._render_event = None
        self._render_generation = 0
        self._pending_items = ()
        self._render_index = 0
        self._summary_text = ''
        self._use_grid = False
        self._is_inventory = True
        self._read_only = False
        self._render_inventory = {}
        self._selected_item = None
        self._selected_icon_id = None

        filters = feature_card('包包／超空間袋／特技', '選擇資料來源、檢視方式及搜尋條件')
        filters.add_widget(row(
            button('包包', lambda: setattr(self.kind, 'text', '包包')),
            button('超空間袋', lambda: setattr(self.kind, 'text', '超空間袋')),
            button('特技', lambda: setattr(self.kind, 'text', '已確認特技'))))
        self.kind = select(filters, '目前資料來源',
                           ['包包', '超空間袋', '已確認特技'])
        self.storage_section = select(
            filters, '超空間袋區域', ['儲藏室', '雜物櫃'])
        self.display = select(
            filters, '檢視方式', ['大圖示（24 格）', '清單'])
        self.query = field(filters, '搜尋名稱／ID')
        self.add_widget(filters)

        inventory = feature_card('道具與特技清單',
                                 '按格位顯示真實伺服器同步資料；點選可查看詳情')
        self.info = status_line()
        inventory.add_widget(self.info)
        self.grid = GridLayout(cols=COLUMNS, spacing=dp(6), size_hint_y=None,
                               row_default_height=dp(112), row_force_default=True)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        inventory.add_widget(self.grid)
        self.rows = column()
        inventory.add_widget(self.rows)
        inventory.add_widget(row(
            button('上一頁', lambda: self.move(-1)),
            button('下一頁', lambda: self.move(1))))
        self.add_widget(inventory)

        selection = feature_card('選取道具', '點選格位直接預覽；完整操作前再次核對')
        self.selected_info = status_line('點選包包或超空間袋格位查看道具資料')
        selection.add_widget(self.selected_info)
        self.selected_icon = AnchorLayout(size_hint_y=None, height=dp(72),
                                          anchor_x='left', anchor_y='center')
        selection.add_widget(self.selected_icon)
        self.selected_details = status_line('尚未選取道具；不顯示推測的效果')
        selection.add_widget(self.selected_details)
        self.selected_action = button('查看完整資料／使用已確認道具',
                                      self.open_selected_item, 56)
        self.selected_action.disabled = True
        selection.add_widget(self.selected_action)
        selection.add_widget(button(
            'HP／SP 藥水儲存槽', self.storage))
        self.add_widget(selection)

        self.kind.bind(text=lambda *_: self.find())
        self.storage_section.bind(text=lambda *_: self.find())
        self.display.bind(text=lambda *_: self.find())
        self.query.bind(text=lambda *_: self.find())
    def find(self):
        self.offset = 0
        self.key = None
        self._clear_selected()
        self.refresh()

    def move(self, delta):
        self.offset = max(0, self.offset + delta)
        self.key = None
        self._clear_selected()
        self.refresh()

    def _clear_selected(self):
        self._selected_item = None
        self._selected_icon_id = None
        self.selected_icon.clear_widgets()
        self.selected_info.text = '點選包包或超空間袋格位查看道具資料'
        self.selected_details.text = '尚未選取道具；不顯示推測的效果'
        self.selected_action.disabled = True

    def _selected_snapshot(self):
        """Resolve a selection against CURRENT inventory, never a stale cell."""
        selection = self._selected_item
        if selection is None:
            return None
        kind, section, index, item_id = selection
        if kind != self.kind.text or section != self.storage_section.text:
            return None
        if kind not in ('包包', '超空間袋'):
            return None
        read_only = kind == '超空間袋'
        if read_only:
            storage = self.state.get('room_storage') or {}
            bucket = 'garage' if section == '儲藏室' else 'materials'
            inventory = storage.get(bucket) or {}
        else:
            inventory = self.state.get('inventory') or {}
        record = (inventory.get('items') or {}).get(index)
        if not record or record.get('item_id') != item_id:
            return None
        return inventory, record, read_only, index

    def _show_preview(self, snapshot):
        inventory, record, read_only, index = snapshot
        info = item_details(inventory, index, record)
        self.selected_info.text = '{}（ID {}）｜格位 #{}｜持有 {}{}'.format(
            info['name'], info['id'], info['index'], info['count'],
            '｜超空間袋唯讀' if read_only else
            '｜可用 {}｜保留 {}'.format(info['available'], info['reserved']))
        self.selected_details.text = '已確認效果／屬性：' + '、'.join(info['lines'])
        if self._selected_icon_id != info['id']:
            self.selected_icon.clear_widgets()
            self.selected_icon.add_widget(item_image(info['id'], size=64))
            self._selected_icon_id = info['id']
        self.selected_action.disabled = False
        return info

    def _revalidate_selected(self):
        if self._selected_item is None:
            return
        snapshot = self._selected_snapshot()
        if snapshot is None:
            self._clear_selected()
            self.d.message.text = '選取格位已更新，請重新選擇道具'
        else:
            self._show_preview(snapshot)

    def close(self):
        """Do not leave image construction scheduled after closing a workspace."""
        self._cancel_render()

    def pause_render(self):
        """Stop offscreen image work; rebuild from current data on return."""
        if self._render_event is not None:
            self._cancel_render()
            self.key = None

    def _cancel_render(self):
        self._render_generation += 1
        if self._render_event is not None:
            self._render_event.cancel()
            self._render_event = None
        self._pending_items = ()
        self._render_index = 0

    def _view_key(self, state, inventory):
        """Avoid stringifying ALL knowledge and battle data for a bag view.

        The source snapshots may be mutated in place in preview/testing, so
        record a frozen fingerprint rather than relying on dict identity.
        Skill pages retain their full dependency scope so combat/learned
        updates cannot be masked by an over-aggressive cache.
        """
        options = (self.kind.text, self.storage_section.text,
                   self.display.text, self.query.text, self.offset)
        if self.kind.text in ('包包', '超空間袋'):
            return ('items', bool(inventory.get('ready')),
                    bool(inventory.get('reliable')),
                    repr(inventory.get('items')),
                    repr(inventory.get('reserved')), *options)
        # Skill rows depend on learned/equipped data, actor status and item
        # costs, not on unrelated NPC dialogues or whole-world knowledge.
        knowledge = state.get('knowledge') or {}
        return ('skills', repr(knowledge.get('player')),
                repr(knowledge.get('companions')),
                knowledge.get('active_npc_id'),
                repr(state.get('battle_units')),
                repr(state.get('battle')), repr(state.get('player')),
                repr(state.get('inventory')),
                *options)

    def refresh(self):
        state = self.state
        actual_inventory = state.get('inventory') or {}
        read_only = self.kind.text == '超空間袋'
        storage = state.get('room_storage') or {}
        bucket = 'garage' if self.storage_section.text == '儲藏室' else 'materials'
        inventory = (storage.get(bucket) or {}) if read_only else actual_inventory
        from wlre.services.world.item_image_database import source_token, current_catalog
        key = (source_token(),self._view_key(state, inventory))
        if key == self.key:
            return

        search = self.query.text.strip().casefold()
        is_inventory = self.kind.text in ('包包', '超空間袋')
        if is_inventory:
            entries = visible_items(inventory, search) if inventory.get('ready') else []
        else:
            entries = [(a, skill) for a in actors(state, True)
                       for skill in skill_rows(state, a)
                       if search in (actor_label(a) + skill['name'] + str(skill['id'])).casefold()]
        use_grid = is_inventory and self.display.text == '大圖示（24 格）'
        page_size = PAGE_SIZE if use_grid else 15
        pages = max(1, (len(entries) + page_size - 1) // page_size)
        self.offset = min(self.offset, pages - 1)

        # Cancel old batches before clearing widgets; pending callbacks must
        # not append stale items after a mode/search/page/server change.
        self._cancel_render()
        self.grid.clear_widgets()
        self.rows.clear_widgets()
        self.key = (source_token(),self._view_key(state, inventory))
        self._read_only = read_only
        self._is_inventory = is_inventory
        self._use_grid = use_grid
        self._render_inventory = inventory
        self._pending_items = tuple(entries[
            self.offset * page_size:(self.offset + 1) * page_size])
        self._render_index = 0

        if read_only:
            data_status = ('已同步' if inventory.get('ready')
                           else '等待伺服器同步；不會以普通背包資料代替')
            source = '超空間袋／' + self.storage_section.text + ' · 唯讀 ' + data_status
        elif is_inventory:
            source = ('包包已同步' if actual_inventory.get('ready')
                      else '等待包包同步')
            source += ' · ' + ('數量可靠' if actual_inventory.get('reliable')
                              else '數量未確認')
        else:
            source = '已確認特技'
        if is_inventory:
            source += ' · ' + ('官方圖示已同步' if current_catalog() is not None else '官方圖示尚未同步')
        self._summary_text = source + (
            '\n{}/{} 頁 · {} 項{}'.format(
                self.offset + 1, pages, len(entries),
                ' · 每頁 24 格' if use_grid else ''))
        self.info.text = self._summary_text
        self._revalidate_selected()
        self._render_chunk(self._render_generation)

    def _render_chunk(self, generation):
        """Bound item icon decoding and Kivy widget creation per frame."""
        if generation != self._render_generation:
            return
        self._render_event = None
        start = self._render_index
        stop = min(start + ITEM_RENDER_BATCH, len(self._pending_items))
        batch = self._pending_items[start:stop]
        if self._is_inventory and batch:
            # Read only the visible batch from the current official image database.
            prefetch_item_icons([record['item_id'] for _, record, _ in batch])
        for value in batch:
            if self._is_inventory:
                index, record, name = value
                if self._use_grid:
                    self.grid.add_widget(IconBagCell(
                        index, record, name, self.show_item))
                else:
                    sid = record['item_id']
                    text = '#{} {} ×{}'.format(index, name, record.get('count', 0))
                    if not self._read_only:
                        effects = '／'.join('{}+{}'.format(k.upper(), v)
                                           for k, v in heal_effects(sid).items())
                        text += '\n可用 {} · {}'.format(
                            available(self._render_inventory, str(index)), effects)
                    line = row(item_image(sid), button(
                        text, lambda n=index, v=record: self.show_item(n, v), 68))
                    line.height = dp(68)
                    self.rows.add_widget(line)
            else:
                actor, skill = value
                text = (actor_label(actor) + '｜' + skill['name'] +
                    ' Lv.{} · SP {}\n'.format(skill['level'], skill['sp']) +
                    ('；'.join(skill['reasons']) or '基礎條件可用') +
                    ' · ' + skill['source'])
                self.rows.add_widget(button(
                    text, lambda a=actor, v=skill: self.use_skill(a, v), 90))
        self._render_index = stop
        total = len(self._pending_items)
        if stop < total:
            self.info.text = self._summary_text + (
                '\n正在顯示本頁 {} / {} 項…'.format(stop, total))
            self._render_event = Clock.schedule_once(
                lambda _dt, g=generation: self._render_chunk(g), 0)
        else:
            self.info.text = self._summary_text
            self._pending_items = ()
            self._render_inventory = {}

    def show_item(self, index, record):
        """One tap updates a source-backed detail card without a modal."""
        source = self.kind.text
        if source not in ('包包', '超空間袋'):
            return
        section = self.storage_section.text
        self._selected_item = (source, section, str(index),
                               record.get('item_id'))
        snapshot = self._selected_snapshot()
        if snapshot is None:
            self._clear_selected()
            self.d.message.text = '此格位已更新，請重新選擇道具'
            self.key = None
            self.refresh()
            return
        self._show_preview(snapshot)

    def open_selected_item(self):
        """Detailed modal preserves existing manual actions and safety gates."""
        snapshot = self._selected_snapshot()
        if snapshot is None:
            self._clear_selected()
            self.d.message.text = '此格位已更新，請重新選擇道具'
            return
        inventory, record, read_only, index = snapshot
        info = self._show_preview(snapshot)
        body = column()
        body.add_widget(item_image(info['id'], size=64))
        body.add_widget(label('{}（ID {}）'.format(info['name'], info['id'])))
        body.add_widget(label('格位 #{}｜持有 {}{}'.format(
            info['index'], info['count'],
            '｜僅供檢視' if read_only else
            '｜可用 {}｜保留 {}'.format(info['available'], info['reserved']))))
        for line in info['lines']:
            body.add_widget(label(line))
        popup = None
        def action():
            # Inventory/availability may change while the popup is open.
            latest = self._selected_snapshot()
            if latest is None:
                self.d.message.text = '道具格位已更新，請重新選擇'
                popup.dismiss()
                self._clear_selected()
                return
            current_inventory, current, still_read_only, current_index = latest
            fresh = item_details(current_inventory, current_index, current)
            if (still_read_only or not self.d.live or
                    fresh['available'] <= 0 or not fresh['effects']):
                self.d.message.text = '目前無法使用此道具，請重新確認狀態'
                popup.dismiss()
                return
            popup.dismiss()
            # use_item() requires the original bag slot; it must never use a
            # stale record or a record missing its validated slot index.
            self.use_item(dict(current, index=current_index))
        if not read_only and info['available'] > 0 and info['effects'] and self.d.live:
            body.add_widget(button('使用已確認的 HP／SP 道具', action))
        body.add_widget(button('返回包包', lambda: popup.dismiss()))
        popup = dialog('道具詳情' + ('（遠端唯讀）' if read_only else ''),
                       body, .74)

    def storage(self):
        entries = [((a.get('npc_index',0),res),actor_label(a)+' 補'+res.upper()+' · 儲存槽 '+
                    str(self.state.get('potion_storage',{}).get(res,{}).get('value','待同步')))
                    for a in actors(self.state) for res in ('hp','sp')]
        def choose(value):
            index,resource=value
            self.d.send(dict(type='field_storage',npc_index=index,resource=resource), '確認使用藥水儲存槽補給？')
        pick('藥水儲存槽補給（非戰鬥）',entries,choose)
    def use_item(self, item):
        body = column(); body.add_widget(label(item_name(item['item_id'])+'｜選擇補給資源與目標'))
        popup = None
        state = self.state
        targets = actors(state)
        for target in targets:
            for resource in ('hp', 'sp'):
                def use(t=target, r=resource):
                    try:
                        if state.get('battle', {}).get('active'):
                            owned = [a for a in owned_units(state) if slot(a) not in state['battle'].get('commands', {})]
                            if not owned: raise ValueError('本回合沒有尚未下令的可操作單位')
                            cmd = food_command(state, owned[0], r, item['item_id'], slot(t), index=item['index'])
                            cmd = battle_guard(cmd, state)
                        else:
                            context, actor = field_context(state)
                            cmd = food_command(context, actor, r, item['item_id'], slot(t), True, index=item['index'])
                            cmd['npc_index'] = t.get('npc_index', 0)
                        self.d.send(cmd, '確認使用 '+item_name(item['item_id'])+' 補給 '+actor_label(t)+'？')
                        popup.dismiss()
                    except (ValueError, KeyError, TypeError) as exc: self.d.message.text = str(exc)
                body.add_widget(button(actor_label(target)+' 補'+resource.upper(), use))
        popup = dialog('使用道具', body)
    def use_skill(self, actor, skill):
        if not self.state.get('battle', {}).get('active'):
            self.d.message.text = '手動特技需在戰鬥回合內使用；生活與被動特技僅供檢視'; return
        def target(key):
            try:
                command = learned_command(self.state, actor, skill['id'], key)
                self.d.send(battle_guard(command, self.state))
            except (ValueError, KeyError, TypeError) as exc: self.d.message.text = str(exc)
        pick('選擇特技目標', [(key, value.get('name', key)+f" HP {value.get('hp', '—')}")
            for key, value in self.state.get('battle_units', {}).items()], target)


class Battle(Page):
    def __init__(self, d):
        super().__init__(d)
        from android_app.pages.ui_components import feature_card, status_line
        self.target = None
        self.modes = {}
        panel = feature_card('戰場陣形', '點選我方單位設定行動；敵方單位指定目標',
                             variant='highlight')
        self.info = status_line('等待戰場資料同步')
        panel.add_widget(self.info)
        self.grid = GridLayout(cols=4, spacing=dp(3),
                               size_hint_y=None, height=dp(340))
        panel.add_widget(self.grid)
        self.buttons = {}
        for r in range(1, 5):
            for c in range(1, 5):
                key = f'{c}:{r}'
                b = button(key+' 空位', lambda k=key: self.choose(k), 82)
                self.grid.add_widget(b)
                self.buttons[key] = b
        self.add_widget(panel)
        command_panel = feature_card('本回合行動',
                                     '伺服器確認前不推定命令已執行')
        self.actions = column()
        command_panel.add_widget(self.actions)
        command_panel.add_widget(button(
            '本回合送出角色／夥伴指令', self.submit, 56))
        self.add_widget(command_panel)
    def choose(self, key):
        unit = self.state.get('battle_units', {}).get(key)
        if not unit: return
        if unit in owned_units(self.state, False):
            pick('此單位的行動', list(ACTIONS.items()), lambda mode: self.set_mode(key, mode))
        else: self.target = key; self.key = None; self.refresh()
    def set_mode(self, key, mode): self.modes[key] = mode; self.key = None; self.refresh()
    def submit(self):
        s = self.state
        self.d.send(dict(type='battle_submit', battle_count=s.get('battle_count'), round=s.get('battle', {}).get('round'),
            actor_pids={slot(a): a['pid'] for a in owned_units(s)}, modes=dict(self.modes), target_slot=self.target))
    def refresh(self):
        s = self.state; battle = s.get('battle', {}); units = s.get('battle_units', {})
        round_key = s.get('battle_count'), battle.get('round')
        if getattr(self, 'round_key', None) != round_key:
            self.round_key = round_key; self.modes = {}; self.target = None
        self.info.text = ('戰鬥中' if battle.get('active') else '末次戰場')+f"｜第 {battle.get('round', 0)} 回合\n點選自己的單位設定行動；點選敵方指定目標。"
        for key, view in self.buttons.items():
            u = units.get(key)
            if not u:
                view.text = key+' 空位'
                from android_app.theme import style_button
                style_button(view, primary=False)
                continue
            status = '已離場' if u.get('exited') else '已陣亡' if u.get('hp', 0) <= 0 else f"{u.get('hp', '—')}/{u.get('max_hp', '—')}"
            name = u.get('name', '?'); element = {0:'無',1:'地',2:'水',3:'火',4:'風'}.get(u.get('element'), '?')
            view.text = ('◎ ' if self.target == key else '')+element+' '+name+'\n'+status
            from android_app.theme import style_button
            style_button(view, primary=self.target == key)
        key = (str(units), str(self.modes), str(battle.get('commands')))
        if key != self.key:
            self.key = key; self.actions.clear_widgets()
            for actor in owned_units(s, False):
                key = slot(actor); mode = self.modes.get(key, 'normal')
                self.actions.add_widget(button(actor_label(actor)+'：'+ACTIONS[mode]+'｜'+str(battle.get('commands', {}).get(key, {}).get('status', '未下令')),
                                              lambda k=key: self.choose(k)))
