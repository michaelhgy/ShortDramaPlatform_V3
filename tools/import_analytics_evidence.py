"""Import inspected evidence into the additive V3 analytics foundation.

This script never contacts Xiao V or any theater website.  It only imports the
already saved evidence files and the old V2 revenue tables, marking legacy
revenue as unverified and excluded from analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import analytics_data
from server import v2_file_service as files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--video",
        default="docs/事项档案/小V猫视频号数据补采-2026-10-30.json",
        help="已保存的小V猫视频号证据 JSON",
    )
    parser.add_argument(
        "--remaining",
        default="docs/事项档案/小V猫看板所需数据补采-2026-10-30.json",
        help="已保存的小V猫诊断/处罚证据 JSON",
    )
    parser.add_argument(
        "--key-post-daily",
        default="docs/事项档案/小V猫看板关键作品日数据-2026-10-30.json",
        help="看板排行所需的关键作品分日证据 JSON",
    )
    parser.add_argument("--skip-revenue", action="store_true")
    args = parser.parse_args()
    with files.connection() as conn:
        analytics_data.initialize(conn)
        result = {
            "video": analytics_data.import_video_evidence(conn, args.video, args.remaining, args.key_post_daily),
        }
        if not args.skip_revenue:
            result["revenue"] = analytics_data.import_legacy_revenue(conn)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
