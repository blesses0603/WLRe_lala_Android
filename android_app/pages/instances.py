"""1262 官方副本／協力資料與受伺服器確認的安全房間操作。"""
from android_app.pages.general import Page
from android_app.widgets import label, button, row, select, pick, field, column, dialog
from wlre.services.instance_browser import entries_for, official_catalog


def catalog_rows(mode):
    """僅根據桌面版已驗證 1262 資料表建立手機顯示清單。"""
    return entries_for(mode)


def describe_entry(entry):
    """原始獎勵類型與道具 ID，不宣稱能領取或已解鎖。"""
    def shown(value):
        return str(value) if value is not None else "未提供"
    kind = {1: "一般", 2: "協力", 3: "特殊"}.get(entry.get("kind"), "未知")
    lines = [
        "{}｜{}副本｜編號 {}".format(entry["name"], kind, shown(entry.get("id"))),
        "資料變體 {}｜場景 {}".format(shown(entry.get("variant")), shown(entry.get("map_id"))),
        "最低等級 {}｜人數 {}～{}".format(
            shown(entry.get("min_level")), shown(entry.get("min_members")),
            shown(entry.get("max_members"))),
        "時間限制 {} 分｜房間數 {}（靜態資料）".format(
            shown(entry.get("time_minutes")), shown(entry.get("room_count"))),
        "官方資料表開放旗標：{}".format(
            "是" if entry.get("is_open") is True else
            "否" if entry.get("is_open") is False else "未提供"),
    ]
    awards = entry.get("awards") or []
    lines.append("官方獎勵資料：")
    lines.extend("槽位 {}｜類型 {}｜物品／項目 ID {}｜數量 {}".format(*award)
                 for award in awards[:16] if isinstance(award, list) and len(award) == 4)
    if not awards:
        lines.append("此筆未列出獎勵，不代表沒有獎勵")
    lines.append("※ 這是離線資料表，不是即時房間、可進場狀態或領獎資格。")
    return "\n".join(lines)


