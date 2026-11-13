# -*- coding: utf-8 -*-
r"""
读手机输入法的剪贴板历史 —— 代替"切到设置粘贴再读"那套笨办法

原理：
  安卓 10 以后禁止后台读剪贴板，但【输入法】有权限。
  搜狗输入法把每一条复制的内容写进它自己的数据库：
      /data/data/com.sohu.inputmethod.sogouoem/databases/clipboard_db
  表 CLIPBOARD_ITEM：TIME(毫秒时间戳) / CONTENT(内容)
  有 root 就能直接把整个库拉出来读 —— 一次读几百条都行。

用法：
  python 读剪贴板历史.py                    # 列出最近的记录
  python 读剪贴板历史.py --links            # 只列分享链接
  python 读剪贴板历史.py --urls             # 只列下载地址
  python 读剪贴板历史.py --since 19:20      # 只看这个时间之后的
  python 读剪贴板历史.py --append 链接清单.txt   # 把新链接追加到文件
"""
import argparse
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

TMP = Path(r"D:\sd_probe")

# —— 支持两个输入法（安卓 10+ 禁止后台读剪贴板，但输入法有权限，会把历史写进自己的库）——
# 微信输入法（当前在用）
WX_DB = "/data/data/com.tencent.wetype/databases/ime_database"
WX_COL_TIME, WX_COL_TEXT = "createTime", "content"
# 搜狗输入法（备用）
SG_DB = "/data/data/com.sohu.inputmethod.sogouoem/databases/clipboard_db"
DB_BAIDU = "/data/data/com.baidu.input_oppo/databases/clipborad_records.db"

IME_PATHS = [("微信输入法", WX_DB), ("搜狗输入法", SG_DB), ("百度输入法", DB_BAIDU)]

RE_SHARE = re.compile(r"https?://weixin\.qq\.com/sph/[A-Za-z0-9_\-]+")
RE_VIDEO = re.compile(r"https://51\.wxapp\.tc\.qq\.com/[^\s\"'<>]+|https?://[^\s\"'<>]*stodownload[^\s\"'<>]*")


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


def sh(*args, timeout=90) -> str:
    r = subprocess.run([ADB, "shell", *args], capture_output=True, timeout=timeout)
    return (r.stdout or b"").decode("utf-8", "ignore")


def fetch_db(remote: str = "", tag: str = "clip") -> Path | None:
    """把输入法的剪贴板库拉到电脑（微信输入法有 -wal，要一起拉，否则读不到最新数据）"""
    TMP.mkdir(parents=True, exist_ok=True)
    remotes = [remote] if remote else [p for _n, p in IME_PATHS]
    for rem in remotes:
        for suffix in ("", "-wal", "-shm"):
            src = rem + suffix
            dst = f"/sdcard/Download/_cb{suffix}"
            local = TMP / f"{tag}{suffix}"
            if local.exists():
                local.unlink()
            sh("su", "-c", f"cp '{src}' {dst} 2>/dev/null; chmod 666 {dst} 2>/dev/null")
            subprocess.run([ADB, "pull", dst, str(local)], capture_output=True, timeout=120)
            sh("su", "-c", f"rm -f {dst}")
        base = TMP / tag
        if base.exists() and base.stat().st_size > 0:
            return base
    return None


def current_ime_db():
    """只读【当前正在用的】输入法的库 —— 快得多，不用遍历三个"""
    cur = sh("su", "-c", "settings get secure default_input_method")
    if "wetype" in cur:
        return fetch_db(WX_DB, "cur")
    if "sogou" in cur:
        return fetch_db(SG_DB, "cur")
    if "baidu" in cur:
        return fetch_db(DB_BAIDU, "cur")
    return auto_db()


def newest_share(fetch=True):
    """拿剪贴板历史里最新的一条分享链接（阶段1 每轮用它确认复制到了什么）"""
    db = current_ime_db() if fetch else None
    if not db:
        return ""
    for _t, c in reversed(read_items(db)):
        m = RE_SHARE.search(c)
        if m:
            return m.group(0)
    return ""


