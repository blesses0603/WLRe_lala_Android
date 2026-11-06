"""Official database preview; this popup never invokes dashboard.send."""
from kivy.clock import Clock
from android_app.widgets import column,label,field,select,check,button,dialog
from wlre.services.world.navigation_preview_job import PreviewJob


def open_navigation_preview(dashboard):
    job=PreviewJob();body=column();body.add_widget(label('官方資料庫導航預覽，不會移動角色。'))
    player=dashboard.state.get('player',{})
    fields=[field(body,name,value) for name,value in (
        ('地圖 ID',player.get('scene',10000)),('起點 X',player.get('x',0)),('起點 Y',player.get('y',0)),
        ('終點 X',player.get('x',0)),('終點 Y',player.get('y',0)))]
    mode=select(body,'通行模式',('步行','海上','飛行'),'步行')
    smooth=check(body,'平面走廊平滑（斜坡會拒絕）',False)
    status=label('同步每個模型最多 2 個檔案／32 MiB。');output=label('');validation=[None]
    def run(download):
        try:
            validation[0]=None;values=[f.text for f in fields]
            job.start(dashboard.state,values[0],values[1:3],values[3:5],
                      travel_mode={'步行':'land','海上':'sea','飛行':'sky'}[mode.text],smooth=smooth.active,download=download)
        except (ValueError,KeyError) as error:validation[0]=str(error);status.text=validation[0]
    body.add_widget(button('從資料庫預覽',lambda:run(False)))
    body.add_widget(button('同步此地圖並預覽',lambda:run(True)))
    body.add_widget(status);body.add_widget(output)
    popup=dialog('官方導航預覽',body)
    def poll(_):
        value=({'status':'error','message':validation[0]} if validation[0] else job.poll(dashboard.state))
        status.text=value['message'];result=value.get('result')
        output.text=('地圖：'+str(result['logical_map'])+'\n來源：'+result.get('source_label','官方已校驗資料庫')+'\n'+
                     '\n'.join(f'{x:.2f}, {y:.2f}' for x,y in result['packet_points_xy_float'][:256])) if result else ''
    event=Clock.schedule_interval(poll,.25)
    popup.bind(on_dismiss=lambda *_:(event.cancel(),job.close()))
    return popup
