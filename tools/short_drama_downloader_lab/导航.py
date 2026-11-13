# -*- coding: utf-8 -*-
r"""
导航 —— 只负责"在微信里走路"和"读页面上的字"

职责边界（重要）：
  · 这个文件【只做微信界面操作】，不碰采集表、不碰剪贴板、不碰下载
  · 坐标全部标注了实测来源；能认字就认字，认不了才用固定坐标

页面（实测）：
  聊天页      com.tencent.mm/.ui.LauncherUI
  剧集播放页   ...finder.drama.timeline.FinderNativeDramaTimelineUI
  剧集界面    播放页上弹出的浮层（同一个 activity，靠页签判断开没开）
"""
import re
import time

import 视图 as V

WX_USER = "0"                         # 当前使用主微信
WX_PKG = "com.tencent.mm"
PLAYER_ACT_HINTS = ("FinderNativeDramaTimelineUI",   # 从剧集界面进来的播放页
                    "FinderShareFeedRelUI")          # 从卡片直接进来的播放页

# ── 区域（实测坐标，别随手改）──
R_CHAT_TOP = (0, 200, 1240, 560)       # 聊天列表顶部（找第一条置顶聊天）
R_CHAT_BOTTOM = (0, 250, 1240, 2600)   # 聊天消息区，避开底部输入框提示
R_CHAT_SCAN = (120, 250, 1120, 2600)   # 卡片图像扫描区，避开头像和输入框
R_BANNER = (0, 2100, 1240, 2460)       # 播放页底部「免费剧集：<剧名>第N集」（y 在 2230~2380 浮动）
R_BANNER_LEFT = (0, 2050, 800, 2480)   # 横幅局部区，避免整屏 OCR
# 横幅文字通常在左侧；右侧是视频画面字幕，尤其第11集时容易把两段文字
# OCR 合成一条。窄区优先，宽区只作兜底。
R_BANNER_TEXT = (0, 2240, 700, 2420)
R_EP_TITLE = (0, 850, 1240, 1010)      # 剧集界面上的剧名（实测 y≈927）
R_EP_TABS = (0, 1150, 1240, 1330)      # 剧集界面的「1-30」这类页签
R_EP_GRID = (0, 1330, 1240, 2300)      # 剧集界面的集号网格

# ── 播放页坐标 ──
R_ACTION_BAR = (0, 2500, 1240, 2772)   # 底部动作栏（点赞/转发/推荐/评论 四个数字）
P_PANEL_ROW = 2432                     # 分享面板图标行 y
P_COPY_LINK = (1122, 2431)             # 「复制链接」
P_VIDEO_CENTER = (620, 1100)           # 画面中央（点一下 = 播放/暂停 切换）
BTN_DY = 80                            # 数字在按钮下方约 80px（实测：点数字上方 80px 能打开面板）
P_SHARE_FALLBACK = (900, 2572)         # 认不到数字时的兜底（实测）


def share_button():
    """识别底部动作栏图标，点击从左数第二个分享箭头。

    不使用点赞数、转发数等文字。图标位置会随页面布局变化，
    通过亮色图标的连通区域识别四个操作按钮，再取第二个图标中心。
    """
    try:
        import cv2
        import numpy as np

        img = np.asarray(V.screenshot("action-bar.png").convert("RGB"))
        x1, y1, x2, y2 = 450, 2480, 1230, 2605
        gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_RGB2GRAY)
        mask = ((gray > 170) & (gray < 255)).astype("uint8") * 255
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        icons = []
        for x, y, w, h, area in stats[1:]:
            if 45 <= w <= 90 and 45 <= h <= 90 and area >= 400:
                icons.append((x + x1, y + y1, w, h))
        icons.sort(key=lambda box: box[0])
        if len(icons) >= 3:
            x, y, w, h = icons[1]
            return x + w // 2, y + h // 2
    except Exception:
        pass
    return P_SHARE_FALLBACK


R_SHEET = (0, 1950, 1240, 2620)        # 分享面板（只在下半部）


