import copy
from android_app.pages.general import Page
from android_app.widgets import column, label, button, row, field, select, pick, confirm
from wlre.services.battle.party import own_team, player_name
from wlre.services.social.chat import CHANNELS, plain_text


class Party(Page):
    def __init__(self, d):
        if getattr(d, 'page_name', '') == '組隊管理':
            Page.__init__(self, d, embedded=True, show_title=False)
            self.compact=True
            self._build_compact()
            return
        super().__init__(d)
        self.compact=False
        from android_app.pages.ui_components import feature_card, status_line
        controls = feature_card('組隊管理', '邀請附近玩家、申請入隊或管理既有隊伍')
        self.info = status_line()
        controls.add_widget(self.info)
        self.target = field(controls, '目標角色 ID（可由附近玩家選取）', numeric=True)
        controls.add_widget(row(
            button('選擇附近玩家', self.choose_nearby),
            button('必要成員設定', self.guard)))
        controls.add_widget(row(
            button('邀請組隊', lambda: self.act('invite')),
            button('申請入隊', lambda: self.act('apply'))))
        controls.add_widget(row(
            button('開關組隊邀請', self.flag),
            button('離隊／解散', lambda: d.send(
                {'type': 'team', 'action': 'leave'},
                '確認離開隊伍？隊長離隊會解散隊伍。'))))
        self.add_widget(controls)
        nearby = feature_card('附近玩家', '只顯示與目前角色同場景的玩家')
        self.nearby_preview = status_line()
        nearby.add_widget(self.nearby_preview)
        nearby.add_widget(button('選擇玩家並操作', self.choose_nearby))
        self.add_widget(nearby)
        team = feature_card('我的隊伍', '伺服器已確認的隊員與隊長')
        self.members = column()
        team.add_widget(self.members)
        self.add_widget(team)
        requests = feature_card('待確認邀請／申請', '接受與拒絕均等待伺服器回覆')
        self.requests = column()
        requests.add_widget(self.requests)
        self.add_widget(requests)

    def _build_compact(self):
        """Condensed server-backed party area, with three genuine views."""
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput
        from android_app.theme import MUTED, style_input, style_button
        from android_app.pages.social_visual import (
            SocialButton, SocialIcon, caption, heading, glass_card)

        self.page_index=0
        self.party_tab='附近玩家'
        self.info=caption('等待組隊資料同步',height=24)
        self.nearby_preview=caption('',height=20)
        self.members=BoxLayout(orientation='vertical',size_hint_y=None)
        self.members.bind(minimum_height=self.members.setter('height'))
        self.requests=BoxLayout(orientation='vertical',size_hint_y=None)
        self.requests.bind(minimum_height=self.requests.setter('height'))
        board=glass_card(bright=True,padding=7,gap=5)
        title=BoxLayout(size_hint_y=None,height=dp(31),spacing=dp(6))
        title.add_widget(heading('組隊管理',icon='users'))
        self.add_widget(board)
        board.add_widget(title)
        board.add_widget(self.info)
        tabs=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(5))
        self.party_tabs={}
        for name,symbol in (('附近玩家','pin'),('組隊申請','message'),
                            ('我的隊伍','users')):
            btn=SocialButton(name,lambda k=name:self._select_party_tab(k),
                             icon=symbol,height=38,font='11sp')
            self.party_tabs[name]=btn
            tabs.add_widget(btn)
        board.add_widget(tabs)
        self.scroll=ScrollView(do_scroll_x=False,bar_width=dp(2),
                               size_hint_y=None,height=dp(163))
        self.entries=BoxLayout(orientation='vertical',size_hint_y=None,
                               spacing=dp(4),padding=[dp(2),dp(3)])
        self.entries.bind(minimum_height=self.entries.setter('height'))
        self.scroll.add_widget(self.entries)
        board.add_widget(self.scroll)

        actions=BoxLayout(size_hint_y=None,height=dp(40),spacing=dp(5))
        self.target=TextInput(hint_text='角色 ID',multiline=False,
                              input_filter='int',input_type='number',
                              size_hint_x=.35,font_size='12sp')
        style_input(self.target)
        actions.add_widget(self.target)
        actions.add_widget(SocialButton('邀請',lambda:self.act('invite'),
                                        icon='invite',height=40))
        actions.add_widget(SocialButton('申請',lambda:self.act('apply'),
                                        icon='users',height=40))
        board.add_widget(actions)
        bottom=BoxLayout(size_hint_y=None,height=dp(42),spacing=dp(5))
        bottom.add_widget(SocialButton('選擇附近玩家',self.choose_nearby,
                                       icon='pin',height=42))
        bottom.add_widget(SocialButton('必要成員',self.guard,
                                       icon='shield',height=42))
        bottom.add_widget(SocialButton('邀請開關',self.flag,
                                       icon='settings',height=42))
        board.add_widget(bottom)
        # The original team command guard still runs on every manual action.
        self._render_compact()

    def _select_party_tab(self,name):
        self.party_tab=name
        self.page_index=0
        self._render_compact()

    def _refresh_compact(self):
        p=self.state.get('party',{})
        key=(str(p),str(self.state.get('player',{})),self.d.live,
             self.party_tab,self.page_index)
        if self.key==key:return
        self.key=key
        status=p.get('status','等待同步')
        self.info.text=str(status)[:100]
        self._render_compact()

    def _render_compact(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from android_app.theme import style_button, ACCENT, TEXT, MUTED
        from android_app.pages.social_visual import (
            SocialButton, NearbyTile, caption)
        p=self.state.get('party',{})
        player=self.state.get('player',{})
        team=own_team(self.state)
        nearby=[
            item for item in p.get('nearby',{}).values()
            if type(item) is dict and player.get('scene') is not None
            and item.get('scene') == player.get('scene')
            and type(item.get('role_id')) is int
            and item.get('role_id') != player.get('role_id')
        ]
        requests=[
            (key,item) for key,item in p.get('requests',{}).items()
            if type(item) is dict and item.get('status')=='pending'
        ]
        labels={'附近玩家':len(nearby),'組隊申請':len(requests),
                '我的隊伍':len(team['members']) if team else 0}
        for name,btn in self.party_tabs.items():
            style_button(btn,primary=name==self.party_tab,radius=12)
            btn.font_size='11sp'
            btn.text=f'{name}（{labels[name]}）'
        self.entries.clear_widgets()
        if self.party_tab=='附近玩家':
            if not nearby:
                self.entries.add_widget(caption(
                    '尚無同場景已同步玩家；可稍後重新整理',
                    height=42))
            for item in nearby[:32]:
                rid=item['role_id']
                self.entries.add_widget(NearbyTile(
                    str(item.get('name') or rid)[:35],rid,
                    '角色 ID：'+str(rid),
                    lambda target=rid:self.act('invite',target),
                    lambda target=rid:self.act('apply',target)))
            self.nearby_preview.text='同場景 {} 名'.format(len(nearby))
        elif self.party_tab=='組隊申請':
            if not requests:
                self.entries.add_widget(caption('目前沒有待回覆的組隊申請',height=42))
            for key,request in requests[:25]:
                item=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(5))
                title=caption(
                    '角色 '+player_name(self.state,request.get('role_id'))+
                    '：'+{'team_invite':'邀請入隊',
                         'team_application':'申請入隊',
                         'team_leader_offer':'隊長交接'}.get(
                             request.get('type'),'組隊請求'),
                    height=42)
                item.add_widget(title)
                accept=SocialButton('接受',lambda k=key:self.d.send(
                    dict(type='team',action='respond',request=k,answer=1)),
                    icon='check',height=42)
                refuse=SocialButton('拒絕',lambda k=key:self.d.send(
                    dict(type='team',action='respond',request=k,answer=2)),
                    icon='close',height=42)
                item.add_widget(accept);item.add_widget(refuse)
                self.entries.add_widget(item)
        else:
            if not team:
                self.entries.add_widget(caption('目前尚未加入已確認的隊伍',height=42))
            else:
                for rid in team.get('members',[])[:4]:
                    box=BoxLayout(size_hint_y=None,height=dp(43),spacing=dp(5))
                    box.add_widget(caption(
                        player_name(self.state,rid)+
                        ('（隊長）' if rid==team['leader_id'] else ''),
                        color=TEXT,height=42))
                    if (team['leader_id']==player.get('role_id')
                            and rid!=team['leader_id']):
                        box.add_widget(SocialButton(
                            '移除',lambda target=rid:self.act('kick',target),
                            icon='close',height=42))
                        box.add_widget(SocialButton(
                            '交接',lambda target=rid:self.act('leader',target),
                            icon='crown',height=42))
                    self.entries.add_widget(box)
                self.entries.add_widget(SocialButton(
                    '離隊／解散',lambda:self.d.send(
                        {'type':'team','action':'leave'},
                        '確認離開隊伍？隊長離隊會解散隊伍。'),
                    icon='users',height=38))
        self.scroll.scroll_y=1

    def act(self, action, rid=None):
        try: rid = int(rid if rid is not None else self.target.text)
        except ValueError: self.d.message.text = '請選擇玩家或輸入有效角色 ID'; return
        command = dict(type='team', action=action, role_id=rid)
        self.d.send(command, f"確認對 {player_name(self.state, rid)} 執行"+
                    ('移除隊員？' if action == 'kick' else '轉交隊長？')) if action in ('kick', 'leader') else self.d.send(command)
    def choose_nearby(self):
        scene = self.state.get('player', {}).get('scene')
        pick('附近玩家', [(v['role_id'], f"{v['name']}（{v['role_id']}）") for v in
            self.state.get('party', {}).get('nearby', {}).values() if v.get('scene') == scene],
            lambda rid: setattr(self.target, 'text', str(rid)))
    def flag(self):
        p = self.state.get('party', {})
        self.d.send(dict(type='team', action='flag', enabled=not p.get('enabled_requested', p.get('enabled'))))
    def guard(self):
        if 'ai_settings' not in self.d.data:
            self.d.message.text = '等待本帳號設定同步，請稍候再試'
            return
        from android_app.settings_ui import SettingsEditor
        SettingsEditor(self.d.app, self.d.sid, initial='必要成員')
    def refresh(self):
        if getattr(self, 'compact', False):
            return self._refresh_compact()
        p = self.state.get('party', {}); team = own_team(self.state)
        key = (str(p), self.d.live)
        if self.key == key: return
        self.key = key
        self.info.text = p.get('status', '等待同步')+'\n'+('隊長：'+player_name(self.state, team['leader_id']) if team else '目前未組隊')
        nearby = [
            v.get('name', '未知角色')
            for v in p.get('nearby', {}).values()
            if v.get('scene') == self.state.get('player', {}).get('scene')
        ]
        self.nearby_preview.text = (
            '同場景 {} 名：{}'.format(len(nearby),
                                 '、'.join(str(name) for name in nearby[:4]))
            if nearby else '尚無已確認的附近玩家')
        self.members.clear_widgets(); self.requests.clear_widgets()
        if team:
            for rid in team['members']:
                self.members.add_widget(label(player_name(self.state, rid)+f'（{rid}）'+(' · 隊長' if rid == team['leader_id'] else '')))
                if team['leader_id'] == self.state.get('player', {}).get('role_id') and rid != team['leader_id']:
                    self.members.add_widget(row(button('移除', lambda r=rid: self.act('kick', r)),
                                                button('交接隊長', lambda r=rid: self.act('leader', r))))
        for key, request in p.get('requests', {}).items():
            self.requests.add_widget(label({'team_invite': '組隊邀請', 'team_application': '入隊申請', 'team_leader_offer': '隊長交接'}.get(request['type'], '請求')+
                '：'+player_name(self.state, request['role_id'])+' · '+request['status']))
            if request['status'] == 'pending':
                self.requests.add_widget(row(button('接受', lambda k=key: self.d.send(dict(type='team', action='respond', request=k, answer=1))),
                    button('拒絕', lambda k=key: self.d.send(dict(type='team', action='respond', request=k, answer=2)))))


