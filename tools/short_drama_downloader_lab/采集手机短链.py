# -*- coding: utf-8 -*-
"""独立入口：复用已验证的手机采集逻辑，结果落在本实验目录。"""
from __future__ import annotations
import argparse, importlib.util, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = Path(r"D:\爆款拆解\阶段1_收集链接.py")

def main() -> int:
    if not OLD.exists(): print(f"找不到已验证的手机采集脚本：{OLD}"); return 2
    parser = argparse.ArgumentParser(); parser.add_argument("--count", type=int, default=0); parser.add_argument("--start", type=int, default=1); args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("legacy_link_collector", OLD)
    if spec is None or spec.loader is None: print("无法加载手机采集逻辑"); return 2
    module = importlib.util.module_from_spec(spec); sys.path.insert(0, str(OLD.parent)); spec.loader.exec_module(module)
    module.TABLE = HERE / "采集表.txt"
    forwarded = []
    if args.count: forwarded += ["--count", str(args.count)]
    if args.start > 1: forwarded += ["--start", str(args.start)]
    old_argv = sys.argv
    try: sys.argv = [str(OLD), *forwarded]; module.main()
    finally: sys.argv = old_argv
    return 0

if __name__ == "__main__": raise SystemExit(main())
