from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch


class AndroidPreviewUITests(unittest.TestCase):
    def test_popup_only_submits_preview_and_cancels_on_close(self):
        from android_app.navigation_preview_ui import open_navigation_preview
        d=SimpleNamespace(state={'player':{'scene':10000,'x':1,'y':2}},send=Mock())
        job=Mock();job.poll.return_value={'status':'ready','message':'preview only','result':dict(logical_map=10000,catalog_key='a'*64,packet_points_xy_float=[[1,2]])}
        clock=Mock()
        with patch('android_app.navigation_preview_ui.PreviewJob',return_value=job),patch('android_app.navigation_preview_ui.Clock',clock):
            popup=open_navigation_preview(d)
            try:
                buttons={w.text:w for w in popup.walk() if hasattr(w,'dispatch') and getattr(w,'text',None) in ('從資料庫預覽','同步此地圖並預覽')}
                buttons['從資料庫預覽'].dispatch('on_release')
                self.assertFalse(job.start.call_args.kwargs['download'])
                poll=clock.schedule_interval.call_args.args[0];poll(0)
                self.assertTrue(any('1.00, 2.00' in getattr(w,'text','') for w in popup.walk()))
                job.start.side_effect=ValueError('invalid input')
                buttons['同步此地圖並預覽'].dispatch('on_release');poll(0)
                self.assertTrue(any(getattr(w,'text','')=='invalid input' for w in popup.walk()))
                d.send.assert_not_called()
            finally:popup.dismiss()
        clock.schedule_interval.return_value.cancel.assert_called_once()
        job.close.assert_called_once()


if __name__=='__main__':unittest.main()
