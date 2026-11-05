"""Offline preview of the actual Android gate widget, never the desktop login.

All preview state is visibly labelled and lives in tools/, which APK staging
excludes. No server, account, IPC or Android service is started.
"""
import argparse
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width',type=int,default=393)
    parser.add_argument('--height',type=int,default=852)
    parser.add_argument('--state',choices=('pending','checking','passed','blocked'),default='checking')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--font-scale',type=float,default=1.0)
    parser.add_argument('--animation-output',type=Path,help='Record 18 actual Kivy frames to a labelled preview GIF.')
    args=parser.parse_args()
    os.environ.setdefault('KIVY_NO_ARGS','1')
    os.environ['KIVY_DPI']='96'; os.environ['KIVY_METRICS_DENSITY']='1'
    os.environ['KIVY_METRICS_FONTSCALE']=str(args.font_scale)
    from kivy.config import Config
    Config.set('graphics','width',str(args.width)); Config.set('graphics','height',str(args.height))
    Config.set('graphics','resizable','0')
    from kivy.core.text import LabelBase, DEFAULT_FONT
    font=ROOT/'android_app/assets/fonts/NotoSansTC-Regular.ttf'
    if not font.is_file():font=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if not font.is_file():parser.error('Restore the bundled Chinese font for preview.')
    LabelBase.register(DEFAULT_FONT,fn_regular=str(font),fn_bold=str(font))
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.core.window import Window
    from android_app.verification_ui import VerificationDashboard
    Window.clearcolor=(.014,.035,.073,1)
    token=[True,'a'*64]
    class Preview(App):
        def build(self):
            root=BoxLayout(orientation='vertical')
            self.notice=Label(text='UI 預覽 · 示意狀態 · 未連接正式服務',font_size='10sp',color=(.99,.80,.39,1),size_hint_y=None,height=22)
            root.add_widget(self.notice)
            self.panel=VerificationDashboard(lambda:self.apply('checking'),lambda:self.apply('pending'),lambda:setattr(self.notice,'text','UI 預覽 · 不會開啟真實登入或連線'))
            root.add_widget(self.panel); self.apply(args.state)
            if args.output or args.animation_output:
                if args.output:args.output.parent.mkdir(parents=True,exist_ok=True)
                Clock.schedule_once(self.capture,3)
            return root
        def apply(self,kind):
            service={}; local={}; connected=kind!='pending'
            detail='等待背景服務建立連線，完成後會開始核對官方資源。'
            if kind=='checking':
                service={'status':'checking','ready':False}; detail='正在核對官方來源。檢查期間不會開啟帳號登入。'
            elif kind=='passed':
                service={'status':'ready','ready':True,'catalog_token':token}; local={'status':'ready','ready':True,'catalog_token':token}
                detail='預覽完成狀態。正式版仍須雙端驗證同一份資料來源。'
            elif kind=='blocked':
                service={'status':'blocked','ready':False,'failure_code':'manifest_validation_failed'}
                detail='示意：Manifest 核對未通過。請重新檢查，不能跳過驗證。'
            self.panel.apply_state(service,local,connected=connected,detail=detail,login_ready=kind=='passed')
        def capture(self,*_):
            if args.output:self.root.export_to_png(str(args.output))
            print('PREVIEW',args.output,'STATE',args.state,'CONTENT_HEIGHT',self.panel.content_root.height,'VIEWPORT',self.panel.viewport.height,'ACTIONS',self.panel.actions.height,flush=True)
            if args.animation_output:
                import tempfile
                self._frames=tempfile.TemporaryDirectory(prefix='kivy-verification-')
                self._frame_paths=[]
                self.capture_frame()
            else:self.stop()
        def capture_frame(self,*_):
            path=Path(self._frames.name)/f'{len(self._frame_paths):02d}.png'
            self.root.export_to_png(str(path));self._frame_paths.append(path)
            if len(self._frame_paths)<18:
                Clock.schedule_once(self.capture_frame,.1)
                return
            from PIL import Image
            frames=[]
            for path in self._frame_paths:
                with Image.open(path) as frame:frames.append(frame.convert('RGB'))
            args.animation_output.parent.mkdir(parents=True,exist_ok=True)
            frames[0].save(args.animation_output,save_all=True,append_images=frames[1:],duration=100,loop=0)
            for frame in frames:frame.close()
            self._frames.cleanup()
            print('ANIMATION',args.animation_output,'actual Kivy frames',len(self._frame_paths),flush=True)
            self.stop()
    Preview().run()
if __name__=='__main__':main()
