"""Touch NPC roster, dialogue, verified choices and read-only shops."""
from android_app.pages.general import Page
from android_app.widgets import label, button, row, pick
from wlre.services.world.npc_catalog import NPCIndex, scene_npcs
from wlre.services.world.npc_interact import NPCInteractIndex
from wlre.services.world.npc_talk import load_catalog
from wlre.services.world.npc_shop import shop_catalog
from wlre.services.world.dynamic_bundle_runtime import current_catalog_token


class NPC(Page):
    def __init__(self, d):
        super().__init__(d)
        from android_app.pages.ui_components import feature_card, status_line

        self.selected = None
        self.selection_token = None

        nearby = feature_card(
            '目前場景 NPC', '只從已驗證官方場景索引挑選 NPC')
        self.scene_info = status_line('等待角色所在場景')
        nearby.add_widget(self.scene_info)
        nearby.add_widget(button('選擇目前場景 NPC', self.browse))
        self.selection = status_line('尚未選擇 NPC')
        nearby.add_widget(self.selection)
        nearby.add_widget(row(
            button('前往並接續互動',
                   lambda: self.act('npc_approach')),
            button('與所選 NPC 互動',
                   lambda: self.act('npc_start'))))
        self.add_widget(nearby)

        talk = feature_card('NPC 對話',
                            '僅顯示官方已驗證文字與伺服器最新對話狀態',
                            variant='highlight')
        talk.add_widget(button(
            '接續對話',
            lambda: d.send(dict(type='npc_next'))))
        self.info = status_line('等待 NPC 對話狀態同步')
        talk.add_widget(self.info)
        self.add_widget(talk)

        choices = feature_card('選項／商店資訊',
                               '未知對話不自動代選；商店價格僅供查閱')
        self.options = None
        from android_app.widgets import column
        self.actions = column()
        choices.add_widget(self.actions)
        self.add_widget(choices)

    def browse(self):
        scene = self.state.get('player', {}).get('scene')
        try:
            token = current_catalog_token()
            rows = scene_npcs(scene, [], NPCIndex())
            def choose(index):
                if scene != self.state.get('player', {}).get('scene') or token != current_catalog_token():
                    self.d.message.text = '場景或官方資料已更新，請重新選擇'; return
                self.selected = rows[index]
                self.selection_token = token
                self.selection.text = self.selected['name']+'｜事件索引 '+str(self.selected['npc_index'])
            pick('NPC 清單', [(i, r['name']+'｜索引 '+str(r['npc_index'])) for i, r in enumerate(rows)], choose)
        except (ValueError, OSError, RuntimeError):
            self.d.message.text = '目前官方 NPC 索引尚未完成驗證'

    def act(self, kind):
        r = self.selected
        if (not r or r['scene'] != self.state.get('player', {}).get('scene')
                or self.selection_token != current_catalog_token()):
            self.d.message.text = '請重新選擇目前場景的 NPC'; return
        self.d.send(dict(type=kind, confirmed=True, scene=r['scene'], npc_index=r['npc_index'],
                         npc_id=r['npc_id'], x=r['x'], y=r['y']))

    def choose(self, scene, index, option):
        self.d.send(dict(type='npc_choose', confirmed=True, scene=scene,
                         interact_index=index, choice=option['choice'], text_id=option['text_id']))

    def refresh(self):
        scene = self.state.get('player', {}).get('scene')
        self.scene_info.text = ('目前場景 ID：{}'.format(scene)
                                if scene is not None else '等待角色所在場景同步')
        info = self.state.get('npc_dialogue', {})
        key = (repr(info), current_catalog_token(), self.d.live)
        if key == self.key: return
        self.key = key
        self.actions.clear_widgets()
        lines = [info.get('reason') or '對話狀態：'+info.get('phase', 'idle')]
        try:
            talks = load_catalog()
            for ident in (info.get('history') or [])[-50:]:
                lines.append(talks.get(ident, '未取得對話文字 ID '+str(ident)))
            if info.get('active') and info.get('phase') == 'choice_unavailable':
                scene, index = info.get('scene'), info.get('option_index')
                choices = NPCInteractIndex().choices(scene, index, talks)
                shop = shop_catalog(scene, index)
                if choices:
                    lines.append(choices['title'])
                    for option in choices['options']:
                        self.actions.add_widget(button(option['text'],
                            lambda o=option,s=scene,i=index:self.choose(s,i,o), 64))
                    self.actions.add_widget(button('關閉選項', lambda:self.d.send(dict(type='npc_close_choice', confirmed=True))))
                elif shop:
                    lines.extend([shop['title'], shop['reason']])
                    gold = self.state.get('gold', {})
                    lines.append('持有金幣：'+(str(gold.get('amount')) if gold.get('ready') and gold.get('reliable') else '待同步'))
                    for p in shop['products']:
                        lines.append('{}｜基礎買價 {}｜收購價 {}'.format(p['name'], p['price_gold'], p['sell_price_gold']))
                    self.actions.add_widget(button('關閉商店', lambda:self.d.send(dict(type='npc_close_shop', confirmed=True))))
                else:
                    lines.append('選項資料尚未核對，不代選答案')
                    self.actions.add_widget(button('關閉選項', lambda:self.d.send(dict(type='npc_close_choice', confirmed=True))))
        except (ValueError, OSError, RuntimeError, EOFError):
            lines.append('官方文字或選項資料尚未通過驗證')
        self.info.text = '\n\n'.join(lines)
