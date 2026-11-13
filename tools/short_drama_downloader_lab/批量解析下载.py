# -*- coding: utf-8 -*-
"""V3 原片下载执行步骤：接收软件逐集计划，后台解析并安全保存视频。"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from server.drama_download_state import fingerprint, probe_video, receipt_matches, VideoValidationError


def progress(message: str, *, keep: bool = True, **details) -> None:
    """Send operator-facing progress without links or credentials."""
    print("PROGRESS=" + json.dumps({"message": message, "keep": keep, **details}, ensure_ascii=False), flush=True)


def load_config() -> dict:
    return json.loads((HERE / "配置.json").read_text(encoding="utf-8"))

def load_links(path: Path, limit: int = 0) -> list[dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].startswith("http"):
            rows.append({"drama": parts[0].strip(), "episode": parts[1].strip(), "link": parts[2].strip()})
    return rows[:limit] if limit else rows

def analyse(cfg: dict, link: str) -> dict:
    body = json.dumps({"uid": cfg["uid"], "baseurl": link, "rawtext": link, "agentid": cfg["agentid"]}, ensure_ascii=False).encode()
    req = urllib.request.Request(cfg["analysis_api"], data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=cfg.get("download_timeout_seconds", 180)) as response:
        result = json.loads(response.read().decode("utf-8", "ignore"))
    if result.get("code") != 1 or not (result.get("data") or {}).get("url"):
        raise RuntimeError(f"解析失败：{result.get('msg') or result.get('message') or result.get('code')}")
    return result

def episode_number(text: str, fallback: str) -> str:
    match = re.search(r"第\s*(\d+)\s*集", text) or re.search(r"(\d+)", fallback)
    return (match.group(1) if match else fallback).zfill(3)


def numeric_episode(text: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*集", text or "")
    return int(match.group(1)) if match else None

class EpisodeFailure(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def download(url: str, target: Path, timeout: int, on_progress=None, validate=None, replace_invalid=False) -> int:
    """先下载临时文件；长度和视频检查通过后才提交正式文件。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    original = fingerprint(target) if target.exists() else None
    temporary = target.with_name(target.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "MicroMessenger Client", "Accept": "*/*", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as response, temporary.open("wb") as stream:
        total = 0
        content_length = response.headers.get("Content-Length", "")
        expected = int(content_length) if content_length.isdigit() else 0
        last_report = time.monotonic()
        if on_progress:
            on_progress(total, expected)
        while chunk := response.read(256 * 1024):
            stream.write(chunk)
            total += len(chunk)
            if on_progress and time.monotonic() - last_report >= 1:
                on_progress(total, expected)
                last_report = time.monotonic()
        if on_progress:
            on_progress(total, expected)
    if total < 100_000 or (expected and total != expected):
        raise EpisodeFailure("download", f"文件未完整接收：{total}/{expected or '未知'} bytes")
    if validate:
        validate(temporary)
    if target.exists():
        if not replace_invalid or original != fingerprint(target):
            raise EpisodeFailure("file_conflict", f"目标文件已存在，已保留原文件和新临时文件：{target.name}")
        # 只修复本软件有逐集归属记录、且已证实损坏的下载；原字节另存后才替换。
        backup = target.with_name(target.name + ".before-repair-" + uuid.uuid4().hex[:8])
        shutil.copy2(target, backup)
        if original != fingerprint(target):
            raise EpisodeFailure("file_conflict", "修复期间文件发生变化，未替换原文件")
        os.replace(temporary, target)
    else:
        temporary.rename(target)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="采集表.txt")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--drama", default="")
    parser.add_argument("--theater", default="")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--result-path", type=Path, default=None)
    parser.add_argument("--log-path", type=Path, default=None)
    parser.add_argument("--resume-records", type=Path)
    parser.add_argument("--episodes", default="")
    args = parser.parse_args()
    cfg = load_config()
    table = HERE / args.table
    if not table.exists():
        print(f"找不到采集表：{table}")
        return 2
    rows = load_links(table)
    if args.drama:
        rows = [row for row in rows if row["drama"] == args.drama]
    if args.episodes:
        selected = {int(value) for value in re.findall(r"\d+", args.episodes)}
        rows = [row for row in rows if int(re.search(r"\d+", row["episode"]).group()) in selected]
    # 兼容历史重复行，但同一集只处理最后一条。
    rows = list({(row["drama"], row["episode"]): row for row in rows}.values())
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print("采集表中没有可处理的短链")
        return 2
    root = args.output_root or (HERE / cfg.get("download_root", "原片"))
    result_path = args.result_path or (HERE / "解析结果.jsonl")
    log_path = args.log_path or (HERE / "下载记录.log")
    receipts = json.loads(args.resume_records.read_text(encoding="utf-8")).get("episodes", {}) if args.resume_records else {}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ok = failed = 0
    with result_path.open("a", encoding="utf-8") as results, log_path.open("a", encoding="utf-8") as log:
        for index, row in enumerate(rows, 1):
            episode = int(re.search(r"\d+", row["episode"]).group())
            receipt = receipts.get(str(episode), {})
            stage = "parse"
            title, returned_episode = "", None
            try:
                target = root / args.theater / row["drama"] / f"{row['drama']}-第{episode:03d}集.mp4"
                if receipt_matches(receipt, target, row["link"]):
                    record = {**receipt, "status": "ok", "skipped": True}
                    progress(f"第{episode}集已下载并校验，跳过重复处理", episode=episode, action="skipped")
                else:
                    data = None
                    for attempt in range(1, 4):
                        progress(f"正在解析第{episode}集（本轮第{index}/{len(rows)}条，第{attempt}/3次），等待接口返回", episode=episode, action="parse")
                        try:
                            data = analyse(cfg, row["link"])["data"]
                            break
                        except (OSError, urllib.error.URLError, ValueError):
                            if attempt == 3:
                                raise
                            progress(f"第{episode}集解析连接中断，正在重试这一条", episode=episode, action="retry")
                            time.sleep(1)
                    title = str(data.get("title") or "")
                    returned_episode = numeric_episode(title)
                    progress(f"第{episode}集解析返回名称：{title or '未提供名称'}", episode=episode, action="parsed", title=title, returned_episode=returned_episode)
                    if returned_episode is not None and returned_episode != episode:
                        raise EpisodeFailure("link_mismatch", f"采集表为第{episode}集，解析返回第{returned_episode}集")
                    phone_confirmed = receipt.get("link") == row["link"] and receipt.get("link_confirmed") is True
                    if returned_episode is None and not phone_confirmed:
                        raise EpisodeFailure("episode_unknown", "解析名称没有集数，手机采集也未确认集数，不能按推算编号下载")
                    replace_invalid = False
                    if target.exists():
                        owned = receipt.get("managed_by") == "v3-drama-download" and receipt.get("file") == str(target) and receipt.get("link") == row["link"]
                        if owned:
                            try:
                                probe_video(target)
                            except VideoValidationError:
                                replace_invalid = True
                        if not replace_invalid:
                            raise EpisodeFailure("file_conflict", f"已有同名视频但不能确认需要替换，已保留：{target.name}")
                    stage = "download"
                    size = 0
                    for attempt in range(1, 4):
                        progress(f"正在连接第{episode}集的视频地址（第{attempt}/3次）", episode=episode, action="connect")
                        def report(received, expected):
                            amount = f"{received / 1024 / 1024:.1f} MB"
                            if expected:
                                amount += f" / {expected / 1024 / 1024:.1f} MB（{min(100, received * 100 / expected):.0f}%）"
                            progress(f"正在下载第{episode}集：已接收 {amount}", keep=False, episode=episode, action="download", bytes=received, total_bytes=expected)
                        try:
                            size = download(str(data["url"]), target, int(cfg.get("download_timeout_seconds", 180)), report, probe_video, replace_invalid=replace_invalid)
                            break
                        except (OSError, urllib.error.URLError):
                            if attempt == 3:
                                raise
                            progress(f"第{episode}集传输中断，保留正式视频，正在重试下载", episode=episode, action="retry")
                            time.sleep(1)
                    record = {"status": "ok", "managed_by": "v3-drama-download", "drama": row["drama"], "theater": args.theater,
                        "episode": episode, "expected_episode": episode, "returned_episode": returned_episode,
                        "confirmation_source": "parser" if returned_episode else "phone", "title": title,
                        "link": row["link"], "link_confirmed": phone_confirmed, "file": str(target),
                        "verified": True, **fingerprint(target)}
                    progress(f"第{episode}集下载完成，视频轨道和时长检查通过：{size / 1024 / 1024:.1f} MB", episode=episode, action="saved")
                message, ok = f"[{index}/{len(rows)}] OK {title or row['episode']} {record['bytes']} bytes", ok + 1
            except (OSError, urllib.error.URLError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                kind = getattr(exc, "kind", stage)
                progress(f"第{episode}集处理失败：{exc}", episode=episode, action="error")
                record = {"status": "error", "drama": row["drama"], "theater": args.theater,
                    "episode": episode, "expected_episode": episode, "returned_episode": returned_episode,
                    "title": title, "link": row["link"], "failure_kind": kind, "error": str(exc)}
                message, failed = f"[{index}/{len(rows)}] ERROR 第{episode}集 {exc}", failed + 1
            results.write(json.dumps(record, ensure_ascii=False) + "\n")
            results.flush()
            print("EPISODE_RESULT=" + json.dumps(record, ensure_ascii=False), flush=True)
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{message}\n")
            log.flush()
            print(message, flush=True)
            time.sleep(float(cfg.get("request_interval_seconds", 0.7)))
    print(f"完成：成功 {ok}，失败 {failed}，输出目录：{root}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
