"""1262 官方副本資料唯讀瀏覽。此頁不查詢／建立房間，也不發送遊戲封包。"""
from android_app.pages.general import Page
from android_app.widgets import label, button, row, select, pick
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
        self.add_widget(label("副本／協力｜1262 官方資料（唯讀）"))
        self.add_widget(label(
            "目前僅能查看已驗證的副本種類、參與條件與獎勵資料。"
            "尚未接入房間查詢、建立／加入、準備、開始或領獎操作。"))
        self.mode = select(self, "類型", ["一般／特殊副本", "協力副本"])
        self.mode.bind(text=lambda *_: self.render())
        self.info = label()
        self.add_widget(self.info)
        self.add_widget(button("搜尋／瀏覽副本清單", self.browse))
        self.add_widget(button("查詢伺服器房間（僅讀取）", self.query_rooms))
        self.add_widget(button("查看已同步房間清單", self.browse_rooms))
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
        pick('伺服器房間（只讀）', rows,
            lambda index: setattr(self.details, 'text',
                '伺服器房間資料（不可直接加入）：\n' +
                '\n'.join('{}：{}'.format(k, v) for k, v in rooms[index].items())))

    def refresh(self):
        data = (self.state.get('instances') or {}).get(self.current_mode()) or {}
        if not self.d.live:
            self.live_info.text = '離線／等待登入：僅能查看官方離線副本資料'
        elif not data.get('ready'):
            self.live_info.text = '房間未同步；請手動查詢，系統不會自動重送'
        else:
            room = data.get('room') or {}
            self.live_info.text = '{}\n伺服器房間 {} 間｜自己房間：{}'.format(
                data.get('status', '已同步'), len(data.get('rooms') or []),
                room.get('room_id', '尚未由伺服器確認'))
