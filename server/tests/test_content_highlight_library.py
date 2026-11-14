import tempfile
import unittest
from pathlib import Path

from server.content_highlight_library import build_library_payload, get_library, list_libraries, save_library


class ContentHighlightLibraryTests(unittest.TestCase):
    def test_materializes_versioned_ranges_and_can_reload(self):
        lines = [
            {"id": "E01-001", "episode": 1, "start": 10.0, "end": 12.0, "pause_after": 0.4, "text": "你给我滚出去"},
            {"id": "E01-002", "episode": 1, "start": 12.5, "end": 15.0, "pause_after": 0.8, "text": "这婚书今天必须撕掉"},
        ]
        story_map = {"highlights": [{
            "start_line": "E01-001", "end_line": "E01-002", "hook_label": "逼婚",
            "conflict_id": "c1", "viewer_question": "她会怎么反击？", "reason": "强冲突",
        }]}
        payload = build_library_payload(
            drama_id="drama-1", drama_title="测试剧", source_fingerprint="fp1", method_version="m1",
            lines=lines, story_map=story_map, inventory=[{"episode": 1, "source": "D:/ep1.mp4"}],
        )
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["boundaryStatus"], "ready")
        self.assertEqual(item["episode"], 1)
        self.assertLess(item["startTime"], item["endTime"])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_library(root, payload)
            self.assertEqual(len(list_libraries(root, "drama-1")), 1)
            loaded = get_library(root, "drama-1", payload["versionId"])
            self.assertEqual(loaded["items"][0]["id"], item["id"])


if __name__ == "__main__":
    unittest.main()

