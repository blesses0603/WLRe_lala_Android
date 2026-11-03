from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Ellipse, Line
from kivy.uix.widget import Widget
from android_app.pages.general import Page
from android_app.widgets import label, button, row, field, pick
from android_app.assets import texture
from wlre.services.world.smallmaps import SmallMaps
from wlre.services.world.portals import Portals
from wlre.services.world.portal_policy import allowed_rows
from wlre.services.world.map_names import parse_map_id
from wlre.services.world.scene_names_1275 import source_scene_label

def map_label(scene):
    from wlre.services.world.dynamic_bundle_runtime import current_runtime
    runtime=current_runtime()
    return source_scene_label(scene, getattr(runtime, 'scene_names', {}))
from wlre.services.world.display_position import current_position


class MapCanvas(Widget):
    def __init__(self, on_pick, **kwargs):
        super().__init__(size_hint_y=None,height=dp(320),**kwargs)
        self.texture=None;self.projection=None;self.player=None;self.selected=None;self.portals=[];self.on_pick=on_pick
        self._draw_signature=None
        self.bind(pos=lambda *_:self.draw(),size=lambda *_:self.draw())
    def box(self):
        side=min(self.width,self.height)
        return self.x+(self.width-side)/2,self.y+(self.height-side)/2,side
    def screen(self,u,v):
        x,y,size=self.box();return x+u/1024*size,y+(1024-v)/1024*size
    def draw(self):
        # Bitmap texture, scene and markers can be stable while Kivy polls.
        # Skip expensive canvas clear/rebuild until something actually moves.
        marks=lambda point: tuple((point or {}).get(key) for key in ('x','y'))
        signature=(
            tuple(self.pos),tuple(self.size),id(self.texture),
            id(self.projection),marks(self.player),marks(self.selected),
            tuple((p.get('x'),p.get('y'),p.get('coordinate_valid'))
                  for p in self.portals),
        )
        if signature==self._draw_signature:
            return
        self._draw_signature=signature
        self.canvas.clear()
        x,y,size=self.box()
        with self.canvas:
            Color(.08,.15,.2,1);Rectangle(pos=self.pos,size=self.size)
            if not self.texture:return
            Color(1,1,1,1);Rectangle(texture=self.texture,pos=(x,y),size=(size,size))
            if self.projection:
                for portal in self.portals:
                    if portal.get('coordinate_valid'):
                        u,v=self.screen(*self.projection.packet_to_pixel(portal['x'],portal['y']))
                        Color(.2,1,1,1);Line(circle=(u,v,dp(4)),width=1.2)
                for point,color in ((self.player,(1,.2,.2,1)),(self.selected,(1,.85,.2,1))):
                    if point:
                        u,v=self.screen(*self.projection.packet_to_pixel(point['x'],point['y']))
                        Color(*color);Ellipse(pos=(u-dp(4),v-dp(4)),size=(dp(8),dp(8)))
    def on_touch_down(self,touch):
        x,y,size=self.box()
        if self.texture and self.projection and x<=touch.x<=x+size and y<=touch.y<=y+size:
            u=(touch.x-x)/size*1024;v=1024-(touch.y-y)/size*1024
            px,py=self.projection.pixel_to_packet(u,v)
            self.on_pick(round(px),round(py));return True
        return super().on_touch_down(touch)


