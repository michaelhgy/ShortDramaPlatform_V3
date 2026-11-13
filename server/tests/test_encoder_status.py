import json
from pathlib import Path
import tempfile
import unittest

from server.encoder_status import job_encoder_status


class EncoderStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = {'id': 'a' * 32, 'attempt': 1, 'status': 'running'}
        self.path = self.root / ('a' * 12) / 'a1' / 'encoder_check.json'
        self.path.parent.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def test_real_old_driver_message_preserves_required_driver_and_raw_evidence(self):
        diagnostic = ('[h264_nvenc] Driver does not support the required nvenc API version. '
                      'Required: 13.0 Found: 11.0\r\n'
                      '[h264_nvenc] The minimum required Nvidia driver for nvenc is 570.0 or newer')
        self.write({'encoder': 'libx264', 'returncode': 4294967256, 'diagnostic': diagnostic})
        result = job_encoder_status(self.root, self.job)
        self.assertIn('驱动不兼容', result['warning']['reason'])
        self.assertIn('570.0', result['warning']['action'])
        self.assertNotIn('13.0', result['warning']['action'])
        self.assertEqual(diagnostic, result['warning']['diagnostic'])

    def test_unknown_failure_does_not_invent_driver_version_or_cause(self):
        for diagnostic in ('No NVENC capable devices found', 'OpenEncodeSessionEx failed', '', None):
            with self.subTest(diagnostic=diagnostic):
                self.write({'encoder': 'libx264', 'diagnostic': diagnostic})
                result = job_encoder_status(self.root, self.job)
                self.assertEqual(result['encoder'], 'libx264')
                self.assertNotIn('驱动不兼容', result['warning']['reason'])
                self.assertNotIn('570', result['warning']['action'])

    def test_missing_partial_invalid_or_oversized_logs_do_not_break_snapshot(self):
        self.assertIsNone(job_encoder_status(self.root, self.job))
        for data in ('{"encoder":', 'null', '[]', '{}', '{"encoder":"unknown"}', 'x' * 16_385):
            with self.subTest(data=data[:30]):
                self.path.write_text(data, encoding='utf-8')
                self.assertIsNone(job_encoder_status(self.root, self.job))
        self.path.write_bytes(b'\xff')
        self.assertIsNone(job_encoder_status(self.root, self.job))
        self.write({'encoder': 'h264_nvenc', 'returncode': 0, 'diagnostic': ''})
        self.assertEqual({'encoder': 'h264_nvenc', 'warning': None}, job_encoder_status(self.root, self.job))

    def test_retry_uses_only_its_own_attempt_and_waiting_does_not_reuse_old_warning(self):
        self.write({'encoder': 'libx264', 'diagnostic': 'old failure'})
        self.assertIsNotNone(job_encoder_status(self.root, self.job)['warning'])
        for status in ('waiting', 'cancelled'):
            self.assertIsNone(job_encoder_status(self.root, {**self.job, 'status': status}))
        retry = {**self.job, 'attempt': 2}
        self.assertIsNone(job_encoder_status(self.root, retry))
        new_path = self.path.parent.parent / 'a2' / self.path.name
        new_path.parent.mkdir()
        new_path.write_text('{"encoder":"h264_nvenc"}', encoding='utf-8')
        self.assertIsNone(job_encoder_status(self.root, retry)['warning'])
        self.assertIsNotNone(job_encoder_status(self.root, {**self.job, 'status': 'done'})['warning'])
