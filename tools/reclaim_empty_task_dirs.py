"""回收「生产文件」里的空壳目录：把已经彻底清完的任务留下的空目录链删掉。

**为什么会有这个工具**：7 天原素材清理只清空 ``素材`` 目录里的文件、**保留目录本身**，
清空之后 ``剧集``／``账号``／``日期`` 就成了挂在盘上的空壳。代码里的正常路径已经修好
（``prune_empty_task_directories()``，挂在原素材清理成功之后），本工具只处理**历史遗留**。

两遍，各管一类历史遗留：

1. **按任务往上收**：对 ``cleanup_status='raw_cleaned'`` 的任务调同一个函数 —— 这是主路径。
2. **孤儿空壳**：任务记录已经被"删除剧集"删掉、但目录还在的（``9月18日`` 的 6 个账号空壳就是这样）。
   第一遍按任务驱动，碰不到它们。第二遍有三重护栏：
   ① 除 ``.DS_Store`` 外为空（递归判定：子目录也要全部可回收）；
   ② 目录**不在**任何任务的目录里面；
   ③ 目录**内部也没有**任何任务 —— 用的是**全部任务**（含进行中的），不是只有已清理的。

**判定**：``.DS_Store`` 是苹果电脑 Finder 写下的垃圾文件、不是本系统生成的，
用户口径（2026-09-19）：**不许阻挡清理**。

**范围**：只碰 ``生产文件`` 目录本身及其下面；**数据库一个字节都不写**（只读打开）。

用法：
    python tools/reclaim_empty_task_dirs.py          # 预演，只打印
    python tools/reclaim_empty_task_dirs.py --apply  # 真删
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import v2_file_service as service  # noqa: E402

DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")


def _content_files(directory: Path) -> list[Path]:
    """目录下真实文件（``.DS_Store`` 不算内容）。"""
    return [item for item in directory.rglob("*") if item.is_file() and item.name != ".DS_Store"]


def _junk_files(directory: Path) -> list[Path]:
    return [item for item in directory.rglob("*") if item.is_file() and item.name == ".DS_Store"]


def _task_held(directory: Path, task_roots: list[Path]) -> bool:
    """目录是不是"任务的地盘"：它就是任务目录、在任务目录里面、或内部还挂着任务。"""
    for root in task_roots:
        if directory == root or directory.is_relative_to(root) or root.is_relative_to(directory):
            return True
    return False


def _orphan_candidates(production_root: Path, task_roots: list[Path]) -> list[Path]:
    """没有任务指向、且除 ``.DS_Store`` 外为空的目录（深的在前，父目录才会跟着变空）。

    递归判定：一个目录可回收 = 它不受任务保护 + 它下面没有真实文件 + 它的子目录**全部**可回收。
    碰到任务的地盘（任务目录本身／在任务目录里／内部挂着任务）就整块跳过，不再往下走。
    """
    found: list[Path] = []

    def removable(directory: Path) -> bool:
        if _task_held(directory, task_roots):
            return False
        for item in directory.iterdir():
            if item.is_dir():
                if not removable(item):
                    return False
            elif item.name != ".DS_Store":
                return False
        found.append(directory)
        return True

    for item in sorted(production_root.iterdir()):
        if item.is_dir():
            removable(item)
    return found


def main() -> None:
    apply = "--apply" in sys.argv
    production_root = Path(service.WORKSPACE) / "生产文件"
    if not production_root.is_dir():
        raise SystemExit(f"找不到生产文件目录：{production_root}")

    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        cleaned = conn.execute(
            "SELECT account_name, drama_name, root_path FROM production_tasks "
            "WHERE cleanup_status='raw_cleaned' AND root_path<>''"
        ).fetchall()
        # ⚠️ 必须是**全部**任务：正在使用的任务目录一个都不许碰。
        all_roots: list[Path] = []
        for (root_path,) in conn.execute("SELECT root_path FROM production_tasks WHERE root_path<>''"):
            try:
                all_roots.append(Path(str(root_path)).resolve())
            except OSError:
                continue
    finally:
        conn.close()

    files_before = len(_content_files(production_root))
    empty_dates = [item for item in sorted(production_root.iterdir())
                   if item.is_dir() and not _content_files(item)]
    orphans = _orphan_candidates(production_root, all_roots)

    print(f"数据盘：{service.WORKSPACE}")
    print(f"彻底清完（raw_cleaned）的任务：{len(cleaned)} 个     全部任务：{len(all_roots)} 个")
    print(f"生产文件下真实文件（.DS_Store 不算）：{files_before} 个")
    print()
    print("=" * 78)
    print("要回收的内容" + ("（即将执行）" if apply else "（预演，不写入）"))
    print("=" * 78)
    total_dirs = total_junk = 0
    for date_dir in empty_dates:
        dirs = sum(1 for item in date_dir.rglob("*") if item.is_dir())
        junk = len(_junk_files(date_dir))
        total_dirs += dirs
        total_junk += junk
        print(f"  {date_dir.name:<10} 子目录 {dirs:>4} 个   .DS_Store {junk:>4} 个   真实文件 0 个")
    print(f"  {'合计':<10} 子目录 {total_dirs:>4} 个   .DS_Store {total_junk:>4} 个")
    print()
    print("第二遍（没有任务指向的孤儿空壳）：")
    if orphans:
        for directory in orphans:
            print(f"  {directory.relative_to(production_root)}")
    else:
        print("  （无）")
    print()
    print("不动的：还有真实文件的日期目录、任何任务目录（含进行中的）、另外四个一级目录、数据库记录")

    if not apply:
        print("\n（预演结束。加 --apply 才会真删。）")
        return

    print()
    print("=" * 78)
    print("开始回收")
    print("=" * 78)
    removed = 0
    for account, drama, root_path in cleaned:
        got = service.prune_empty_task_directories(Path(str(root_path)))
        if got:
            removed += len(got)
            print(f"  {account} ×《{drama}》：回收 {len(got)} 个目录")
    print(f"  第一遍合计 {removed} 个目录")
    orphan_removed = 0
    for directory in orphans:
        try:
            # 必须用 rmtree：目录里通常还躺着 .DS_Store，rmdir 只吃全空目录、会直接失败。
            # 安全性由 _orphan_candidates 保证（除 .DS_Store 外为空 + 不受任务保护）。
            shutil.rmtree(directory)
        except OSError:
            continue
        orphan_removed += 1
        print(f"  回收孤儿空壳 {directory.relative_to(production_root)}")
    print(f"  第二遍合计 {orphan_removed} 个目录")
    print(f"\n合计回收 {removed + orphan_removed} 个目录")

    print()
    print("=" * 78)
    print("复验")
    print("=" * 78)
    left = [item.name for item in sorted(production_root.iterdir())
            if item.is_dir() and not _content_files(item)]
    files_after = len(_content_files(production_root))
    print(f"  仍然没内容的日期目录 = {len(left)} 个（应为 0）" + (f" → {left}" if left else ""))
    print(f"  真实文件 = {files_after} 个（清理前 {files_before} 个，必须一致）")
    print(f"  生产文件 根目录仍在 = {production_root.is_dir()}")
    print(f"  仍在盘上的任务目录 = {sum(1 for root in all_roots if root.is_dir())} 个"
          f"（全部任务 {len(all_roots)} 个；已清理的那批本来就该没目录）")


if __name__ == "__main__":
    main()
