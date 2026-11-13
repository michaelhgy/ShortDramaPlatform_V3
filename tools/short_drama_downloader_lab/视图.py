# -*- coding: utf-8 -*-
r"""
「看屏幕找元素」的公共层 —— 不再写死坐标

原理：每次截图 → OCR 认出屏幕上所有文字和它们的位置 → 按文字找元素 → 点它的中心。
好处：界面上元素挪位置、剧名长短变化、集数增减，都不影响。

用法：
    import 视图 as V
    V.refresh()                 # 重新看一眼屏幕（OCR 一次，结果缓存）
    V.tap_text("文件传输助手")   # 找到就点它的中心
    V.find("开始去水印")         # 只找不点
    V.wait_text("复制链接", 20)  # 等它出现
"""
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TMP = Path(r"D:\sd_probe")
_ENGINE = None
_ITEMS = None


def find_adb() -> str:
    p = shutil.which("adb")
    if p:
        return p
    for c in (Path.home() / "AppData/Local/Microsoft/WinGet/Links/adb.exe",
              *Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools*/**/adb.exe")):
        if c.exists():
            return str(c)
    sys.exit("找不到 adb.exe")


ADB = find_adb()


def sh(*args, timeout=90, root=False) -> str:
    """在【设备上】执行命令（等价于 adb shell ...）"""
    cmd = [ADB, "shell"]
    if root:
        cmd += ["su", "-c", " ".join(str(a) for a in args)]
    else:
        cmd += [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return (r.stdout or b"").decode("utf-8", "ignore")


def adb(*args, timeout=90) -> str:
    """执行【adb 自己的】命令（reverse / forward / devices / pull …）
    ⚠️ 不能加 shell —— reverse 是 adb 的命令，不是设备上的命令"""
    r = subprocess.run([ADB] + [str(a) for a in args], capture_output=True, timeout=timeout)
    return (r.stdout or b"").decode("utf-8", "ignore").strip()


def screenshot(name="v.png", tries=3):
    """截屏并返回 PIL Image
    ⚠️ adb pull 偶尔会拉到不完整的文件（0 字节 / 截断），必须校验并重试，
       否则 PIL 会抛 "image file is truncated" 直接把脚本搞崩。"""
    from PIL import Image
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / name
    last = None
    for attempt in range(1, tries + 1):
        attempt_path = p.with_name(f"{p.stem}.{attempt}{p.suffix}")
        try:
            # 直接通过 exec-out 取 PNG，避免先写手机文件再 pull 时读到半截文件。
            result = subprocess.run(
                [ADB, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0 or len(result.stdout) < 10000:
                last = f"截图返回异常：code={result.returncode} bytes={len(result.stdout)}"
                time.sleep(0.4)
                continue
            attempt_path.write_bytes(result.stdout)
            im = Image.open(attempt_path)
            im.load()                      # 真正解码一遍，截断的会在这里报错
            attempt_path.replace(p)
            return im.convert("RGB")
        except Exception as e:
            last = str(e)[:80]
            attempt_path.unlink(missing_ok=True)
            time.sleep(0.5)
    raise RuntimeError(f"截图连续 {tries} 次失败：{last}")


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def refresh(crop=None, img=None):
    """重新 OCR 一次当前屏幕；结果缓存起来给 find/tap_text 用"""
    global _ITEMS
    im = img if img is not None else screenshot()
    if crop:
        im = im.crop(crop)
        ox, oy = crop[0], crop[1]
    else:
        ox, oy = 0, 0
    res, _ = _engine()(im)
    items = []
    for box, text, score in (res or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({
            "text": text.replace(" ", ""),
            "raw": text,
            "x": int(sum(xs) / 4) + ox,
            "y": int(sum(ys) / 4) + oy,
            "score": float(score),
            "box": (int(min(xs)) + ox, int(min(ys)) + oy, int(max(xs)) + ox, int(max(ys)) + oy),
        })
    _ITEMS = items
    return items


def items():
    return list(_ITEMS or [])


def refresh_multi(boxes):
    """⚠️ 性能关键：只截一次屏，在内存里裁成多块分别 OCR。
    比"每块各截一次屏"快好几倍（截屏本身走 adb，很贵）。
    返回所有块合起来的元素列表（坐标已还原到整屏）。"""
    img = screenshot()
    out = []
    eng = _engine()
    for box in boxes:
        x1, y1, x2, y2 = box
        crop = img.crop((x1, y1, x2, y2))
        res, _ = eng(crop)
        for b, text, score in (res or []):
            xs = [p[0] for p in b]
            ys = [p[1] for p in b]
            out.append({
                "text": text.replace(" ", ""),
                "raw": text,
                "x": int(sum(xs) / 4) + x1,
                "y": int(sum(ys) / 4) + y1,
                "score": float(score),
                "box": (int(min(xs)) + x1, int(min(ys)) + y1, int(max(xs)) + x1, int(max(ys)) + y1),
            })
    global _ITEMS
    _ITEMS = out
    return out


def find(*keys, exact=False):
    """在缓存的 OCR 结果里找元素，返回 (x, y, 文字) 或 None。
    先找完全相等的，再退回包含匹配。"""
    its = items()
    for it in its:
        for k in keys:
            if (it["text"] == k) if exact else (k in it["text"]):
                return it["x"], it["y"], it["text"]
    return None


def in_region(region, *keys, exclude_time=True, min_len=1, exact=False):
    """⚠️ 性能关键：不重新截图，直接从【已缓存的】整屏 OCR 结果里，
    按区域过滤出目标 —— 一屏只 OCR 一次，多个元素共用"""
    x1, y1, x2, y2 = region
    for it in items():
        if not (x1 <= it["x"] <= x2 and y1 <= it["y"] <= y2):
            continue
        if exclude_time and RE_TIME.match(it["text"]):
            continue
        if len(it["text"]) < min_len:
            continue
        for k in keys:
            if (it["text"] == k) if exact else (k in it["text"]):
                return it
    return None


def lowest_in_region(region, min_len=3, exclude_time=True):
    """区域内 y 最大的那条（= 最下面那条消息）"""
    x1, y1, x2, y2 = region
    cands = [i for i in items()
             if x1 <= i["x"] <= x2 and y1 <= i["y"] <= y2
             and len(i["text"]) >= min_len
             and not (exclude_time and RE_TIME.match(i["text"]))]
    return max(cands, key=lambda i: i["y"]) if cands else None


def all_in_region(region, exclude_time=True, min_len=1):
    x1, y1, x2, y2 = region
    return [i for i in items()
            if x1 <= i["x"] <= x2 and y1 <= i["y"] <= y2
            and len(i["text"]) >= min_len
            and not (exclude_time and RE_TIME.match(i["text"]))]


RE_TIME = __import__("re").compile(r"^\d{1,2}[:：]\d{2}$")


def find_all(*keys):
    out = []
    for it in items():
        for k in keys:
            if k in it["text"]:
                out.append(it)
                break
    return out


def tap_xy(x, y, wait=1.0):
    sh("input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)


def tap_text(*keys, wait=1.2, fresh=False, must=True):
    """找到文字就点它的中心；找不到返回 False"""
    if fresh or _ITEMS is None:
        refresh()
    hit = find(*keys)
    if not hit:
        if must:
            print(f"      ⚠️ 屏幕上找不到「{keys[0]}」")
        return False
    x, y, t = hit
    tap_xy(x, y, wait)
    return True


def wait_text(*keys, timeout=20, interval=1.2, fresh=True):
    """等某段文字出现，返回 (x,y,文字) 或 None"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fresh:
            refresh()
        hit = find(*keys)
        if hit:
            return hit
        time.sleep(interval)
    return None


def swipe(x1, y1, x2, y2, ms=350, wait=1.0):
    sh("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))
    time.sleep(wait)


def key(code, wait=0.8):
    sh("input", "keyevent", str(code))
    time.sleep(wait)


def foreground() -> str:
    out = sh("dumpsys", "activity", "activities")
    m = re.search(r"topResumedActivity.*?\s([\w\.]+/[\w\.]+)", out)
    return m.group(1) if m else ""


def dump(limit=25):
    """调试用：打印当前屏幕认到的文字"""
    for it in items()[:limit]:
        print(f"   「{it['text'][:40]}」 ({it['x']},{it['y']}) {it['score']:.2f}")


if __name__ == "__main__":
    refresh()
    print(f"当前前台: {foreground()}")
    print(f"认到 {len(items())} 段文字：")
    dump(40)