class InstanceCatalog(Page):
    def __init__(self, dashboard):
        super().__init__(dashboard)
        self.add_widget(label("副本／協力｜官方 1262 房間與獎勵"))
        self.add_widget(label(
            "下列操作只送出一次，結果以伺服器回覆為準；"
            "協力創房、入房可能消耗門票或點數。付費寶箱禁止自動購買。"))
        self.mode = select(self, "類型", ["一般／特殊副本", "協力副本"])
        self.mode.bind(text=lambda *_: self.render())
        self.info = label()
        self.add_widget(self.info)
        self.add_widget(button("搜尋／瀏覽副本清單", self.browse))
        self.add_widget(button("查詢伺服器房間（僅讀取）", self.query_rooms))
        self.add_widget(button("查看已同步房間清單／選擇加入", self.browse_rooms))
        self.add_widget(row(button("建立房間", self.create_room),
                            button("查詢房間成員", self.query_members)))
        self.add_widget(row(button("離開房間", self.leave_room),
                            button("準備／取消準備", self.toggle_standby)))
        self.add_widget(row(button("開始一般副本", self.start_room),
                            button("一般副本手動入場", self.enter_room)))
        self.add_widget(row(button("領取免費協力獎勵", self.claim_reward),
                            button("明確取消寶箱", self.cancel_reward)))
        self.add_widget(button("切換免費協力獎勵自動領取（預設關閉）", self.toggle_reward_auto))
        self.live_info = label("房間尚未同步；離線資料不代表即時房間。")
        self.add_widget(self.live_info)
        self.details = label("請選擇副本；此操作不會連線或消耗資源。")
        self.add_widget(self.details)
        self.render()

    def rows(self):
        return catalog_rows("coop" if self.mode.text == "協力副本" else "main")

    def render(self):
        try:
            rows = self.rows()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.info.text = "無法讀取已驗證的 1262 資料表：" + type(exc).__name__
            self.details.text = "此頁不可操作；請確認安裝包有完整官方資料。"
            return
        self.info.text = "本類已核對 {} 筆；僅代表靜態資料，不代表伺服器有空房。".format(len(rows))
        self.details.text = "請選擇副本；此操作不會連線或消耗資源。"

    def browse(self):
        try:
            choices = [(i, "{}｜等級 {}｜{}～{} 人｜ID {}".format(
                entry["name"], entry.get("min_level", "未提供"),
                entry.get("min_members", "?"), entry.get("max_members", "?"),
                entry.get("id", "?"))) for i, entry in enumerate(self.rows())]
        except (OSError, ValueError, KeyError, TypeError):
            self.d.message.text = "副本資料表無法驗證，已拒絕開啟清單"
            return
        if not choices:
            self.d.message.text = "此分類沒有已驗證資料"
            return
        # Capture the exact chosen category instead of reading a later Spinner value.
        rows = self.rows()
        pick("官方副本清單（僅查詢本機）", choices,
             lambda index: setattr(self.details, "text", describe_entry(rows[index])))

    def current_mode(self):
        return 'coop' if self.mode.text == '協力副本' else 'main'

    def query_rooms(self):
        if not self.d.live:
            self.d.message.text = '請先登入；離線資料不是即時房間'
            return
        # This is explicit, user-triggered, and never retries an unknown result.
        self.d.send({'type': 'instance_refresh', 'mode': self.current_mode()})

    def browse_rooms(self):
        if not self.d.live:
            self.d.message.text = '請先登入；離線不顯示過時的房間清單'
            return
        data = (self.state.get('instances') or {}).get(self.current_mode()) or {}
        if not data.get('ready'):
            self.d.message.text = '請先手動查詢，並等待伺服器 S85／S186 回覆'
            return
        rooms = data.get('rooms') or []
        if not rooms:
            self.d.message.text = '伺服器已回覆目前沒有房間'
            return
        rows = [(index, '房間 {}｜人數 {}｜{}'.format(
            item.get('room_id', '未知'), item.get('members', '?'),
            item.get('manager') or '房主 ID '+str(item.get('host_id', '?'))))
            for index, item in enumerate(rooms)]
        pick('伺服器房間（選擇後確認是否加入）', rows,
             lambda index: self.join_room(rooms[index], self.current_mode()))


    def _data(self, mode=None):
        return ((self.state.get('instances') or {}).get(mode or self.current_mode()) or {})

    def _send(self, action, mode=None, question=None, **values):
        if not self.d.live:
            self.d.message.text = '請先完成登入與伺服器同步'
            return
        self.d.send({'type': action, 'mode': mode or self.current_mode(), **values}, question)

    def create_room(self):
        mode = self.current_mode()
        rows = [item for item in self.rows() if mode == 'coop' or item.get('kind') == 1]
        if not self.d.live or not rows:
            self.d.message.text = '請先登入且具有可用的官方副本資料'
            return
        entries = [(i, '{}｜{} 人｜編號 {}'.format(
            item['name'], item.get('min_members', '?'), item.get('id')))
            for i, item in enumerate(rows)]
        pick('選擇要建立的官方副本', entries,
             lambda i: self._create_form(rows[i], mode))

    def _create_form(self, entry, mode):
        body = column()
        privacy = select(body, '房間類型', ['公開', '私人'])
        password = field(body, '私人房間密碼（4 位 ASCII 數字）')
        capacity = select(body, '協力房間人數', [str(i) for i in range(1, 9)]) if mode == 'coop' else None
        def submit():
            public = privacy.text == '公開'
            cmd = {'public': public, 'password': '' if public else password.text.strip()}
            if mode == 'main':
                cmd['map_id'] = entry['map_id']
            else:
                cmd.update(dungeon_id=entry['id'], player_count=int(capacity.text),
                           confirm_cost=True)
            question = ('確定建立{}房間「{}」？'.format(
                '協力' if mode == 'coop' else '一般副本', entry['name']) +
                ('\n可能消耗門票或點數，提交後不會自動重送。' if mode == 'coop' else
                 '\n建立結果需等待伺服器確認。'))
            self._send('instance_create', mode, question, **cmd)
            popup.dismiss()
        body.add_widget(row(button('下一步：確認建立', submit),
                            button('取消', lambda: popup.dismiss())))
        popup = dialog('建立副本房間', body, .8)

    def join_room(self, room, mode):
        self.details.text = ('伺服器房間資料：\n' +
                             '\n'.join('{}：{}'.format(k, v) for k, v in room.items()))
        if not self.d.live:
            return
        body = column()
        is_public = room.get('public') is True
        password = field(body, '私人房間密碼（公開房間免填）')
        body.add_widget(label('此操作只使用最新伺服器房間清單；結果不明禁止重試。'))
        def submit():
            cmd = {'room_id': room.get('room_id'),
                   'password': '' if is_public else password.text.strip()}
            if mode == 'main':
                cmd['sn'] = room.get('sn')
            else:
                cmd['confirm_cost'] = True
            self._send('instance_join', mode,
                '確定加入此房間？' +
                ('\n協力入房可能消耗門票或點數。' if mode == 'coop' else '') +
                '\n若伺服器沒有確認，請勿重送。', **cmd)
            popup.dismiss()
        body.add_widget(row(button('下一步：確認加入', submit),
                            button('取消', lambda: popup.dismiss())))
        popup = dialog('加入伺服器房間', body, .7)

    def query_members(self):
        room = self._data().get('room') or {}
        if type(room.get('room_id')) is not int:
            self.d.message.text = '請先確認目前所在的伺服器房間'
            return
        self._send('instance_members', room_id=room['room_id'])

    def leave_room(self):
        self._send('instance_leave', question='確定離開已確認的副本房間？\n未完成的協力獎勵不能被當成已結算。')

    def toggle_standby(self):
        room = self._data('coop').get('room') or {}
        standby = room.get('standby')
        if type(standby) is not bool:
            self.d.message.text = '協力準備狀態尚未由伺服器同步'
            return
        target = not standby
        self._send('instance_coop_standby', 'coop',
                   '確定{}？僅房主與全員到齊時可操作。'.format('準備' if target else '取消準備'),
                   standby=target)

    def start_room(self):
        self._send('instance_start', 'main',
                   '確定由房主開始一般副本？\n須符合官方人數要求，且伺服器房間名單完整。')

    def enter_room(self):
        self._send('instance_enter', 'main',
                   '確定進入已由伺服器確認開始的一般副本？\n入場結果不明不會重送。')

    def claim_reward(self):
        self._send('instance_reward_claim', 'coop',
                   '確定只領取伺服器確認的免費協力寶箱？\n需背包可靠同步且至少四格空位。',
                   action='free')

    def cancel_reward(self):
        self._send('instance_reward_cancel', 'coop',
                   '確定取消目前伺服器的協力寶箱？此操作不能還原，請再次確認。',
                   confirm_cancel=True)

    def toggle_reward_auto(self):
        enabled = bool(self._data('coop').get('auto_claim_enabled'))
        self._send('instance_auto_reward', 'coop',
                   '確定{}免費協力獎勵自動領取？\n只對免費寶箱生效，付費寶箱永不自動購買。'.format(
                       '關閉' if enabled else '開啟'),
                   enabled=not enabled)

    def refresh(self):
        data = (self.state.get('instances') or {}).get(self.current_mode()) or {}
        if not self.d.live:
            self.live_info.text = '離線／等待登入：僅能查看官方離線副本資料'
        elif not data.get('ready'):
            self.live_info.text = '房間未同步；請手動查詢，系統不會自動重送'
        else:
            room = data.get('room') or {}
            reward=self._data('coop').get('reward') or {}
            self.live_info.text = '{}\n伺服器房間 {} 間｜自己房間：{}\n房間成員：{} 人｜階段：{}\n協力獎勵：{}｜自動免費領獎：{}'.format(
                data.get('status', '已同步'), len(data.get('rooms') or []),
                room.get('room_id', '未確認'), len(data.get('members') or []),
                data.get('phase', '未知'),
                ('尚未同步' if not reward else '免費' if reward.get('open_reward') == 1
                 else '付費／其他' if reward.get('open_reward') == 2 else '無可領取寶箱'),
                '已開啟' if self._data('coop').get('auto_claim_enabled') else '關閉')