def auto_db() -> Path | None:
    """自动挑【最新数据】的那个输入法库（用户在哪个输入法里复制，数据就在哪）
    ⚠️ 每个输入法要用不同的临时文件名，否则会互相覆盖"""
    best, best_ts = None, -1
    for idx, (name, path) in enumerate(IME_PATHS):
        db = fetch_db(path, f"clip{idx}")
        if not db:
            continue
        try:
            items = read_items(db)
        except Exception:
            continue
        if items and items[-1][0] > best_ts:
            best, best_ts = db, items[-1][0]
    return best


def auto_db_tail(path=None, n=3):
    """返回 (库路径, 最新 n 条)"""
    db = Path(path) if path else auto_db()
    if not db:
        return None, []
    return db, read_items(db)[-n:]


def read_items(db_path: Path):
    """返回 [(时间戳毫秒, 内容)]，按时间正序。自动适配不同输入法的表结构"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    t = None
    for cand in ("clipboard_record", "CLIPBOARD_ITEM"):
        if cand in tables:
            t = cand
            break
    if t is None:
        con.close()
        return []
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    tcol = "createTime" if "createTime" in cols else ("TIME" if "TIME" in cols else cols[1])
    ccol = "content" if "content" in cols else ("CONTENT" if "CONTENT" in cols else cols[2])
    rows = list(cur.execute(f"select {tcol}, {ccol} from [{t}] order by {tcol} asc"))
    con.close()
    return [(int(r[0]), (r[1] or "").strip()) for r in rows if r[1]]


def hhmm(ms: int) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ms / 1000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", action="store_true", help="只列分享链接")
    ap.add_argument("--urls", action="store_true", help="只列下载地址")
    ap.add_argument("--since", default="", help="只看这个时间之后，如 19:20")
    ap.add_argument("--append", default="", help="把新链接追加到这个文件")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = fetch_db() or fetch_db(DB_BAIDU)
    if not db:
        print("❌ 拉不到输入法的剪贴板库。确认手机连着、root 可用。")
        return
    items = read_items(db)
    print(f"共读到 {len(items)} 条剪贴板记录（{db}）\n")

    if args.since:
        h, m = args.since.split(":")[:2]
        today = time.strftime("%Y-%m-%d")
        cut = time.mktime(time.strptime(f"{today} {h}:{m}:00", "%Y-%m-%d %H:%M:%S")) * 1000
        items = [i for i in items if i[0] >= cut]

    shares, urls = [], []
    for ts, content in items:
        if RE_SHARE.search(content):
            shares.append((ts, RE_SHARE.search(content).group(0)))
        elif RE_VIDEO.search(content):
            urls.append((ts, RE_VIDEO.search(content).group(0)))

    if args.links or args.append:
        out = [s for _, s in shares]
        if args.append:
            f = Path(args.append)
            old = {l.strip() for l in f.read_text(encoding="utf-8").splitlines()} if f.exists() else set()
            new = [u for u in out if u not in old]
            with f.open("a", encoding="utf-8") as fp:
                for u in new:
                    fp.write(u + "\n")
            print(f"分享链接 {len(out)} 条，其中新的 {len(new)} 条已追加到 {f}")
        else:
            for ts, s in shares:
                print(f"  {hhmm(ts)}  {s}")
        return

    if args.urls:
        for ts, u in urls:
            print(f"  {hhmm(ts)}  {u[:150]}")
        return

    for ts, c in items[-args.limit if args.limit else -30:]:
        tag = "分享链接" if RE_SHARE.search(c) else ("下载地址" if RE_VIDEO.search(c) else "其它")
        print(f"  {hhmm(ts)}  [{tag}]  {c[:110]}")


if __name__ == "__main__":
    main()
