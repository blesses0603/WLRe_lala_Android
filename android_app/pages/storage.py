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
        from android_app.pages.ui_components import feature_card, status_line

        self.selected = None

        selector = feature_card(
            '儲藏空間與操作', '存入／取出都要核對兩端庫存版次與物品身分')
        self.target = select(selector, '儲藏區域', ['儲藏室', '雜物櫃'])
        self.action = select(selector, '操作', ['存入', '取出'])
        self.target.bind(text=lambda *_: self.clear())
        self.action.bind(text=lambda *_: self.clear())
        self.add_widget(selector)

        item = feature_card('選取來源道具',
                            '物品須來自已同步的背包或對應儲藏空間',
                            variant='highlight')
        item.add_widget(button('選擇來源物品', self.browse))
        self.selection = status_line('請選擇物品')
        item.add_widget(self.selection)
        self.count = field(item, '本次數量（1～65535）', '1', numeric=True)
        self.submit_button = button('確認送出存取', self.submit, 56)
        item.add_widget(self.submit_button)
        self.add_widget(item)

        feedback = feature_card('存取狀態',
                                '未確認的送出結果不得自動重送')
        self.status = status_line('等待儲藏空間同步')
        feedback.add_widget(self.status)
        self.add_widget(feedback)

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
