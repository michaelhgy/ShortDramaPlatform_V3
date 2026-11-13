import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from server.ffmpeg_process import run_progress


class ProgressWatchdogTests(unittest.TestCase):
    def run_child(self, script, timeout=.5):
        seen=[]
        with tempfile.TemporaryFile() as log:
            result=run_progress([sys.executable,'-u','-c',script],log,
                                lambda f,end:seen.append((f,end)),stall_seconds=timeout)
        return result,seen

    def test_advancing_frames_can_take_longer_than_timeout(self):
        result,seen=self.run_child("import time\nfor n in range(1,9):\n print(f'frame={n}\\nprogress=continue',flush=True);time.sleep(.1)\nprint('progress=end',flush=True)")
        self.assertEqual(result,(0,8));self.assertEqual(seen[-1],(8,True))

    def test_no_first_frame_stops_owned_process(self):
        processes=[];original=subprocess.Popen
        def launch(*args,**kw):
            p=original(*args,**kw);processes.append(p);return p
        start=time.monotonic()
        with patch('server.ffmpeg_process.subprocess.Popen',side_effect=launch):
            with self.assertRaisesRegex(RuntimeError,'第0帧'):
                self.run_child('import time;time.sleep(30)')
        self.assertLess(time.monotonic()-start,5)
        self.assertIsNotNone(processes[0].poll())

    def test_unchanged_frame_heartbeats_do_not_extend_deadline(self):
        with self.assertRaisesRegex(RuntimeError,'第3帧'):
            self.run_child("import time\nwhile True:\n print('frame=3\\nprogress=continue',flush=True);time.sleep(.05)")

    def test_nonzero_exit_preserved(self):
        result,_=self.run_child('import sys;sys.exit(7)',timeout=2)
        self.assertEqual(result,(7,0))

    def test_callback_cancellation_stops_child(self):
        processes=[];original=subprocess.Popen
        def launch(*args,**kw):
            p=original(*args,**kw);processes.append(p);return p
        def cancel(*args):raise ValueError('cancel test')
        with patch('server.ffmpeg_process.subprocess.Popen',side_effect=launch),tempfile.TemporaryFile() as log:
            with self.assertRaisesRegex(ValueError,'cancel test'):
                run_progress([sys.executable,'-u','-c',"import time;print('frame=1\\nprogress=continue',flush=True);time.sleep(30)"],log,cancel)
        self.assertIsNotNone(processes[0].poll())


if __name__=='__main__':unittest.main()
