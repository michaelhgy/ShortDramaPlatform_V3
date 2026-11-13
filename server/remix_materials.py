"""原剧二创：把逐集识别结果整理成给模型判断的材料（本地，不调用模型）。

方法依据：docs/事项档案/2026-11-12-原剧二创选点方法.md 第 2 节。

- 每句台词编号，例如 E03-017（第3集第17句）。模型只回答编号，秒数由本程序换算，
  避免模型编造时间点。
- 去掉每集开头对上一集结尾的回顾，以及与前文完全重复的台词。
- 标出较长停顿和集末，供结尾判断参考。
"""
from __future__ import annotations

import re
from typing import Any

LONG_PAUSE_S = 1.2
RECAP_WINDOW_S = 40.0
RECAP_TAIL_LINES = 40

_PUNCT = re.compile(r"[\s，。！？、,.!?；;：:“”\"'…—\-~～]+")


def _norm(text: str) -> str:
    return _PUNCT.sub("", text)


def line_id(episode: int, index: int) -> str:
    return f"E{episode:02d}-{index:03d}"


def build_lines(transcripts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """transcripts: [{"episode": 1, "duration": 155.9, "segments": [{start,end,text}]}]，按集排序。

    返回保留下来的台词，每句含 id/episode/start/end/text/pause_after/episode_end。
    被判为回顾或重复的台词不出现在结果中。
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_tail: set[str] = set()
    for item in sorted(transcripts, key=lambda row: int(row["episode"])):
        episode = int(item["episode"])
        duration = float(item.get("duration") or 0)
        segments = [s for s in item.get("segments", []) if str(s.get("text", "")).strip()]
        episode_lines: list[dict[str, Any]] = []
        in_recap = True
        recap_end: float | None = None
        for segment in segments:
            text = str(segment["text"]).strip()
            key = _norm(text)
            if not key:
                continue  # 只有标点或空白的识别结果
            start, end = float(segment["start"]), float(segment["end"])
            if in_recap and start <= RECAP_WINDOW_S and key and key in previous_tail:
                recap_end = end
                continue  # 本集开头重复上一集结尾的回顾
            in_recap = False
            if len(key) >= 6 and key in seen:
                continue  # 与前文完全重复的长句（识别幻觉或回放）
            if key:
                seen.add(key)
            episode_lines.append({"episode": episode, "start": start, "end": end, "text": text})
        for index, line in enumerate(episode_lines, 1):
            line["id"] = line_id(episode, index)
            following = episode_lines[index] if index < len(episode_lines) else None
            gap = (following["start"] if following else duration) - line["end"]
            line["pause_after"] = round(max(gap, 0.0), 2)
            line["episode_end"] = following is None
        if episode_lines and recap_end is not None:
            episode_lines[0]["recap_end"] = recap_end  # 合成时从回顾之后开始播放
        kept.extend(episode_lines)
        previous_tail = {_norm(str(s["text"])) for s in segments[-RECAP_TAIL_LINES:]}
    return kept


def render_for_model(lines: list[dict[str, Any]]) -> str:
    """紧凑文本：每行 `E01-012 [停] 台词`，[停]=之后停顿较长，[集末]=本集最后一句。"""
    rows: list[str] = []
    current = None
    for line in lines:
        if line["episode"] != current:
            current = line["episode"]
            rows.append(f"## 第{current}集")
        marks = ""
        if line["episode_end"]:
            marks = " [集末]"
        elif line["pause_after"] >= LONG_PAUSE_S:
            marks = " [停]"
        rows.append(f"{line['id']}{marks} {line['text']}")
    return "\n".join(rows)


def index_by_id(lines: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {line["id"]: line for line in lines}
