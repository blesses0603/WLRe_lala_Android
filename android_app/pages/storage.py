"""儲藏室／雜物櫃存取；兩端庫存與回覆皆由共用核心確認。"""
from types import SimpleNamespace
from android_app.pages.general import Page
from android_app.widgets import label, button, select, field, pick
from wlre.services.items.catalog import item_display_name
from wlre.services.items.reservations import identity, available
from wlre.services.items.room_storage_transfer import plan_transfer


def transfer_command(state, selection, count):
    target, action, index, expected, bag_revision, storage_revision = selection
    source = state['inventory'] if action == 'deposit' else state['room_storage'][target]
    item = source.get('items', {}).get(str(index))
    if item is None or identity(item) != identity(expected):
        raise ValueError('物品身分已變更，請重新選取')
    text = str(count).strip()
    if not text.isascii() or not text.isdecimal() or not 1 <= len(text) <= 5:
        raise ValueError('數量請輸入 1～65535 的整數')
    command = dict(type='room_storage', target=target, action=action, index=index,
                   item_id=item['item_id'], count=int(text), bag_revision=bag_revision,
                   storage_revision=storage_revision)
    plan_transfer(SimpleNamespace(**state), command)
    return command


class Storage(Page):
    def __init__(self, d):
        super().__init__(d)
        self.selected = None
        self.target = select(self, '儲藏區域', ['儲藏室', '雜物櫃'])
        self.action = select(self, '操作', ['存入', '取出'])
        self.target.bind(text=lambda *_:self.clear())
        self.action.bind(text=lambda *_:self.clear())
        self.add_widget(button('選擇來源物品', self.browse))
        self.selection = label('請選擇物品'); self.add_widget(self.selection)
        self.count = field(self, '數量', '1', numeric=True)
        self.submit_button = button('送出存取', self.submit); self.add_widget(self.submit_button)
        self.status = label(); self.add_widget(self.status)

    def clear(self):
        self.selected = None
        self.selection.text = '請重新選擇物品'

    def browse(self):
        target = 'garage' if self.target.text == '儲藏室' else 'materials'
        action = 'deposit' if self.action.text == '存入' else 'withdraw'
        storage = self.state.get('room_storage', {})
        source = self.state.get('inventory', {}) if action == 'deposit' else storage.get(target, {})
        if not source.get('ready'):
            self.d.message.text = '來源庫存尚未同步'; return
        rows = [(int(k), dict(v)) for k, v in source.get('items', {}).items()]
        scene, role = self.state.get('player', {}).get('scene'), self.state.get('player', {}).get('role_id')
        revision = self.state.get('inventory', {}).get('revision'), storage.get('revision')
        def choose(n):
            if (scene, role) != (self.state.get('player', {}).get('scene'), self.state.get('player', {}).get('role_id')):
                self.d.message.text = '場景或角色已改變，請重新選擇'; return
            index, item = rows[n]
            self.selected = (target, action, index, item, *revision)
            self.selection.text = '{}｜格位 {}｜可用 {}'.format(item_display_name(item['item_id']), index, available(source, index))
        pick('來源物品', [(i, '{} ×{}｜格位 {}'.format(item_display_name(v['item_id']), v.get('count', 0), k))
                         for i, (k, v) in enumerate(rows)], choose)

    def submit(self):
        if not self.selected:
            self.d.message.text = '請選擇來源物品'; return
        try:
            command = transfer_command(self.state, self.selected, self.count.text)
            if self.d.send(command): self.clear()
        except (ValueError, KeyError, TypeError) as exc:
            self.d.message.text = str(exc)

    def refresh(self):
        storage = self.state.get('room_storage', {})
        self.status.text = storage.get('status', '等待儲藏空間同步')
        self.submit_button.disabled = not self.d.live or bool(storage.get('pending') or storage.get('uncertain'))
