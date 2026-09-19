"""功能档案自检：扫 docs/功能档案/ 里的说明书，报出"补丁式写法"和结构缺项。

用法：
    py -3.12 tools/check_feature_archive.py
或双击 tools\\查功能档案.bat

只读脚本：不修改任何文件。
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "docs" / "功能档案"

# 标准文件里会“举例说明不要这么写”，所以不检查它们的内容用词
STANDARD_FILES = {"README.md", "_模板.md"}

PATCH_WORDS = [
    "原来是什么", "还没做", "没有入口", "已知局限", "别搞混",
    "历史上", "至今没", "未验证", "未复核", "暂无", "已删除", "不会再", "已经不用",
]
OWNER_WORDS = ["用户定", "用户拍板", "用户原话", "用户明确", "用户说"]

REQUIRED = ["他会这么说", "改动须知", "代码入口"]


def check(path: Path) -> list[str]:
    issues: list[str] = []
    text = io.open(path, encoding="utf-8").read()
    lines = text.splitlines()
    is_standard = path.name in STANDARD_FILES

    if not is_standard:
        for i, line in enumerate(lines, 1):
            for w in PATCH_WORDS:
                if w in line:
                    issues.append(f"  补丁式写法「{w}」 第 {i} 行：{line.strip()[:60]}")
            for w in OWNER_WORDS:
                if w in line:
                    issues.append(f"  标了“谁定的”「{w}」 第 {i} 行：{line.strip()[:60]}")

    for key in REQUIRED:
        if key not in text:
            issues.append(f"  缺结构：找不到「{key}」")

    if not is_standard and len(lines) > 150:
        issues.append(f"  偏长：{len(lines)} 行（建议 ≤150）")

    # 第五段里的编号规则：至少 3 条
    m = re.search(r"## 五、.*?\n(.*?)(?=\n## |\Z)", text, re.S)
    if m:
        numbered = re.findall(r"^\s*\d+\.\s+\*\*", m.group(1), re.M)
        if len(numbered) < 3:
            issues.append(f"  第五段编号规则只有 {len(numbered)} 条（建议 ≥3：改这里要注意什么）")
    return issues


def main() -> int:
    if not ARCHIVE_DIR.is_dir():
        print(f"找不到目录：{ARCHIVE_DIR}")
        return 1

    files = sorted(p for p in ARCHIVE_DIR.rglob("*.md"))
    if not files:
        print("功能档案目录是空的。")
        return 0

    total_issues = 0
    print("=" * 68)
    print("功能档案自检（只读）")
    print("=" * 68)
    for path in files:
        rel = path.relative_to(ARCHIVE_DIR)
        issues = check(path)
        if issues:
            total_issues += len(issues)
            print(f"\n[需要看] {rel}")
            for item in issues:
                print(item)
        else:
            print(f"[OK] {rel}")

    print("\n" + "=" * 68)
    if total_issues:
        print(f"共 {len(files)} 份，发现 {total_issues} 处待看。")
        print("规则：只记规则，不打补丁；不写“已取消/没做/没验证”，也不标“谁定的”。")
        print("     要写“没做/没验证” → 去 docs/待做需求清单.md。")
    else:
        print(f"共 {len(files)} 份，全部通过。")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
