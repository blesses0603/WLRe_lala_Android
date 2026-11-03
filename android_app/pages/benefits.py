"""福利 > 魔方：排程留在前景服務，關閉頁面不會停止。"""
import time
from android_app.pages.general import Page
from android_app.widgets import label, button, check


class Benefits(Page):
    def __init__(self, d):
        super().__init__(d)
        self.add_widget(label('福利 > 魔方'))
        self.auto = check(self, '自動開啟已分析完成的時間魔方', True)
        self.auto.bind(active=self.set_auto)
        self.info = label(); self.add_widget(self.info)
        self.open_button = button('開啟魔方', lambda: d.send(dict(type='time_cube', action='open')))
        self.add_widget(self.open_button)
        self.add_widget(label('最多儲存 3 次。等待伺服器確認可開啟次數；切換頁面與鎖屏後仍由背景服務處理。'))
        self.rendering = False

    def set_auto(self, _, enabled):
        if not self.rendering:
            self.d.send(dict(type='time_cube', action='auto', enabled=enabled))

    def refresh(self):
        cube = self.state.get('time_cube', {})
        self.rendering = True
        self.auto.active = cube.get('enabled', True)
        self.auto.disabled = not self.d.live
        self.rendering = False
        count = cube.get('count')
        lines = ['可開啟：{} / 3'.format(count) if cube.get('ready') else '可開啟：等待同步']
        deadline = cube.get('deadline')
        if count == 3:
            lines.append('儲存已滿')
        elif deadline is not None:
            sec = max(0, int(deadline-time.monotonic()))
            lines.append('分析中：{}時{:02d}分{:02d}秒'.format(sec//3600, sec//60%60, sec%60)
                         if sec else '等待伺服器確認分析完成')
        lines.append(cube.get('status', '等待魔方同步'))
        if not self.state.get('automation', {}).get('enabled', True):
            lines.append('全域自動接續已暫停')
        self.info.text = '\n\n'.join(lines)
        self.open_button.disabled = not (self.d.live and cube.get('ready') and count
                                        and not cube.get('pending') and not cube.get('uncertain'))
