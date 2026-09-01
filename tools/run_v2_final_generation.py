"""Queue one V2 material for real Jianying finished-draft generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.final_engine.runner import start_finished_video


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video_id", help="production_video_tasks.id")
    args = parser.parse_args()
    print(start_finished_video(args.video_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
