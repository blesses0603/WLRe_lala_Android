"""Touch-first manual partner deployment; game server owns final state."""
from android_app.pages.general import Page
from android_app.widgets import label, button, row
from wlre.services.battle.companions import problem
from wlre.services.items.combat_resources import CAT


def companion_rows(state):
    knowledge = state.get("knowledge", {})
    current = knowledge.get("active_npc_id")
    result = []
    for index, p in sorted((knowledge.get("companions") or {}).items(),
                           key=lambda pair: int(pair[0])):
        info = CAT["npcs"].get(str(p.get("npc_id")), {})
        stats = p.get("stats") or {}
        result.append({
            "index": int(index), "npc_id": p.get("npc_id"),
            "name": info.get("name") or p.get("name") or "夥伴 {}".format(index),
            "active": p.get("npc_id") == current,
            "level": stats.get("level", "—"),
            "hp": stats.get("hp", "—"), "max_hp": stats.get("max_hp", "—"),
            "sp": stats.get("sp", "—"), "max_sp": stats.get("max_sp", "—"),
            "faith": p.get("faith", "—"),
            "reasons": {action: problem(state, int(index), p.get("npc_id"), action)
                        for action in ("deploy", "rest")},
        })
    return result


class Companions(Page):
    def __init__(self, d):
        super().__init__(d)
        from android_app.pages.ui_components import feature_card, status_line
        summary=feature_card('夥伴出戰', '出戰與休息由伺服器確認，不先顯示成功')
        self.title=status_line(
            '出戰前需停止自動戰鬥、徘徊及衝突活動')
        summary.add_widget(self.title)
        self.info=status_line()
        summary.add_widget(self.info)
        self.add_widget(summary)
        self.items=__import__(
            'android_app.widgets', fromlist=['column']).column()
        self.add_widget(self.items)
        self._signature=None

    def change(self, partner, action):
        reason = problem(self.state, partner["index"], partner["npc_id"], action)
        if reason:
            self.d.message.text = reason
            return
        self.d.send({
            "type": "companion", "index": partner["index"],
            "npc_id": partner["npc_id"], "action": action,
        }, "確認{}「{}」？切換後需等待伺服器回覆。".format(
            "出戰" if action == "deploy" else "休息", partner["name"]))

    def refresh(self):
        from android_app.pages.ui_components import feature_card, status_line
        knowledge=self.state.get('knowledge',{})
        if not knowledge.get('companions_ready'):
            self.info.text='等待伺服器同步夥伴清單'
            self._signature=None
            self.items.clear_widgets()
            return
        rows=companion_rows(self.state)
        signature=repr((rows,self.d.live))
        if signature==self._signature:
            return
        self._signature=signature
        self.info.text='已同步 {} 名夥伴，切換需等待伺服器回覆'.format(
            len(rows))
        self.items.clear_widgets()
        if not rows:
            self.items.add_widget(status_line('目前沒有已確認的夥伴'))
        for item in rows:
            status='● 出戰中' if item['active'] else '○ 休息中'
            card=feature_card(item['name'],
                              'Lv.{}｜{}'.format(item['level'],status),
                              variant='highlight' if item['active'] else 'normal')
            card.add_widget(status_line(
                'HP {}/{}　SP {}/{}'.format(
                    item['hp'],item['max_hp'],item['sp'],item['max_sp'])))
            card.add_widget(status_line(
                '忠誠／好友度：{}'.format(item['faith'])))
            deploy=button(
                '設為出戰',
                lambda p=item:self.change(p,'deploy'))
            rest=button(
                '讓夥伴休息',
                lambda p=item:self.change(p,'rest'))
            deploy.disabled=bool(item['reasons']['deploy']) or not self.d.live
            rest.disabled=bool(item['reasons']['rest']) or not self.d.live
            card.add_widget(row(deploy,rest))
            reasons=[v for v in item['reasons'].values() if v]
            if reasons:
                card.add_widget(status_line(
                    '操作限制：'+'／'.join(dict.fromkeys(reasons))))
            self.items.add_widget(card)