def panel_open() -> bool:
    """分享面板开着吗。
    ⚠️ 只读面板那一块（约 0.5 秒），别整屏 OCR（1.8 秒）——
       那就是肉眼看到的"点开分享后发呆"。"""
    V.refresh(crop=R_SHEET)
    for it in V.items():
        if any(k in it["text"] for k in ("复制链接", "转发给朋友", "分享到朋友圈", "设为铃声")):
            return True
    return False


def open_share_panel(tries=2) -> bool:
    """点转发把分享面板打开；没开就重试（用最新算出的坐标）。
    这个确认很重要 —— 面板没开的话，后面的"滑动+点复制链接"全都落在视频上，
    表现就是"漏点分享"和"莫名其妙点了暂停"。"""
    for i in range(tries):
        V.tap_xy(*share_button(), wait=1.2)
        if panel_open():
            return True
        print(f"      （面板没开，重试第{i+2}次）")
        time.sleep(0.4)
    return False

RE_TIME = re.compile(r"^\d{1,2}[:：]\d{2}$")


# ────────────────────── 基础 ──────────────────────
def safe_x(x) -> int:
    """把 x 钳到安全区，避开屏幕两侧 150px。
    ⚠️ 安卓的"从边缘往里滑"是系统返回手势 —— 贴边滑会被当成返回，滑几次就把微信退出去了。"""
    return max(150, min(1090, int(x)))


def swipe_safe(x1, y1, x2, y2, ms=250, wait=0.5):
    V.swipe(safe_x(x1), y1, safe_x(x2), y2, ms, wait)


def find_in(region, *keys, exclude_time=True, min_len=1):
    """在【当前缓存】的整屏 OCR 结果里，挑出落在 region 内、包含 keys 之一的元素。
    ⚠️ 用之前必须先 V.refresh()，否则读到的是上一次的画面。"""
    x1, y1, x2, y2 = region
    for it in V.items():
        if not (x1 <= it["x"] <= x2 and y1 <= it["y"] <= y2):
            continue
        if exclude_time and RE_TIME.match(it["text"]):
            continue
        if len(it["text"]) < min_len:
            continue
        for k in keys:
            if k in it["text"]:
                return it
    return None


def _active_pixel(rgb) -> bool:
    r, g, b = rgb
    return max(rgb) - min(rgb) > 25 or min(rgb) < 190