class Chat(Page):
    def __init__(self, d):
        if getattr(d, 'page_name', '') == '聊天訊息':
            Page.__init__(self, d, embedded=True, show_title=False)
            self.compact=True
            self.offset=0
            self.quote=None
            self.pending=False
            self.sent_text=None
            self._build_compact()
            return
        super().__init__(d)
        self.compact=False
        from android_app.pages.ui_components import feature_card, status_line
        self.offset=0
        self.quote=None
        self.pending=False
        self.sent_text=None
        conversation=feature_card(
            '聊天訊息', '從目前角色同步，點擊訊息可引用或密語')
        self.filter=select(conversation, '顯示頻道',
                           ['全部',*CHANNELS,'跨服','系統'])
        self.filter.bind(text=lambda *_:self.render())
        self.messages=column()
        conversation.add_widget(self.messages)
        conversation.add_widget(row(
            button('較早訊息',lambda:self.move(-1)),
            button('最新訊息',lambda:self.move(999))))
        self.add_widget(conversation)
        compose=feature_card('發送訊息', '伺服器接受訊息不代表對方已讀')
        self.channel=select(compose,'發送頻道',list(CHANNELS))
        self.target=field(compose,'密語名稱／角色 ID')
        self.quote_label=status_line('未引用訊息')
        compose.add_widget(self.quote_label)
        compose.add_widget(button('取消引用',self.cancel_quote))
        self.text=field(compose,'聊天內容')
        self.send_button=button('送出',self.send,52)
        compose.add_widget(row(button('表情',self.emojis),self.send_button))
        self.delivery_status=status_line('等待輸入訊息')
        compose.add_widget(self.delivery_status)
        self.add_widget(compose)
        self.channel.bind(
            text=lambda *_:self.cancel_quote()
            if self.quote and self.quote['channel']!=self.channel.text else None)

    def _build_compact(self):
        """Actual messages, selector, reply bar and verified game emoji."""
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.spinner import Spinner
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput
        from android_app.theme import (
            ACCENT, MUTED, TEXT, SOFT, style_button, style_input, neon_surface)
        from android_app.widgets import RoundedSpinnerOption
        from android_app.pages.social_visual import (
            SocialIcon, SocialButton, caption, heading, glass_card)

        panel=glass_card(bright=True,padding=7,gap=5)
        self.add_widget(panel)
        controls=BoxLayout(size_hint_y=None,height=dp(41),
                           spacing=dp(5))
        controls.add_widget(heading('頻道',icon='layers'))
        self.filter=Spinner(text='全部',values=['全部',*CHANNELS,'跨服','系統'],
                            option_cls=RoundedSpinnerOption,
                            size_hint_x=.54,font_size='12sp')
        style_button(self.filter,radius=11)
        controls.add_widget(self.filter)
        self.online=caption('連線狀態待同步',color=MUTED,
                            height=40,size='10sp')
        self.online.size_hint_x=.44
        controls.add_widget(self.online)
        panel.add_widget(controls)

        announcement=BoxLayout(size_hint_y=None,height=dp(29),
                               padding=[dp(5),dp(1)],
                               spacing=dp(5))
        neon_surface(announcement,color=SOFT,radius=11)
        announcement.add_widget(SocialIcon('megaphone',edge=19))
        self.announcement=caption(
            '聊天紀錄取自目前角色，無最新系統公告',
            size='10sp',height=26)
        announcement.add_widget(self.announcement)
        panel.add_widget(announcement)
        self.message_scroll=ScrollView(do_scroll_x=False,
                            bar_width=dp(3),size_hint_y=None,
                            height=dp(226))
        self.messages=BoxLayout(orientation='vertical',
                               size_hint_y=None,spacing=dp(5),
                               padding=[dp(4),dp(3),dp(4),dp(4)])
        self.messages.bind(minimum_height=self.messages.setter('height'))
        self.message_scroll.add_widget(self.messages)
        panel.add_widget(self.message_scroll)

        reactions=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(5))
        neon_surface(reactions,color=SOFT,radius=13)
        # Use actual, included game emote assets. Missing ZIP / JPEG support
        # falls back to an operable picker, never a Unicode tofu symbol.
        try:
            from android_app.assets import emoji_entries, emoji_texture
            from kivy.uix.image import Image
            keys=[
                int(key) for key,row in emoji_entries().items()
                if str(key).isdigit() and isinstance(row,dict)
                and row.get('available',True)
            ][:7]
            for key in keys:
                action=SocialButton('',lambda idx=key:self._insert_emoji(idx),
                                    icon='smile',height=34,font='10sp')
                try:
                    sprite=emoji_texture(key)
                    if sprite is not None:
                        img=Image(texture=sprite,size_hint=(None,None),
                                  size=(dp(26),dp(26)))
                        action.add_widget(img)
                        action.bind(pos=lambda w,*_,icon=img:
                                    setattr(icon,'center',w.center))
                        img.center=action.center
                        action.glyph.opacity=0
                except (OSError,KeyError,ValueError):
                    pass
                reactions.add_widget(action)
        except (OSError,KeyError,ValueError,ImportError,TypeError):
            pass
        reactions.add_widget(SocialButton(
            '更多',self.emojis,icon='smile',height=34,font='10sp'))
        panel.add_widget(reactions)

        send_header=BoxLayout(size_hint_y=None,height=dp(37),
                              spacing=dp(5))
        send_header.add_widget(caption('頻道',height=37,size='11sp'))
        self.channel=Spinner(text='區域',values=list(CHANNELS),
                             size_hint_x=.48,option_cls=RoundedSpinnerOption,
                             font_size='12sp')
        style_button(self.channel,radius=11)
        send_header.add_widget(self.channel)
        self.target=TextInput(hint_text='密語角色 ID',
                              multiline=False,input_filter='int',
                              input_type='number',size_hint_x=.38,
                              font_size='12sp')
        style_input(self.target)
        send_header.add_widget(self.target)
        panel.add_widget(send_header)

        compose=BoxLayout(size_hint_y=None,height=dp(46),spacing=dp(6))
        self.text=TextInput(hint_text='輸入訊息…',
                            multiline=False,input_type='text',
                            font_size='13sp')
        style_input(self.text)
        compose.add_widget(self.text)
        self.send_button=SocialButton('送出',self.send,icon='send',
                                     primary=True,height=46,
                                     font='13sp')
        self.send_button.size_hint_x=None
        self.send_button.width=dp(85)
        compose.add_widget(self.send_button)
        panel.add_widget(compose)

        actions=BoxLayout(size_hint_y=None,height=dp(26),
                          spacing=dp(6))
        self.quote_label=caption('未引用訊息',size='10sp',
                                 height=26)
        actions.add_widget(self.quote_label)
        actions.add_widget(SocialButton('取消引用',
                                        self.cancel_quote,icon='close',
                                        height=26,font='10sp'))
        panel.add_widget(actions)
        self.delivery_status=caption('等待輸入訊息',
                                    height=21,size='10sp')
        panel.add_widget(self.delivery_status)

        pager=BoxLayout(size_hint_y=None,height=dp(30),spacing=dp(4))
        pager.add_widget(SocialButton('較早',
                                      lambda:self.move(-1),
                                      icon='list',height=30))
        pager.add_widget(SocialButton('最新',
                                      lambda:self.move(999),
                                      icon='refresh',height=30))
        panel.add_widget(pager)
        self.filter.bind(text=lambda *_:self.render())
        self.channel.bind(text=lambda *_:self._change_compact_channel())
        self._change_compact_channel()
        self.render()

    def _change_compact_channel(self):
        # Whisper recipient is a genuine role ID; no fake @ mention target.
        whisper=self.channel.text=='密語'
        self.target.disabled=not whisper
        self.target.opacity=1 if whisper else .38
        if self.quote and self.quote['channel']!=self.channel.text:
            self.cancel_quote()

    def _insert_emoji(self, index):
        # Catalog ID was obtained from bundled verified game emoji entries.
        self.text.text+=f'[Emoji{index}]'

    def _render_compact(self):
        from kivy.metrics import dp
        from android_app.pages.social_visual import MessageTile, caption
        rows=self.d.data.get('chat',[])
        if not isinstance(rows,list):
            rows=[]
        filtered=[
            item for item in rows if isinstance(item,dict)
            and (self.filter.text=='全部'
                 or item.get('channel')==self.filter.text)
        ]
        pages=max(1,(len(filtered)+19)//20)
        self.offset=min(max(0,self.offset),pages-1)
        self.messages.clear_widgets()
        if not filtered:
            self.messages.add_widget(caption(
                '尚無從目前角色同步的聊天訊息',
                height=dp(56),size='12sp'))
        pid=self.state.get('player',{}).get('role_id')
        for record in filtered[self.offset*20:self.offset*20+20]:
            sender=record.get('name') or str(record.get('role_id','未知角色'))
            own=pid is not None and record.get('role_id')==pid
            reply=record.get('reply_text')
            # The official chat parser does not verify a clock field.
            self.messages.add_widget(MessageTile(
                str(sender)[:45],str(record.get('channel','未知頻道'))[:12],
                plain_text(record.get('text',''))[:500],
                own=own,
                reply=plain_text(reply)[:120] if type(reply) is str else None,
                callback=lambda m=record:self.actions(m)))
        self.messages.add_widget(caption(
            f'{self.offset+1}/{pages} 頁 · 保留最近 200 則',
            height=dp(25),size='10sp'))
        announcements=[
            item for item in rows[-200:]
            if isinstance(item,dict) and item.get('channel')=='系統'
        ]
        if announcements:
            self.announcement.text=(
                '【系統】'+plain_text(announcements[-1].get('text',''))[:160])
        else:
            self.announcement.text='聊天紀錄來自目前角色；尚無已同步系統公告'
        self.online.text='角色已連線' if self.d.live else '等待角色連線'
        self.message_scroll.scroll_y=0

    def cancel_quote(self): self.quote = None; self.quote_label.text = '未引用訊息'
    def emojis(self):
        from android_app.assets import emoji_entries, emoji_texture
        from kivy.uix.image import Image
        from kivy.metrics import dp
        entries = [(int(i), '[Emoji'+i+']') for i, data in emoji_entries().items() if data.get('available', True)]
        def icon(index):
            value = emoji_texture(index)
            return Image(texture=value, size_hint=(None, None), size=(dp(40),dp(40))) if value else None
        pick('選擇表情', entries, lambda i: setattr(self.text, 'text', self.text.text + f'[Emoji{i}]'), icon=icon)
    def send(self):
        if self.pending: return
        import uuid
        self.request_id = uuid.uuid4().hex
        command = dict(type='chat', request_id=self.request_id, channel=self.channel.text, target=self.target.text, text=self.text.text)
        if self.quote: command['reply'] = copy.deepcopy(self.quote)
        if self.d.send(command):
            self.d.message.text = '聊天已排入佇列；請以伺服器轉送／回覆為準'
            self.delivery_status.text = '發送中，等待伺服器回覆'
            import time
            self.pending = True
            self.pending_started = time.monotonic()
            self.send_button.disabled = True
            self.sent_text = self.text.text
            self.sent_quote = copy.deepcopy(self.quote)
    def ack(self, value):
        if not self.pending or value.get('request_id') != getattr(self, 'request_id', None): return
        self.pending = False
        self.send_button.disabled = False
        status = value.get('status')
        self.delivery_status.text = {'sent': '伺服器已接受，不代表對方已讀',
            'uncertain': '發話結果未知，請勿直接重送'}.get(status, '訊息未能送出')
        if status == 'sent':
            # Server accepted the chat packet; no claim that others read it.
            if self.text.text == value.get('text') == self.sent_text: self.text.text = ''
            if self.quote == getattr(self, 'sent_quote', None): self.cancel_quote()
            self.d.message.text = '伺服器已回覆發話成功；不代表對方已讀'
        elif status == 'uncertain':
            self.d.message.text = '背景服務回覆中斷，發話結果未知；原文字已保留，請先確認再重送'
        else:
            self.d.message.text = '伺服器拒絕或未能送出聊天訊息；原文字已保留'

    def move(self, delta):
        self.offset = max(0, self.offset+delta); self.render()
    def actions(self, message):
        body = column()
        body.add_widget(label(plain_text(message.get('text', ''))))
        popup = None
        def whisper():
            if message.get('channel') == '跨服': self.d.message.text = '跨服訊息不能當作本服密語對象'; return
            pid = self.state.get('player', {}).get('role_id')
            rid = message.get('role_id')
            target = message.get('target_id') if rid == pid else rid
            self.channel.text = '密語'; self.target.text = str(target or ''); popup.dismiss()
        def quote():
            channel = message.get('channel')
            if channel not in CHANNELS or not message.get('role_id'):
                self.d.message.text = '此頻道不支援引用回覆'; return
            self.channel.text = channel
            pid = self.state.get('player', {}).get('role_id')
            target = message.get('target_id') if message['role_id'] == pid else message['role_id']
            if channel == '密語': self.target.text = str(target)
            self.quote = dict(role_id=message['role_id'], text=message['text'], channel=channel,
                items=[v['item_id'] if isinstance(v, dict) else v for v in message.get('items', [])],
                has_at=bool(message.get('reply_id')), whisper_target=target)
            self.quote_label.text = '引用：'+plain_text(message['text'])
            prefix = '@'+message.get('name', str(message['role_id']))+' '
            if not self.text.text.startswith(prefix): self.text.text = prefix+self.text.text
            popup.dismiss()
        body.add_widget(row(button('密語回覆', whisper), button('引用回覆', quote)))
        def copy_message():
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(plain_text(message.get('text',''))); popup.dismiss()
        body.add_widget(button('複製訊息', copy_message))
        from android_app.widgets import dialog
        popup = dialog('訊息操作', body, .6)
    def render(self):
        if getattr(self, 'compact', False):
            return self._render_compact()
        rows = [r for r in self.d.data.get('chat', []) if self.filter.text == '全部' or r.get('channel') == self.filter.text]
        pages = max(1, (len(rows)+19)//20); self.offset = min(self.offset, pages-1)
        self.messages.clear_widgets()
        for message in rows[self.offset*20:self.offset*20+20]:
            text = '['+message.get('channel', '?')+'] '+message.get('name', str(message.get('role_id', '')))+'：'+plain_text(message.get('text', ''))
            if message.get('reply_text'): text += '\n↳ '+plain_text(message['reply_text'])
            from android_app.pages.ui_components import message_button
            player_id=self.state.get('player', {}).get('role_id')
            own=(player_id is not None and message.get('role_id') == player_id)
            self.messages.add_widget(message_button(
                text, lambda m=message: self.actions(m), own=own))
            import re
            from android_app.assets import emoji_texture
            from kivy.uix.image import Image
            from kivy.metrics import dp
            tokens = re.findall(r'\[Emoji([0-9]+)\]', message.get('text', ''))[:8]
            images = []
            for index in tokens:
                value = emoji_texture(index)
                if value: images.append(Image(texture=value, size_hint=(None,None), size=(dp(32),dp(32))))
            if images: self.messages.add_widget(row(*images))
        self.messages.add_widget(label(f'{self.offset+1}/{pages} 頁 · 保留最近 200 則'))
    def refresh(self):
        if self.pending:
            import time
            if not self.d.live:
                self.pending = False
                self.send_button.disabled = False
                self.d.message.text = '遊戲連線中斷；聊天狀態未確認，原文字已保留'
                self.delivery_status.text = '斷線，發話狀態未確認'
            elif time.monotonic() - getattr(self, 'pending_started', time.monotonic()) >= 20:
                self.pending = False
                self.send_button.disabled = False
                self.d.message.text = '等待伺服器發話結果逾時；原文字已保留，重送前請先檢查聊天紀錄'
                self.delivery_status.text = '逾時未確認，請先檢查聊天紀錄'
        key = (str(self.d.data.get('chat')), self.filter.text)
        if key != self.key:
            was_latest = self.offset >= max(0, ((len(getattr(self, '_previous', []))+19)//20)-1)
            self._previous = self.d.data.get('chat', [])
            if was_latest: self.offset = 999
            self.key = key; self.render()
