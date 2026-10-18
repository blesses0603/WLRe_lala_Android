from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from android_app.pages.general import Page
from android_app.widgets import column, label, button, row, field, select, pick, dialog
from android_app.assets import item_image
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
        super().__init__(d); self.offset = 0
        self.kind = select(self, '顯示', ['包包', '超空間袋', '已確認特技'])
        self.storage_section = select(self, '超空間袋區域', ['儲藏室', '雜物櫃'])
        self.display = select(self, '包包檢視方式', ['大圖示（24 格）', '清單'])
        self.query = field(self, '搜尋名稱／ID')
        self.info = label(); self.add_widget(self.info)
        self.add_widget(button('使用 HP／SP 藥水儲存槽', self.storage))
        self.grid = GridLayout(cols=COLUMNS, spacing=dp(5), size_hint_y=None,
                               row_default_height=dp(112), row_force_default=True)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.add_widget(self.grid)
        self.rows = column(); self.add_widget(self.rows)
        self.add_widget(row(button('上一頁', lambda: self.move(-1)),
                            button('下一頁', lambda: self.move(1))))
        self.kind.bind(text=lambda *_: self.find())
        self.storage_section.bind(text=lambda *_: self.find())
        self.display.bind(text=lambda *_: self.find())
        self.query.bind(text=lambda *_: self.find())
    def find(self): self.offset = 0; self.key = None; self.refresh()
    def move(self, delta): self.offset = max(0, self.offset+delta); self.key = None; self.refresh()
    def refresh(self):
        state = self.state
        actual_inventory = state.get('inventory', {})
        read_only = self.kind.text == '超空間袋'
        storage = state.get('room_storage') or {}
        bucket = ('garage' if self.storage_section.text == '儲藏室'
                  else 'materials')
        inventory = (storage.get(bucket) or {}) if read_only else actual_inventory
        key = (str(inventory), str(state.get('knowledge')),
               str(state.get('battle_units')), self.query.text,
               self.kind.text, self.storage_section.text,
               self.display.text, self.offset)
        if key == self.key:
            return
        self.key = key
        search = self.query.text.strip().casefold()
        self.grid.clear_widgets()
        self.rows.clear_widgets()
        is_inventory = self.kind.text in ('包包', '超空間袋')
        if is_inventory:
            entries = visible_items(inventory, search) if inventory.get('ready') else []
        else:
            entries = [(a, skill) for a in actors(state, True)
                       for skill in skill_rows(state, a)
                       if search in (actor_label(a)+skill['name']+str(skill['id'])).casefold()]
        use_grid = is_inventory and self.display.text == '大圖示（24 格）'
        page_size = PAGE_SIZE if use_grid else 15
        pages = max(1, (len(entries)+page_size-1)//page_size)
        self.offset = min(self.offset, pages-1)
        if read_only:
            data_status = ('已同步' if inventory.get('ready')
                           else '等待伺服器同步；不會以普通背包資料代替')
            source = ('超空間袋／'+self.storage_section.text +
                      ' · 唯讀 ' + data_status)
        elif is_inventory:
            source = ('包包已同步' if actual_inventory.get('ready')
                      else '等待包包同步')
            source += ' · ' + ('數量可靠' if actual_inventory.get('reliable')
                              else '數量未確認')
        else:
            source = '已確認特技'
        self.info.text = source + (
            '\n{}/{} 頁 · {} 項{}'.format(
                self.offset+1, pages, len(entries),
                ' · 每頁 24 格' if use_grid else ''))
        for value in entries[self.offset*page_size:self.offset*page_size+page_size]:
            if is_inventory:
                index, record, name = value
                if use_grid:
                    self.grid.add_widget(IconBagCell(
                        index, record, name, self.show_item))
                else:
                    sid = record['item_id']
                    text = '#{} {} ×{}'.format(
                        index, name, record.get('count', 0))
                    if not read_only:
                        effects = '／'.join('{}+{}'.format(k.upper(), v)
                                           for k, v in heal_effects(sid).items())
                        text += '\n可用 {} · {}'.format(
                            available(inventory, str(index)), effects)
                    line = row(item_image(sid), button(
                        text, lambda n=index,v=record:self.show_item(n,v), 68))
                    line.height = dp(68)
                    self.rows.add_widget(line)
            else:
                actor, skill = value
                text = (actor_label(actor)+'｜'+skill['name']+
                    ' Lv.{} · SP {}\n'.format(skill['level'], skill['sp'])+
                    ('；'.join(skill['reasons']) or '基礎條件可用')+
                    ' · '+skill['source'])
                self.rows.add_widget(button(
                    text, lambda a=actor,v=skill:self.use_skill(a,v), 90))

    def show_item(self, index, record):
        read_only = self.kind.text == '超空間袋'
        storage = self.state.get('room_storage') or {}
        bucket = ('garage' if self.storage_section.text == '儲藏室'
                  else 'materials')
        inventory = ((storage.get(bucket) or {}) if read_only
                     else self.state.get('inventory') or {})
        current = (inventory.get('items') or {}).get(str(index))
        if not current or current.get('item_id') != record.get('item_id'):
            self.d.message.text = '此格位已更新，請重新開啟道具'
            self.key = None
            self.refresh()
            return
        info = item_details(inventory, index, current)
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
            popup.dismiss()
            self.use_item(current)
        if not read_only and info['available'] > 0 and info['effects'] and self.d.live:
            body.add_widget(button('使用已確認的 HP／SP 道具', action))
        body.add_widget(button('返回包包', lambda: popup.dismiss()))
        popup = dialog('道具詳情' + ('（遠端唯讀）' if read_only else ''), body, .74)

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
        super().__init__(d); self.target = None; self.modes = {}
        self.info = label(); self.add_widget(self.info)
        self.grid = GridLayout(cols=4, spacing=dp(3), size_hint_y=None, height=dp(340)); self.add_widget(self.grid)
        self.buttons = {}
        for r in range(1, 5):
            for c in range(1, 5):
                key = f'{c}:{r}'
                b = button(key+' 空位', lambda k=key: self.choose(k), 82)
                self.grid.add_widget(b); self.buttons[key] = b
        self.actions = column(); self.add_widget(self.actions)
        self.add_widget(button('本回合送出角色／夥伴指令', self.submit))
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
            if not u: view.text = key+' 空位'; continue
            status = '已離場' if u.get('exited') else '已陣亡' if u.get('hp', 0) <= 0 else f"{u.get('hp', '—')}/{u.get('max_hp', '—')}"
            name = u.get('name', '?'); element = {0:'無',1:'地',2:'水',3:'火',4:'風'}.get(u.get('element'), '?')
            view.text = ('◎ ' if self.target == key else '')+element+' '+name+'\n'+status
            view.background_color = (.3,.55,.65,1) if self.target == key else (.6,.7,.8,1)
        key = (str(units), str(self.modes), str(battle.get('commands')))
        if key != self.key:
            self.key = key; self.actions.clear_widgets()
            for actor in owned_units(s, False):
                key = slot(actor); mode = self.modes.get(key, 'normal')
                self.actions.add_widget(button(actor_label(actor)+'：'+ACTIONS[mode]+'｜'+str(battle.get('commands', {}).get(key, {}).get('status', '未下令')),
                                              lambda k=key: self.choose(k)))