def bottom_card_area(img=None):
    """从聊天截图中找最后一个大卡片图像块。

    聊天中的剧名有明确的 # 前缀，卡片本身用图像块定位。这样不会把封面文字、
    账号名或输入框提示当成卡片锚点。
    """
    if img is None:
        img = V.screenshot()
    pix = img.load()
    x1, y1, x2, y2 = R_CHAT_SCAN
    xs = list(range(x1, x2, 4))
    threshold = max(25, len(xs) // 6)
    row_counts = []
    for y in range(y1, y2):
        count = sum(_active_pixel(pix[x, y]) for x in xs)
        row_counts.append(count)

    groups = []
    start = None
    gap = 0
    for offset, count in enumerate(row_counts):
        y = y1 + offset
        if count >= threshold:
            if start is None:
                start = y
            gap = 0
            continue
        if start is None:
            continue
        gap += 1
        if gap <= 3:
            continue
        end = y - gap
        if end - start + 1 >= 250:
            groups.append((start, end))
        start = None
        gap = 0
    if start is not None and y2 - start >= 250:
        groups.append((start, y2 - 1))
    if not groups:
        return None

    top, bottom = groups[-1]
    height = max(1, bottom - top)
    col_groups = []
    col_start = None
    col_gap = 0
    for x in xs:
        count = sum(_active_pixel(pix[x, y]) for y in range(top, bottom, 4))
        active = count >= max(8, height // 16)
        if active:
            if col_start is None:
                col_start = x
            col_gap = 0
            continue
        if col_start is None:
            continue
        col_gap += 1
        if col_gap <= 2:
            continue
        end = x - col_gap * 4
        if end - col_start >= 100:
            col_groups.append((col_start, end))
        col_start = None
        col_gap = 0
    if col_start is not None:
        col_groups.append((col_start, x2 - 1))
    if not col_groups:
        return None
    left, right = max(col_groups, key=lambda q: q[1] - q[0])
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "x": (left + right) // 2,
        "y": (top + bottom) // 2,
    }


def read_bottom_task(img=None):
    """读取最后一个 #剧名及其下方卡片的点击位置。"""
    if img is None:
        img = V.screenshot()
    V.refresh(crop=R_CHAT_BOTTOM, img=img)
    tags = [i for i in V.items() if i["text"].strip().startswith("#")]
    if not tags:
        return None
    tag = max(tags, key=lambda i: i["y"])
    area = bottom_card_area(img)
    if not area or area["top"] <= tag["y"]:
        return None
    return {
        "text": tag["text"].strip(),
        "label_text": tag["text"].strip(),
        "label_x": tag["x"],
        "label_y": tag["y"],
        "x": area["x"],
        "y": area["y"],
        "raw_y": area["bottom"],
        "card_area": area,
    }


def _banner_items(expected_episode=0):
    """同一截图先识别窄区，未确认横幅或目标集时才扩大区域。"""
    image = V.screenshot("banner.png")
    items = V.refresh(crop=R_BANNER_TEXT, img=image)
    if _banner_hit(items) and (not expected_episode or _banner_episodes(items) == [expected_episode]):
        return items
    return V.refresh(crop=R_BANNER_LEFT, img=image)


def _banner_hit(items):
    # 允许 OCR 把“免费剧集”拆开或漏掉一个字，但必须同时出现“免费”和“剧/集”。
    for item in items:
        text = item["text"].replace(" ", "")
        if "免费" in text and ("剧集" in text or ("剧" in text and "集" in text)):
            return item
    return None


def _banner_episodes(items):
    # OCR 可能把免费剧集和第N集拆成相邻文字块，仅接受横幅同一行的集号。
    hits = [item for item in items if "免费" in item["text"]]
    numbers = []
    for item in items:
        text = item["text"].replace(" ", "")
        same_line = any(abs(item.get("y", 0) - hit.get("y", 0)) <= 35 for hit in hits)
        if "免费" in text or same_line:
            numbers.extend(int(value) for value in re.findall(r"第\s*(\d+)\s*集", text))
    return list(dict.fromkeys(numbers))


def read_drama_banner(expected_episode=0):
    """返回局部横幅和实际集数；无横幅不能据此断言一定是广告。"""
    items = _banner_items(expected_episode=expected_episode)
    return _banner_hit(items), _banner_episodes(items)


def wait_for_drama_banner(expected_episode=0, timeout=30):
    """等待左下短剧横幅，并可选校验当前集数。

    集数校验只在“免费剧集”横幅的固定左下区域进行。右侧视频字幕即使
    出现“第11集”，也不会被当作横幅集数；OCR 漏掉集数时只表示页面可见，不能证明已进入目标集；有界等待后由采集器重新选集。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        items = _banner_items(expected_episode=expected_episode)
        hit = _banner_hit(items)
        if hit:
            episodes = _banner_episodes(items)
            if not expected_episode or episodes == [expected_episode]:
                return hit
        time.sleep(0.5)
    return None


# ────────────────────── 页面判断 ──────────────────────
def in_player(refresh=False) -> bool:
    """只把出现“免费剧集”横幅的页面认作短剧播放页。"""
    return _banner_hit(_banner_items()) is not None


def episode_sheet_open() -> bool:
    """分页页签，或无页签时的连续集号网格；不把单个数字当选集页。"""
    V.refresh(crop=R_EP_TABS)
    if any(re.fullmatch(r"\d+\s*-\s*\d+", it["text"].strip()) for it in V.items()):
        return True
    V.refresh(crop=R_EP_GRID)
    nums = {int(it["text"]) for it in V.items() if re.fullmatch(r"\d{1,2}", it["text"].strip())}
    return any({n, n+1, n+2, n+3} <= nums for n in nums)


# ────────────────────── 动作 ──────────────────────
def restart_wechat(wait=9):
    """只操作主微信用户0。"""
    V.sh("am", "force-stop", "--user", WX_USER, WX_PKG, root=True)
    time.sleep(3)
    V.sh("am", "start", "--user", WX_USER, "-f", "0x10000000", "-n", f"{WX_PKG}/.ui.LauncherUI")
    deadline = time.time() + wait
    while time.time() < deadline:
        state = V.sh("dumpsys", "activity", "activities")
        if re.search(r"u0\s+com\.tencent\.mm/", state):
            return
        time.sleep(0.5)
    raise RuntimeError("主微信用户0未到达前台，未继续执行")


def open_file_helper(verbose=True) -> bool:
    """进「文件传输助手」聊天。打开后自动停在最新消息，不用滑。"""
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    V.refresh()
    hit = find_in(R_CHAT_TOP, "文件传输助手")
    if not hit:
        log("❌ 顶部找不到「文件传输助手」")
        return False
    log("点「文件传输助手」")
    V.tap_xy(hit["x"], hit["y"], wait=2.2)
    return True


def open_first_pinned_chat(verbose=True) -> bool:
    """从主微信聊天列表进入第一条置顶聊天。"""
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    V.refresh(crop=R_CHAT_TOP)
    cands = []
    for it in V.items():
        t = it["text"].strip()
        if not (250 <= it["y"] <= 500):
            continue
        if not t or RE_TIME.match(t) or t.isdigit():
            continue
        if t in ("微信", "通讯录", "发现", "我"):
            continue
        cands.append(it)
    if not cands:
        log("❌ 找不到第一条置顶聊天")
        return False
    top = min(cands, key=lambda i: i["y"])
    log(f"点第一条置顶聊天「{top['text'][:24]}」")
    V.tap_xy(safe_x(top["x"]), top["y"], wait=2.2)
    return True


def open_bottom_card(verbose=True):
    """点击最后一个 #剧名 下方的卡片，进入视频号播放页。"""
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    task = read_bottom_task()
    if not task:
        log("❌ 没有找到最后一个 #剧名 + 卡片")
        return False
    log(f"点最后一个任务「{task['label_text'][:24]}」")
    V.tap_xy(safe_x(task["x"]), task["y"], wait=1.0)

    if not wait_for_drama_banner(timeout=30):
        log("❌ 30 秒内没有出现「免费剧集」横幅")
        return False

    # 卡片打开后先确认短剧横幅，再暂停一次
    pause_video()
    log("已暂停")
    return True


def open_card_at(x: int, y: int, verbose=True):
    """Use the card position already identified by the V3 reader."""
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    log("点击已识别的剧集卡片")
    V.tap_xy(safe_x(x), int(y), wait=1.0)
    if not wait_for_drama_banner(timeout=30):
        log("❌ 30 秒内没有出现「免费剧集」横幅")
        return False
    pause_video()
    log("已暂停")
    return True


def pause_video():
    """点画面中央 = 播放/暂停【切换】。
    只在"确定正在播"的时候点（比如刚点开卡片、刚切完集、刚下滑）——
    已经暂停了再点会变成播放。"""
    V.tap_xy(P_VIDEO_CENTER[0], P_VIDEO_CENTER[1], wait=0.4)


def open_drama_list(tries=3) -> bool:
    """点底部「免费剧集」横幅，打开剧集界面（浮层）。
    ⚠️ 每次都先 refresh 再找 —— 不刷新就会拿旧画面找，明明在屏幕上却"找不到"。"""
    for attempt in range(1, tries + 1):
        hit = wait_for_drama_banner(timeout=5)
        if not hit:
            print("      ⚠️ 屏幕上没有「免费剧集」横幅")
            continue
        if attempt == 1:
            print(f"      点横幅「{hit['text'][:26]}」")
        V.tap_xy(hit["x"], hit["y"], wait=1.5)
        for _ in range(8):
            if episode_sheet_open():
                return True
            time.sleep(0.5)
    print("      ⚠️ 剧集界面打不开")
    return False


def tap_episode(n: int) -> bool:
    """在剧集界面点第 n 集。
    ⚠️ 页签会随总集数变（实测见过 1-30 / 31-60 / 61-90 / 91-92），
       所以【按页签上写的范围】挑，而不是只在前两个里选 ——
       之前写死"第二个页签"，点第 78 集就选错页签、找不到格子。"""
    V.refresh(crop=R_EP_TABS)
    tabs = []
    for it in V.items():
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", it["text"].strip())
        if m:
            tabs.append((int(m.group(1)), int(m.group(2)), it))
    tabs.sort(key=lambda t: t[0])

    for lo, hi, it in tabs:
        if lo <= n <= hi:
            V.tap_xy(it["x"], it["y"], wait=1.0)
            break

    V.refresh(crop=R_EP_GRID)
    cands = [i for i in V.items()
             if i["text"].strip(".．") == str(n) and i["score"] > 0.7]
    if not cands:
        got = sorted({int(i["text"]) for i in V.items() if i["text"].strip().isdigit()})
        print(f"      ⚠️ 网格里找不到第 {n} 集（这页有：{got[:16]}）")
        return False
    tgt = min(cands, key=lambda i: i["y"])
    V.tap_xy(tgt["x"], tgt["y"], wait=1.0)
    if not wait_for_drama_banner(expected_episode=n, timeout=30):
        print(f"      ⚠️ 30 秒内没有确认第 {n} 集播放页")
        return False
    pause_video()
    return True


def swipe_next_episode(dist=520, wait=0.3):
    """在视频区往上滑 = 下一集。

    ⚠️ 不在这里读屏找横幅位置 —— 那要整屏截屏+OCR（约 1.8 秒），
       就是肉眼看到的"下滑之后发呆"。滑动位置用固定坐标：
       视频区大约在 y 400~2200，从中间往上滑 520px 刚好一集。
    ⚠️ 距离要短：滑 1400px 会一次翻好几集（实测第1集直接跳到第6集）。
    """
    swipe_safe(620, 1400, 620, 1400 - dist, 240, wait)


# ────────────────────── 读页面上的字 ──────────────────────
def read_episode() -> int:
    """读取左下短剧横幅里的「第 N 集」。"""
    items = _banner_items()
    episodes = _banner_episodes(items)
    if episodes:
        return episodes[0]
    return 0


def read_sheet_title() -> str:
    """剧集界面上的剧名（y≈927）。
    ⚠️ 这是最可靠的读剧名位置 —— 播放页顶部只有备案号，读不到。"""
    V.refresh(crop=R_EP_TITLE)
    best = ""
    for it in V.items():
        t = it["text"].strip()
        if (len(t) >= 3 and not t.isdigit()
                and not re.fullmatch(r"\d+\s*-\s*\d+", t)
                and "免费剧集" not in t and "第" not in t):
            if len(t) > len(best):
                best = t
    return best.strip("…·-—-—_ ")


def read_total_episodes() -> int:
    """剧集界面的总集数。
    ⚠️ 页签「31-60」里的大数最可信（那就是它能到的最后一集）；
       网格里光认最大数字会把别的数字认进来（实测把 58 集认成了 92 集）。"""
    V.refresh(crop=R_EP_TABS)
    total = 0
    for it in V.items():
        m = re.search(r"\d+\s*-\s*(\d+)", it["text"])
        if m:
            total = max(total, int(m.group(1)))
    if total:
        return total

    # 兜底：30 集以内没有 x-y 页签，看网格里连续的那一串
    V.refresh(crop=R_EP_GRID)
    nums = sorted({int(i["text"]) for i in V.items()
                   if re.fullmatch(r"\d{1,3}", i["text"].strip("."))})
    if not nums:
        return 0
    run = best = 1
    for a, b in zip(nums, nums[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return nums[0] + best - 1 if nums[0] == 1 else nums[-1]


# ────────────────────── 编排 ──────────────────────
def goto_player(verbose=True) -> bool:
    """从任意状态走到【剧集播放页】（点开最下面那条卡片）。
    永远走同一条路：重启主微信 → 第一条置顶聊天 → 点卡片 → 暂停。
    不做"已经在播放页就跳过"这种聪明判断 —— 分支越多 bug 越多。"""
    log = (lambda *a: print("   ", *a)) if verbose else (lambda *a: None)
    log("重启微信 → 微信主页")
    restart_wechat()
    if not open_first_pinned_chat(verbose):
        return False
    if not open_bottom_card(verbose):
        return False
    ok = in_player()
    log("✅ 到达播放页" if ok else f"❌ 没到播放页：{V.foreground()}")
    return ok
