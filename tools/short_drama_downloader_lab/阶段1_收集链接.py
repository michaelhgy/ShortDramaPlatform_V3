# -*- coding: utf-8 -*-
r"""
V3 手机采集执行步骤。
任务身份、成果和最终完成由 V3 管理；本脚本只接收任务卡片与集数计划，
选择连续缺失段、确认当前集、复制分享链接，并逐集报告结果。
指定补采不会删除原记录，也不会改读其他卡片或重启微信。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import 视图 as V                      # noqa: E402
import 导航 as N                      # noqa: E402
from 读剪贴板历史 import newest_share   # noqa: E402

HERE = Path(__file__).resolve().parent
TABLE = HERE / "采集表.txt"

# 阶段 1 靠"读输入法的剪贴板历史"拿链接，所以必须用【会记录历史】的普通输入法。
# （ADBKeyboard 是极简输入法，不记录历史 —— 那是阶段 2 用来做广播输入的）
IME_RECORDING = "com.sohu.inputmethod.sogouoem/.SogouIME"


# ────────────────────── 采集表 ──────────────────────
def load_table() -> dict:
    """返回 {(剧名, 集数): 链接}"""
    rows = {}
    if TABLE.exists():
        for line in TABLE.read_text(encoding="utf-8").splitlines():
            p = line.split("\t")
            if len(p) >= 3:
                m = re.search(r"\d+", p[1])
                if m:
                    rows[(p[0], int(m.group(0)))] = p[2]
    return rows


def save_table(rows: dict):
    temporary = TABLE.with_suffix(TABLE.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        for (d, e), link in sorted(rows.items()):
            f.write(f"{d}\t第{e}集\t{link}\n")
        f.flush()
    temporary.replace(TABLE)


def missing_ranges(have: set, total: int, start: int = 1):
    """算出缺失的连续区间：缺 3/6-8/11-13/19 → [(3,3), (6,8), (11,13), (19,19)]"""
    out = []
    for n in sorted(set(range(start, total + 1)) - have):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [(a, b) for a, b in out]


# ────────────────────── 输入法 ──────────────────────
def ensure_recording_ime() -> bool:
    """切到会记录剪贴板历史的输入法。"""
    for u in ("", "--user 0"):
        V.sh("su", "-c", f"ime set {u} {IME_RECORDING}".strip())
    time.sleep(2)
    for line in V.sh("dumpsys", "input_method").splitlines():
        if "mCurMethodId=" in line:
            return "sogou" in line
    return False


# ────────────────────── 单集采集 ──────────────────────
def progress(message: str, **details) -> None:
    print("PROGRESS=" + json.dumps({"message": message, "keep": True, **details}, ensure_ascii=False), flush=True)


def grab_one(prev_link="", episode: int = 0) -> str:
    """按分享图标打开面板，右滑找到复制链接，读取剪贴板并校验更新。"""
    label = f"第{episode}集" if episode else "当前集"
    for attempt, wait in enumerate((0.9, 1.5), 1):
        progress(f"正在打开{label}分享面板（第{attempt}次尝试）")
        if not N.open_share_panel(tries=1):
            print(f"      （分享面板未出现，第{attempt}次）")
            continue
        progress(f"正在右滑{label}分享菜单，查找复制链接")
        V.swipe(1080, N.P_PANEL_ROW, 160, N.P_PANEL_ROW, 220, 0.3)
        progress(f"正在复制{label}分享链接")
        V.tap_xy(*N.P_COPY_LINK, wait=wait)
        time.sleep(0.25)
        progress(f"正在读取{label}剪贴板，确认链接已更新")
        link = newest_share() or ""
        if link and link != prev_link:
            return link
        print("      （剪贴板链接未变化，重试一次）")
    return ""


def recover_episode(target: int) -> bool:
    """只在当前任务内重新选集，不重启微信或改读其他卡片。"""
    progress(f"正在重新定位第{target}集，打开选集并确认集数")
    return bool((N.episode_sheet_open() or N.open_drama_list()) and N.tap_episode(target))


QUICK_CONFIRM_SECONDS = 2
AD_PLAY_SECONDS = 7
ADVANCE_RETRIES = 3
ADVANCE_TIMEOUT_SECONDS = 45


def advance_episode(target: int) -> bool:
    """正常换集快速确认；无横幅时等待广告可滑，再有界重试。"""
    started = time.monotonic()
    deadline = started + ADVANCE_TIMEOUT_SECONDS
    progress(f"正在滑动进入第{target}集", episode=target, action="advance")
    N.swipe_next_episode()
    last_swipe = time.monotonic()

    def check_after_wait():
        hit, episodes = N.read_drama_banner(expected_episode=target)
        if not hit:
            return None
        if episodes == [target]:
            N.pause_video()
            return True
        actual = "、".join(map(str, episodes)) or "未知"
        progress(f"当前横幅集数为{actual}，正在重新选择第{target}集", episode=target, action="advance_reselect")
        return recover_episode(target)

    for attempt in range(ADVANCE_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        progress(f"正在确认第{target}集，尚未确认前不会保存链接", episode=target, action="advance_confirm")
        if N.wait_for_drama_banner(expected_episode=target, timeout=min(QUICK_CONFIRM_SECONDS, remaining)):
            N.pause_video()
            return True
        result = check_after_wait()
        if result is not None:
            return result
        if attempt >= ADVANCE_RETRIES:
            break
        # 广告页可能需要播放6秒后再滑；不暂停、不把等待当作进入目标集。
        retry_at = last_swipe + AD_PLAY_SECONDS
        progress(f"尚未确认第{target}集，可能是广告或加载页；等待播放后再次滑动（重试{attempt+1}/{ADVANCE_RETRIES}）",
                 episode=target, action="advance_wait")
        last_report = time.monotonic()
        while time.monotonic() < retry_at:
            remaining = min(retry_at, deadline) - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))
            now = time.monotonic()
            if now - last_report >= 2:
                progress(f"等待广告或加载结束，已等待{int(now-last_swipe)}秒，目标第{target}集",
                         episode=target, action="advance_wait")
                last_report = now
        if time.monotonic() >= deadline:
            break
        # 等待期间可能已自动回到正剧，先核对，避免多滑一集。
        result = check_after_wait()
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            break
        progress(f"等待结束，正在再次滑动进入第{target}集（重试{attempt+1}/{ADVANCE_RETRIES}）",
                 episode=target, action="advance_retry")
        N.swipe_next_episode()
        last_swipe = time.monotonic()
    progress(f"等待并重试后仍未确认第{target}集，保留已采链接，停止本次采集",
             episode=target, action="advance_failed")
    return False


# ────────────────────── 主流程 ──────────────────────
def main() -> int:
    global TABLE
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--no-nav", action="store_true")
    ap.add_argument("--drama", default="")
    ap.add_argument("--task-x", type=int, default=0)
    ap.add_argument("--task-y", type=int, default=0)
    ap.add_argument("--repair", default="")
    ap.add_argument("--skip-episodes", default="")
    ap.add_argument("--table", type=Path, default=TABLE)
    args = ap.parse_args()
    TABLE = args.table
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    rows = load_table()
    repair = {int(value) for value in re.findall(r"\d+", args.repair)}
    skipped = {int(value) for value in re.findall(r"\d+", args.skip_episodes)}
    if not ensure_recording_ime():
        raise RuntimeError("无法启用剪贴板历史输入法，尚未开始采集")
    progress("正在检查当前微信页面并进入免费剧集")
    if args.no_nav:
        if not (N.episode_sheet_open() or N.in_player(refresh=True)):
            raise RuntimeError("当前已离开本任务播放页，保留成果，请重新开始以定位任务")
    elif args.task_x > 0 and args.task_y > 0:
        if not N.open_card_at(args.task_x, args.task_y):
            raise RuntimeError("打不开已经识别的任务卡片")
    elif not N.episode_sheet_open():
        raise RuntimeError("缺少已确认的任务卡片位置，未自行重启或读取其他任务")
    if not N.episode_sheet_open() and not N.open_drama_list():
        raise RuntimeError("打不开免费剧集的选集界面")
    drama = args.drama.strip() or N.read_sheet_title()
    total = N.read_total_episodes()
    if not drama or total <= 0:
        raise RuntimeError("未确认剧名或总集数，尚未开始采集")
    progress(f"手机选集页共{total}集，正在核对已有成果", action="inventory", total=total)
    have = {e for (d, e) in rows if d == drama} | skipped
    wanted = (repair if repair else set(range(args.start or 1, total + 1)) - have)
    if any(n < 1 or n > total for n in wanted):
        raise RuntimeError("补采集数超出手机选集页范围，未删除原有链接")
    # 先限定指定补采集合，再分连续段；原链接在新链接确认前一直保留。
    ranges = missing_ranges(set(range(1, total + 1)) - wanted, total)
    if args.count:
        out, left = [], args.count
        for a, b in ranges:
            if left <= 0:
                break
            take = min(b - a + 1, left)
            out.append((a, a + take - 1))
            left -= take
        ranges = out
    planned = {n for a, b in ranges for n in range(a, b + 1)}
    collected = set()
    prev_link = newest_share() or ""
    for a, b in ranges:
        progress(f"正在打开选集，查找第{a}集（本段第{a}至第{b}集）")
        if not (N.episode_sheet_open() or N.open_drama_list()) or not N.tap_episode(a):
            raise RuntimeError(f"无法确认第{a}集，保留链接和已采成果，停止本次采集")
        for n in range(a, b + 1):
            # tap_episode 或上一轮 wait 已明确确认集数；不再重复截图识别。
            progress(f"已确认第{n}集，准备复制分享链接", episode=n, action="episode_confirmed")
            link = grab_one(prev_link, episode=n)
            if not link:
                raise RuntimeError(f"第{n}集没有复制到新链接，保留原有记录")
            if any(d == drama and ep != n and old == link for (d, ep), old in rows.items()):
                raise RuntimeError(f"第{n}集链接与其他集重复，未覆盖原记录")
            rows[(drama, n)] = link
            save_table(rows)
            prev_link = link
            collected.add(n)
            progress(f"第{n}集分享链接已确认并保存", episode=n, action="collected")
            if n < b:
                if not advance_episode(n+1):
                    raise RuntimeError(f"未确认第{n+1}集，停止采集；已保存的链接可继续使用")
    print("COLLECT_RESULT=" + json.dumps({"drama": drama, "total": total,
        "collected": sorted(collected), "missing": sorted(planned-collected)}, ensure_ascii=False), flush=True)
    progress(f"链接采集结束：本轮确认{len(collected)}集，手机总集数{total}集", action="collection_done")
    return 0 if planned <= collected else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        progress(f"链接采集停止：{exc}", action="collection_error")
        raise SystemExit(2)