class MapPage(Page):
    def __init__(self,d):
        super().__init__(d)
        from android_app.pages.ui_components import feature_card, status_line
        self.maps=SmallMaps()
        self.portals=Portals()
        self.scene=None
        self.token=None

        map_card=feature_card(
            '小地圖與即時位置',
            '紅點代表角色、黃點代表目的地、青色圓圈代表出口')
        self.title=status_line('等待角色位置')
        map_card.add_widget(self.title)
        self.position_label=status_line('座標：尚未同步')
        map_card.add_widget(self.position_label)
        self.image=MapCanvas(self.picked)
        map_card.add_widget(self.image)
        self.note=status_line('輕觸地圖可選取目標座標')
        map_card.add_widget(self.note)
        self.add_widget(map_card)

        destination=feature_card(
            '目標座標與移動',
            '座標需由地圖確認或手動輸入；指令由伺服器確認')
        self.x_input=field(destination,'目的地 X',numeric=True)
        self.y_input=field(destination,'目的地 Y',numeric=True)
        destination.add_widget(row(
            button('步行前往',self.walk),
            button('停止移動',lambda:d.send({'type':'stop_walk'}))))
        self.add_widget(destination)

        portals=feature_card('NPC／出口與地圖工具',
                             '出口須先選取；未知路線不會自動嘗試')
        portals.add_widget(row(
            button('NPC／出口',lambda:self.entities(False)),
            button('怪物',lambda:self.entities(True))))
        self.portal=None
        portals.add_widget(button('前往所選出口',self.portal_walk))
        portals.add_widget(button('直接嘗試所選出口換圖',self.direct))
        portals.add_widget(button('逐圖核對',self.audit))
        self.add_widget(portals)
    def picked(self,x,y):
        self.x_input.text=str(x);self.y_input.text=str(y);self.image.selected={'x':x,'y':y};self.image.draw()
    def walk(self):
        try:self.d.send(dict(type='walk',scene=self.scene,x=int(self.x_input.text),y=int(self.y_input.text)))
        except ValueError:self.d.message.text='請選取地圖座標或輸入有效 X、Y'
    def portal_walk(self):
        if self.portal:self.d.send(dict(type='portal_walk',portal_id=self.portal['id']))
        else:self.d.message.text='請先選擇出口'
    def direct(self):
        if not self.portal:self.d.message.text='請先選擇出口';return
        self.d.send(dict(type='portal_direct',portal_id=self.portal['id']), '確認嘗試換圖至 '+self.portal.get('name','所選出口')+'？')
    def entities(self,monsters):
        scene=self.scene;rows=[]
        if not monsters:
            rows += [(('portal',p),p['name']+(' · 可直接換圖' if p.get('direct_eligible') else ' · 僅檢視')) for p in self.image.portals]
        rows += [(('entity',p),('Lv.'+str(p.get('level','?'))+' ' if monsters else '')+p['name'])
                 for p in self.portals.data.get('entities',{}).get(str(scene),[]) if bool(p['kind'])==monsters]
        def choose(value):
            kind,p=value
            if scene!=self.scene:self.d.message.text='目前地圖已變更，請重新選擇';return
            self.portal=p if kind=='portal' else None
            self.note.text=p['name']+' · '+p.get('direct_note',p.get('navigation_note','已選取，尚未送出操作'))
            if p.get('coordinate_valid') or kind=='entity' and 'x' in p and 'y' in p:
                self.picked(round(p['x']),round(p['y']))
        pick('怪物' if monsters else 'NPC／出口',rows,choose)
    def audit(self):
        rows=[]
        from wlre.services.world.catalog_source_policy import official_runtime
        for scene,data in sorted(official_runtime('maps').stages.items(),key=lambda p:int(p[0])):
            has=self.maps.has_image(int(scene));portals=self.portals.for_scene(int(scene))
            rows.append((int(scene),map_label(int(scene))+(' · 有原圖' if has else ' · 無原圖')+f' · 出口 {len(portals)}'))
        pick('逐圖核對（只讀；目前地圖持續自動跟隨）',rows,lambda scene:setattr(self.note,'text',map_label(scene)+' · 原圖 '+('有' if self.maps.has_image(scene) else '無')))
    def refresh(self):
        scene=self.state.get('player',{}).get('scene')
        self.title.text='小地圖｜'+(map_label(scene) if scene is not None else '等待角色位置')
        from wlre.services.world.dynamic_bundle_runtime import current_catalog_token
        token=current_catalog_token()
        if scene!=self.scene or token!=self.token:
            self.token=token;self.maps=SmallMaps();self.portals=Portals()
            self.scene=scene;self.portal=None;self.image.selected=None;self.x_input.text=self.y_input.text=''
            self.image.texture=None;self.image.projection=None
            if scene is not None:
                try:
                    projection,model=self.maps.projection(scene)
                    entry=self.maps.entries.get(parse_map_id(model))
                    if entry:self.image.texture=texture('smallmaps.zip',entry);self.image.projection=projection
                except (ValueError,KeyError,OSError):pass
            self.image.portals=allowed_rows(self.portals,scene,self.maps,recovery=self.image.texture is None)
            if not self.image.texture:self.note.text='此圖沒有可顯示的原始小地圖；可從 NPC／出口選擇已確認的返回出口。'
        point=current_position(self.state)
        self.image.player=point if point and point.get('scene')==scene else None
        if self.image.player:
            self.position_label.text='目前座標：({}, {})'.format(
                self.image.player.get('x', '—'),
                self.image.player.get('y', '—'))
        else:
            self.position_label.text='目前座標：等待伺服器同步'
        self.image.draw()

