# -*- coding: utf-8 -*-
"""Read the last ``#剧名 + card`` task from the first pinned chat.

This is the first V3 integration step.  It owns only phone/WeChat reading and
does not collect links or download media.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


WX_PACKAGE = "com.tencent.mm"
WX_USER = "0"
CHAT_TOP = (0, 200, 1240, 560)
CHAT_BOTTOM = (0, 250, 1240, 2600)
CHAT_SCAN = (120, 250, 1120, 2600)
_OCR = None


def find_adb() -> str:
    path = shutil.which("adb")
    if path:
        return path
    candidates = list(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools*/**/adb.exe"))
    if candidates:
        return str(candidates[0])
    raise RuntimeError("找不到 adb.exe")


ADB = find_adb()


def shell(*args: str, timeout: int = 90) -> str:
    result = subprocess.run([ADB, "shell", *args], capture_output=True, timeout=timeout)
    return (result.stdout or b"").decode("utf-8", "ignore")


def screenshot():
    from PIL import Image
    result = subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=60)
    if result.returncode != 0 or len(result.stdout) < 10_000:
        raise RuntimeError("手机截图失败")
    from io import BytesIO
    image = Image.open(BytesIO(result.stdout))
    image.load()
    return image.convert("RGB")


def ocr(image, crop=None):
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    area = image.crop(crop) if crop else image
    offset_x, offset_y = crop[:2] if crop else (0, 0)
    result, _ = _OCR(area)
    items = []
    for box, text, score in result or []:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        items.append({
            "text": str(text).replace(" ", ""),
            "x": int(sum(xs) / 4) + offset_x,
            "y": int(sum(ys) / 4) + offset_y,
            "score": float(score),
        })
    return items


def tap(x: int, y: int, wait: float = 2.0) -> None:
    shell("input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)


def restart_main_wechat() -> None:
    shell("am", "force-stop", "--user", WX_USER, WX_PACKAGE)
    time.sleep(2)
    shell("am", "start", "--user", WX_USER, "-f", "0x10000000", "-n", f"{WX_PACKAGE}/.ui.LauncherUI")
    time.sleep(5)


def valid_chat_name(text: str) -> bool:
    text = text.strip()
    return bool(text and text not in {"当前聊天", "微信", "昨天", "今天", "前天"}
        and not re.fullmatch(r"(?:星期|周)[一二三四五六日天]|\d{1,2}[:：]\d{2}|\d{1,2}月\d{1,2}日", text))


def chat_header(image) -> str:
    # 仅从聊天页顶部标题区建立身份，列表右侧日期不是聊天名称。
    items = [item for item in ocr(image, (120, 120, 1100, 255))
             if valid_chat_name(item["text"]) and 250 < item["x"] < 1050]
    if not items:
        raise RuntimeError("未识别到聊天页顶部名称，未确认聊天身份")
    return min(items, key=lambda item: abs(item["x"] - 620))["text"].strip()


def first_pinned_chat(image) -> str:
    candidates = [item for item in ocr(image, CHAT_TOP)
                  if 250 <= item["y"] <= 500 and 150 <= item["x"] <= 850
                  and valid_chat_name(item["text"]) and not item["text"].isdigit()
                  and item["text"] not in {"通讯录", "发现", "我"}]
    if not candidates:
        raise RuntimeError("找不到第一条置顶聊天")
    selected = min(candidates, key=lambda item: item["y"])
    tap(selected["x"], selected["y"])
    return chat_header(screenshot())


def inspect_cleanup_task(expected_label: str, expected_chat: str) -> dict:
    if not expected_label.startswith("#"):
        raise RuntimeError("缺少待恢复的剧名，未操作消息")
    restart_main_wechat()
    name = first_pinned_chat(screenshot())
    if valid_chat_name(expected_chat) and name != expected_chat:
        raise RuntimeError("置顶聊天与已记录聊天不一致，未恢复清理")
    image = screenshot()
    tags = sorted([item for item in ocr(image, CHAT_BOTTOM) if item["text"].strip().startswith("#")], key=lambda item:item["y"])
    if not tags or tags[-1]["text"].strip() != expected_label:
        raise RuntimeError("最后一个剧名与待恢复任务不一致，未恢复清理")
    areas = [area for area in card_areas(image) if area["top"] > tags[-1]["y"]]
    return {"chat_name":name, "task_label":expected_label, "label_only":not areas}


def active_pixel(rgb) -> bool:
    return max(rgb) - min(rgb) > 25 or min(rgb) < 190


def bottom_card_area(image):
    areas = card_areas(image)
    return areas[-1] if areas else None


def card_areas(image):
    pixels = image.load()
    x1, y1, x2, y2 = CHAT_SCAN
    xs = list(range(x1, x2, 4))
    threshold = max(25, len(xs) // 6)
    groups = []
    start = None
    gap = 0
    for y in range(y1, y2):
        count = sum(active_pixel(pixels[x, y]) for x in xs)
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
    areas = []
    for top, bottom in groups:
        height = max(1, bottom - top)
        columns = []
        col_start = None
        col_gap = 0
        for x in xs:
            count = sum(active_pixel(pixels[x, y]) for y in range(top, bottom, 4))
            if count >= max(8, height // 16):
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
                columns.append((col_start, end))
            col_start = None
            col_gap = 0
        if col_start is not None:
            columns.append((col_start, x2 - 1))
        if columns:
            left, right = max(columns, key=lambda pair: pair[1] - pair[0])
            areas.append({"x": (left + right) // 2, "y": (top + bottom) // 2, "top": top, "bottom": bottom})
    return areas


def read_task_from_image(image, chat_name: str) -> dict[str, object]:
    tags = [item for item in ocr(image, CHAT_BOTTOM) if item["text"].strip().startswith("#")]
    if not tags:
        raise RuntimeError("第一条置顶聊天中没有 #剧名")
    tags.sort(key=lambda item: item["y"])
    cards = card_areas(image)
    tasks = []
    unused_cards = list(cards)
    for index, tag in enumerate(tags):
        boundary = tags[index + 1]["y"] if index + 1 < len(tags) else image.height
        card = next((candidate for candidate in unused_cards if tag["y"] < candidate["top"] and candidate["bottom"] < boundary), None)
        if not card:
            continue
        unused_cards.remove(card)
        label = tag["text"].strip()
        tasks.append({
            "chat_name": chat_name,
            "task_label": label,
            "drama_name": re.sub(r"^#+", "", label).strip(),
            "label_position": {"x": tag["x"], "y": tag["y"]},
            "card_position": {"x": card["x"], "y": card["y"]},
        })
    if not tasks:
        raise RuntimeError("最后一个 #剧名下面没有找到视频卡片")
    if tasks[-1]["task_label"] != tags[-1]["text"].strip():
        raise RuntimeError("最后一个 #剧名下面没有找到完整卡片，未改读前一任务")
    task = tasks[-1]
    return {**task, "tasks": tasks, "task_count": len(tasks)}


def main_wechat_chat(expected_chat: str) -> bool:
    """只有已确认过的主微信聊天才能沿用当前屏幕。"""
    if not expected_chat or expected_chat == "当前聊天":
        return False
    activity = shell("dumpsys", "activity", "activities")
    focused = [line for line in activity.splitlines() if "ResumedActivity" in line or "topResumedActivity" in line]
    if not any(re.search(r"u0\s+com\.tencent\.mm/", line) for line in focused):
        return False
    try:
        return chat_header(screenshot()) == expected_chat
    except RuntimeError:
        return False


def read_task(expected_chat: str = "") -> dict[str, object]:
    if main_wechat_chat(expected_chat):
        try:
            task = read_task_from_image(screenshot(), expected_chat)
            task["read_source"] = "current_screen"
            print("TASK_SOURCE=current", flush=True)
            return task
        except RuntimeError:
            pass
    print("TASK_SOURCE=restart", flush=True)
    restart_main_wechat()
    chat_name = first_pinned_chat(screenshot())
    time.sleep(1.5)
    task = read_task_from_image(screenshot(), chat_name)
    task["read_source"] = "first_pinned_chat"
    return task


def delete_message_at(x: int, y: int) -> bool:
    # 长按文字中心会进入“文字选择”模式，菜单没有删除；优先长按气泡
    # 右侧空白处，失败后再尝试中心和左侧，兼容左右气泡及不同字号。
    candidates = [(x + 250, y), (x, y), (max(120, x - 180), y)]
    for target_x, target_y in candidates:
        shell("input", "tap", "1000", "1000")
        time.sleep(0.25)
        shell("input", "swipe", str(int(target_x)), str(int(target_y)), str(int(target_x)), str(int(target_y)), "800")
        time.sleep(0.8)
        items = ocr(screenshot(), CHAT_BOTTOM)
        delete = next((item for item in items if "删除" in item["text"]), None)
        if not delete:
            continue
        tap(delete["x"], delete["y"], wait=0.8)
        time.sleep(0.8)
        # Some WeChat builds ask for a second confirmation with another 删除 button.
        confirm_items = ocr(screenshot(), CHAT_BOTTOM)
        confirm = [item for item in confirm_items if "删除" in item["text"]]
        if confirm:
            tap(confirm[-1]["x"], confirm[-1]["y"], wait=1.0)
        return True
    shell("input", "tap", "1000", "1000")
    return False


def delete_current_task(expected_label: str, expected_chat: str, resume_label_only: bool = False) -> bool:
    if not expected_label.startswith("#") or not expected_chat or expected_chat == "当前聊天":
        raise RuntimeError("缺少已确认的聊天和剧名身份，未删除任何消息")
    restart_main_wechat()
    chat_name = first_pinned_chat(screenshot())
    if chat_name != expected_chat:
        raise RuntimeError("第一条置顶聊天已变化，未删除消息")
    image = screenshot()
    tags = sorted([item for item in ocr(image, CHAT_BOTTOM) if item["text"].strip().startswith("#")], key=lambda item: item["y"])
    if not tags or tags[-1]["text"].strip() != expected_label:
        raise RuntimeError("最后一个任务与本次下载任务不一致，未删除消息")
    try:
        task = read_task_from_image(image, chat_name)
    except RuntimeError:
        if not resume_label_only:
            raise RuntimeError("没有确认本次完整卡片，未删除消息")
        task = None
    if task:
        if task["task_label"] != expected_label:
            raise RuntimeError("待删除卡片不属于本次任务")
        card = task["card_position"]
        print("PROGRESS=" + json.dumps({"message":"正在删除本次任务卡片", "action":"cleanup_card_attempted"}, ensure_ascii=False), flush=True)
        if not delete_message_at(int(card["x"]), int(card["y"])):
            raise RuntimeError("任务卡片删除失败，已保留剧名")
        image = screenshot()
        if not main_wechat_chat(expected_chat):
            raise RuntimeError("删除后未确认回到本次聊天，已保留剧名，停止队列")
        remaining_tags = sorted([item for item in ocr(image, CHAT_BOTTOM) if item["text"].strip().startswith("#")], key=lambda item: item["y"])
        if not remaining_tags or remaining_tags[-1]["text"].strip() != expected_label:
            raise RuntimeError("删除后未重新确认本次剧名，停止队列")
        if any(area["top"] > remaining_tags[-1]["y"] for area in card_areas(image)):
            raise RuntimeError("卡片删除结果尚未确认，已保留剧名，停止队列")
    else:
        if any(area["top"] > tags[-1]["y"] for area in card_areas(image)):
            raise RuntimeError("恢复清理时仍发现卡片区域，未删除剧名")
    print("PROGRESS=" + json.dumps({"message": "本次任务卡片已清理，正在删除剧名标签", "action": "cleanup_card_removed"}, ensure_ascii=False), flush=True)
    image = screenshot()
    labels = [item for item in ocr(image, CHAT_BOTTOM) if item["text"].strip() == expected_label]
    if not labels:
        raise RuntimeError("没有找到本次任务的剧名标签，未改删其他消息")
    tag = max(labels, key=lambda item: item["y"])
    if not delete_message_at(int(tag["x"]), int(tag["y"])):
        raise RuntimeError("卡片已清理，但剧名删除失败；重新开始会先恢复清理")
    for _ in range(2):
        if not main_wechat_chat(expected_chat):
            raise RuntimeError("剧名删除后未确认回到本次聊天，停止队列")
        after = [item for item in ocr(screenshot(), CHAT_BOTTOM) if item["text"].strip() == expected_label]
        if len(after) >= len(labels):
            raise RuntimeError("剧名删除结果尚未确认，停止队列")
        time.sleep(0.4)
    return True


def argument(name: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else ""


def main() -> int:
    try:
        if "--inspect-cleanup" in sys.argv:
            print("CLEANUP_INSPECTION=" + json.dumps(inspect_cleanup_task(argument("--expected-label"), argument("--expected-chat")), ensure_ascii=False), flush=True)
        elif "--delete-current" in sys.argv:
            delete_current_task(argument("--expected-label"), argument("--expected-chat"), "--resume-label-only" in sys.argv)
            print("DELETE_RESULT=success", flush=True)
        else:
            print("TASK_JSON=" + json.dumps(read_task(argument("--expected-chat")), ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print("TASK_JSON=" + json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
