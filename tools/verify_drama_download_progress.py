"""Isolated checks for live downloader progress; no phone or business data access."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import drama_download_reader as reader


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / 'short_drama_downloader_lab' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'V3_DRAMA_READ_TASK_STATE': str(self.folder / 'state.json')})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.old_state = dict(reader._STATE)
        self.addCleanup(lambda: (reader._STATE.clear(), reader._STATE.update(self.old_state)))
        reader._STATE.clear()
        reader._STATE.update(status='running', phase='parse-download', current_step='准备解析', stage_logs={})

    def test_live_subprocess_request_download_and_title_mismatch(self):
        received_request = threading.Event()
        release_response = threading.Event()
        payload = b'fixture' * (512 * 1024)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received_request.set()
                release_response.wait(12)
                title = 'fixture-第11集' if request['baseurl'].endswith('/11') else 'fixture-第99集'
                body = json.dumps({'code': 1, 'data': {'title': title, 'url': f'http://127.0.0.1:{self.server.server_port}/video'}}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                for offset in range(0, len(payload), 256 * 1024):
                    self.wfile.write(payload[offset:offset + 256 * 1024])
                    self.wfile.flush()
                    time.sleep(.1)

        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        config = self.folder / 'config.json'
        config.write_text(json.dumps({'uid': 'fixture', 'agentid': 'fixture', 'analysis_api': f'http://127.0.0.1:{http.server_port}/parse', 'download_timeout_seconds': 15, 'request_interval_seconds': 0}), encoding='utf-8')
        table = self.folder / 'table.txt'
        table.write_text('other\t第1集\thttp://fixture/1\nfixture\t第11集\thttp://fixture/11\nfixture\t第12集\thttp://fixture/12\n', encoding='utf-8')
        wrapper = self.folder / 'run.py'
        wrapper.write_text(f'''import importlib.util,json\nfrom pathlib import Path\nspec=importlib.util.spec_from_file_location("downloader", {str(ROOT / 'tools/short_drama_downloader_lab/批量解析下载.py')!r})\nm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\nm.load_config=lambda:json.loads(Path({str(config)!r}).read_text())\nm.probe_video=lambda path:{{"duration":12}}\nraise SystemExit(m.main())\n''', encoding='utf-8')
        command = [sys.executable, '-u', '-X', 'utf8', str(wrapper), '--table', str(table), '--drama', 'fixture', '--limit', '2', '--output-root', str(self.folder / 'videos'), '--result-path', str(self.folder / 'result.jsonl'), '--log-path', str(self.folder / 'download.log')]
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(reader._run(command, lambda _: None)), daemon=True)
        thread.start()
        self.assertTrue(received_request.wait(8), 'mock parser was not called')
        try:
            self.assertIn('正在解析第11集', reader._STATE['current_step'])
            time.sleep(5.2)
            self.assertIn('已等待', reader._STATE['current_step'])
            self.assertFalse((self.folder / 'videos').exists(), 'progress must appear before the response')
        finally:
            release_response.set()
        thread.join(12)
        self.assertFalse(thread.is_alive())
        code, lines = outcome[0]
        self.assertEqual(code, 1, 'mismatched episode should fail')
        events = [json.loads(line.removeprefix('PROGRESS=')) for line in lines if line.startswith('PROGRESS=')]
        actions = [event['action'] for event in events]
        self.assertEqual(actions[:3], ['parse', 'parsed', 'connect'])
        downloads = [event for event in events if event['action'] == 'download']
        self.assertGreaterEqual(len(downloads), 3)
        self.assertTrue(any(0 < event['bytes'] < len(payload) for event in downloads))
        self.assertEqual(downloads[-1]['bytes'], len(payload))
        self.assertEqual((self.folder / 'videos/fixture/fixture-第011集.mp4').read_bytes(), payload)
        self.assertFalse((self.folder / 'videos/fixture/fixture-第099集.mp4').exists())
        logs = reader._STATE['stage_logs']['parse-download']
        self.assertTrue(any('解析返回名称' in message for message in logs))
        self.assertTrue(any('第11集下载完成' in message for message in logs))
        self.assertFalse(any('已接收' in message for message in logs), 'byte updates should not flood history')

    def test_collector_actions_before_phone_operations(self):
        view = types.ModuleType('视图')
        nav = types.ModuleType('导航')
        clipboard = types.ModuleType('读剪贴板历史')
        clipboard.newest_share = lambda: 'http://fixture/new'
        nav.P_PANEL_ROW, nav.P_COPY_LINK = 10, (20, 30)
        output = io.StringIO()
        def assert_before(phrase):
            self.assertIn(phrase, output.getvalue().splitlines()[-1])
            return True
        nav.open_share_panel = lambda **_: assert_before('打开第11集分享面板')
        view.swipe = lambda *_: assert_before('右滑第11集分享菜单')
        view.tap_xy = lambda *_, **__: assert_before('复制第11集分享链接')
        with patch.dict(sys.modules, {'视图': view, '导航': nav, '读剪贴板历史': clipboard}):
            collector = load('collector_fixture', '阶段1_收集链接.py')
        with contextlib.redirect_stdout(output), patch.object(collector.time, 'sleep', lambda _: None):
            self.assertEqual(collector.grab_one('old', episode=11), 'http://fixture/new')
        self.assertIn('读取第11集剪贴板', output.getvalue())
        # Exercise the --no-nav branch, which must not refer to a range before it is computed.
        nav.in_player = lambda **_: True
        nav.episode_sheet_open = lambda: True
        nav.read_total_episodes = lambda: 1
        nav.tap_episode = lambda _: True
        nav.read_episode = lambda: 1
        nav.open_share_panel = lambda **_: True
        view.swipe = view.tap_xy = lambda *_, **__: None
        shares = iter(['old', 'http://fixture/1'])
        with patch.object(sys, 'argv', ['collector', '--no-nav', '--drama', 'fixture', '--table', str(self.folder/'collect.txt')]), patch.object(collector, 'ensure_recording_ime', lambda: True), patch.object(collector, 'newest_share', lambda: next(shares)), patch.object(collector.time, 'sleep', lambda _: None), contextlib.redirect_stdout(io.StringIO()):
            collector.main()
        self.assertIn('第1集', (self.folder/'collect.txt').read_text(encoding='utf-8'))

    def test_recover_interrupted_state_and_verify_phase(self):
        (self.folder/'state.json').write_text(json.dumps({'status':'running','phase':'parse-download','current_step':'解析第11集','task':{'drama_name':'fixture'}}), encoding='utf-8')
        reader._STATE.clear()
        reader._STATE.update(status='idle')
        self.assertEqual(reader.status()['status'], 'failed')
        self.assertIn('中断', reader._STATE['current_step'])
        self.assertEqual(reader._STATE['task']['drama_name'], 'fixture')
        videos = self.folder / 'fixture'
        videos.mkdir()
        (videos/'fixture-第011集.mp4').write_bytes(b'x'*100001)
        service = types.ModuleType('server.v2_file_service')
        service.get_v2_settings = lambda: {'drama_download_root': str(self.folder)}
        reader._STATE.update(expected_count=11, episodes={'11': {'file': str(videos/'fixture-第011集.mp4'), 'link':'fixture', 'confirmation_source':'parser'}})
        with patch.dict(sys.modules, {'server.v2_file_service': service}), patch.object(reader, '_theater_for_drama', lambda _: ''), patch.object(reader, 'probe_video', lambda path, **_: {'duration':12, 'bytes':path.stat().st_size, 'mtime_ns':path.stat().st_mtime_ns}):
            reader._verify_worker()
        self.assertTrue(any('正在校验' in message for message in reader._STATE['stage_logs']['verify-download']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
