"""原剧二创：选点方法（剧情地图 → 本地组合 → 逐条复核）。

方法依据：docs/事项档案/2026-11-12-原剧二创选点方法.md。
本模块不依赖 V3 其他模块；模型调用通过参数传入，便于测试和替换。

优化方法时修改本文件中的提示词/规则，并提升 METHOD_VERSION，
软件会按新版本重新生成剧情地图（旧版本地图保留，不覆盖）。
"""
from __future__ import annotations

import random
from typing import Any, Callable

from .remix_materials import index_by_id, render_for_model

METHOD_VERSION = "2026-11-12.3"

ModelCall = Callable[[str, str, dict[str, Any], str], dict[str, Any]]
"""call(task_role, prompt, schema, schema_name) -> {"data": {...}, "usage": {...}, "model": str, "elapsed_s": float}"""

END_TYPES = ("告一段落", "悬念")
CUT_IN_PAD_S = 0.3
CUT_OUT_PAD_S = 0.6
CLIP_END_PAD_S = 1.0

# 跳集放量（2026-11-12）：同一个高光枚举多种跳法组合，每种一条差异视频。
MAX_JUMP_PER_HIGHLIGHT = 8   # 每个高光最多产出几条跳集候选（成本闸，出片不够再调）
MAX_SKIPS_PER_VARIANT = 3    # 一条跳集最多跳几处（拼接点控制在 2—4 个之内）


# ---------------------------------------------------------------------------
# 第二至五步：剧情地图（一次模型调用）
# ---------------------------------------------------------------------------

STORY_MAP_PROMPT = """你是短剧推广视频的剪辑策划。我们要从一部短剧原片里，自动剪出 5—10 分钟的推广视频，发到视频号，引导观众点链接看全剧。
视频保留原声原画面，不加旁白。你的任务是读完全部台词，产出一张"剧情地图"，后续由程序按这张地图自动组合成片。

# 材料说明
- 每行格式：`编号 [标记] 台词`。编号如 E03-017 表示第3集第17句。
- [停] 表示这句之后有较长停顿；[集末] 表示本集最后一句。
- 台词由语音识别得到，可能有错别字、同音字或人名不统一，按上下文理解，不要因为错字误判剧情。
- 所有回答只能引用材料中真实存在的编号，不能编造编号，不要回答秒数。

# 第一步：读懂全剧
写出主要人物（每人一句：身份和与主角的关系）、每集一句话剧情、主线冲突。
主线冲突指贯穿多集、观众最关心结果的矛盾（例如"女主被家人抢走婚约""开店被同行打压"）。为每条主线冲突标出：开始的编号、最激烈的编号、有结果的编号（材料内没有结果则填空字符串）。

# 第二步：找高光起点（视频的第一句）
在主线冲突上找视频开头。好开头能让刷到视频、没看过这部剧的观众 3 秒内被抓住并看懂。
每个候选逐项判断：
1. cold_start_ok：零前情能懂——没看过前面的观众，3 秒内能看懂谁和谁在冲突、为什么冲突。
2. strong_action：有强动作或强表态——命令、威胁、指控、当场揭穿、明确的利害。
3. visual_conflict：有画面对抗——台词暗示画面上有对峙、动手、摔东西、拦人、抓现行、当众羞辱。
4. excluded_type：如果属于以下任一类型，填写类型名；都不属于填"无"：
   感悟（"原来…""我才明白…"）、寒暄、道歉、泛泛提问（"你到底想说什么？"）、假设（"如果有一天…"）、需要前情才懂的身份揭晓（"原来你就是…"）、旁白式自我介绍或回忆铺垫。
前三项至少满足两项，并且 excluded_type 为"无"，才算合格起点。不合格的不要列出。

要求：
- 起点编号是视频的第一句台词，必须是冲突爆发的那一句或紧挨着的前一句，不要从冲突前的铺垫开始。
- 选 {highlight_target} 个合格起点（材料不足时宁缺毋滥），分布在不同的主线冲突或不同的冲突回合上，同一场戏只选一个。
- 每集开头重复上一集结尾的回顾内容不能当起点，只选第一次真实发生的位置。
- 按推荐强度从强到弱排列。
- viewer_question：观众看完开头最想知道什么（例如"她会不会被逼嫁？"）。

参考——合格起点示例：
- "顾家亲事是祖母为我定下的，你怎么能强夺"：零前情就懂（婚事被抢）、有强指控、暗示当面对峙。
- "姐姐，就你这副鬼样子还想开铺子"：当众羞辱、利害明确、画面对抗强。
- "你不嫁也得嫁"：强命令、利害明确。
参考——不合格起点示例：
- "原来承认错误也可以是一种力量"：感悟，没有冲突。
- "阿姨，原来你叫某某"：身份揭晓依赖前情，冷启动看不懂。
- "对不起，沈阿姨" / "顾老师您好"：道歉、寒暄。
- "你到底想说什么？"：泛泛提问。

# 第三步：标结束点（视频的最后一句）
在全剧范围内标出适合作为推广视频最后一句的位置，分两类：
- 告一段落：这一轮冲突有了结果（打脸完成、真相揭开、决定做出、危机解除），观众看完不觉得被掐断。
- 悬念：新冲突刚刚冒头、最想知道下一步的时刻（新人物到来、威胁刚说出口、秘密即将曝光），观众会想点链接看后续。
不能作为结束点的位置：话没说完、问了还没答、动作做到一半、情绪正在爆发中途。
结束点优先选带 [停] 或 [集末] 标记的句子。每集标 1—3 个，两类都要有。

# 台词材料
{material}
"""


SKIPPABLE_PROMPT = """你是短剧推广视频的剪辑策划。我们要把一部短剧剪成"跳集版"推广视频：从一个高光起点开始，跳过中间一些可有可无的段落，让节奏更紧、并产出多条有差异的视频。
你的任务是读完全部台词，标出"删掉后不影响观众理解后文"的连续台词段，供程序组合。

# 材料说明
- 每行格式：`编号 [标记] 台词`。编号如 E03-017 表示第3集第17句。
- [停] 表示这句之后有较长停顿；[集末] 表示本集最后一句。
- 台词由语音识别得到，可能有错别字、人名不统一，按上下文理解。
- 只能引用材料中真实存在的编号，不要编造，不要回答秒数。

# 已选中的高光起点（跳集会从这些位置之一开始播，可跳段要落在它们之后的剧情里）
{highlights}

# 任务：尽量多标可跳过段
跳集版靠"跳过不同的段"产出多条有差异的视频，所以要**尽量多地**标出可以删掉的连续台词段，覆盖全剧各处，不要只标一两个。
候选对象：过渡、支线、重复解释、走位寒暄、可有可无的闲聊、与主线关系不大的插曲。每段逐项判断：
- what：跳过的是什么。
- used_later：后文是否明确用到其中的信息（人物关系、动机、关键道具、问题的提出）。用到了填 true。
- resume_clear：跳过之后，接上的第一句能否让观众明白时间或场景变了。
硬规则（这几类绝不能标为可跳）：不能删掉问题而留下回答；不能删掉铺垫而留下结果；不能把一个连续动作切成两半；不能删掉新人物登场却保留他后面的戏。
除上述硬规则外，**宁可多标**：只要删掉后主线大体连得上就列出，每段如实填写 used_later 和 resume_clear，拿不准时据实标注即可，后续会有专门的逐条复核再把关，不必在这一步过度保守。
数量目标：标 20—40 段，分布在不同集、不同剧情处。每段长度建议 20 秒到 3 分钟的台词量。

# 台词材料
{material}
"""


def _story_map_schema() -> dict[str, Any]:
    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}

    s = {"type": "string"}
    b = {"type": "boolean"}
    return obj({
        "characters": {"type": "array", "items": obj({"name": s, "role": s})},
        "episodes": {"type": "array", "items": obj({"episode": {"type": "integer"}, "summary": s})},
        "conflicts": {"type": "array", "items": obj({
            "id": s, "title": s, "start_line": s, "peak_line": s, "result_line": s,
        })},
        "highlights": {"type": "array", "items": obj({
            "start_line": s, "conflict_id": s, "hook_label": s,
            "cold_start_ok": b, "strong_action": b, "visual_conflict": b, "excluded_type": s,
            "viewer_question": s, "reason": s,
        })},
        "end_points": {"type": "array", "items": obj({
            "line": s, "type": {"type": "string", "enum": list(END_TYPES)}, "reason": s,
        })},
    })


def _skippable_schema() -> dict[str, Any]:
    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}

    s = {"type": "string"}
    b = {"type": "boolean"}
    return obj({
        "skippable": {"type": "array", "items": obj({
            "from_line": s, "to_line": s, "what": s, "used_later": b, "resume_clear": b, "reason": s,
        })},
    })


def highlight_target(episode_count: int) -> int:
    return max(4, min(15, round(episode_count * 0.3)))


def build_story_map(lines: list[dict[str, Any]], call: ModelCall) -> dict[str, Any]:
    """生成剧情地图，分两次模型调用以免单次输出过大撞超时（2026-11-12.3）：
    第一次选高光起点与结束点；第二次把已选高光喂回去，专门标可跳过段。两次结果合并清洗。
    """
    episodes = sorted({line["episode"] for line in lines})
    material = render_for_model(lines)

    # 第一次：选点（高光起点 + 结束点，不含可跳段，输出较小）
    prompt = STORY_MAP_PROMPT.format(
        highlight_target=highlight_target(len(episodes)),
        material=material,
    )
    response = call("highlight", prompt, _story_map_schema(), "short_drama_story_map")
    raw = dict(response.get("data") or {})

    # 第二次：标可跳段（仅当选出了高光才做跳集供给；把已选高光列给模型作范围参考）
    story_map = clean_story_map(raw, lines)
    model_calls = [{k: response.get(k) for k in ("model", "usage", "elapsed_s")}]
    if story_map["highlights"]:
        highlight_brief = "\n".join(
            f"- {h['start_line']}：{h.get('hook_label', '')}" for h in story_map["highlights"]
        )
        skip_prompt = SKIPPABLE_PROMPT.format(highlights=highlight_brief, material=material)
        skip_response = call("skippable", skip_prompt, _skippable_schema(), "short_drama_skippable")
        raw["skippable"] = (skip_response.get("data") or {}).get("skippable") or []
        story_map = clean_story_map(raw, lines)
        model_calls.append({k: skip_response.get(k) for k in ("model", "usage", "elapsed_s")})

    story_map["method_version"] = METHOD_VERSION
    story_map["model_call"] = model_calls[0]
    story_map["model_calls"] = model_calls
    return story_map


def clean_story_map(raw: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    ids = index_by_id(lines)
    order = {line["id"]: pos for pos, line in enumerate(lines)}
    rejected: list[str] = []

    highlights = []
    seen_starts: set[str] = set()
    for item in raw.get("highlights") or []:
        start = str(item.get("start_line", ""))
        passed = sum(bool(item.get(k)) for k in ("cold_start_ok", "strong_action", "visual_conflict"))
        excluded = str(item.get("excluded_type") or "").strip()
        if start not in ids:
            rejected.append(f"起点编号不存在：{start}")
        elif passed < 2 or excluded not in ("", "无"):
            rejected.append(f"起点不合格：{start}（满足{passed}项，排除类型：{excluded or '无'}）")
        elif start in seen_starts:
            continue
        else:
            seen_starts.add(start)
            highlights.append(item)

    end_points = []
    for item in raw.get("end_points") or []:
        line = str(item.get("line", ""))
        if line in ids and item.get("type") in END_TYPES:
            end_points.append(item)
        else:
            rejected.append(f"结束点无效：{line}")
    end_points.sort(key=lambda item: order[item["line"]])

    skippable = []
    for item in raw.get("skippable") or []:
        a, b = str(item.get("from_line", "")), str(item.get("to_line", ""))
        if a not in ids or b not in ids or order[a] > order[b]:
            rejected.append(f"跳过段编号无效：{a}—{b}")
        elif item.get("used_later") or not item.get("resume_clear"):
            continue
        else:
            skippable.append(item)

    return {
        "characters": raw.get("characters") or [],
        "episodes": raw.get("episodes") or [],
        "conflicts": raw.get("conflicts") or [],
        "highlights": highlights,
        "end_points": end_points,
        "skippable": skippable,
        "rejected": rejected,
    }


# ---------------------------------------------------------------------------
# 第六步：本地组合（不调用模型）
# ---------------------------------------------------------------------------

class Timeline:
    """把台词编号换算成原片时间段。"""

    def __init__(self, lines: list[dict[str, Any]], inventory: list[dict[str, Any]]):
        self.lines = lines
        self.pos = {line["id"]: index for index, line in enumerate(lines)}
        self.duration = {int(row["episode"]): float(row["duration"]) for row in inventory}
        self.source = {int(row["episode"]): str(row["source"]) for row in inventory}
        self.episode_in: dict[int, float] = {}
        for line in lines:
            ep = line["episode"]
            if ep not in self.episode_in:
                # 去掉了开头回顾时，从第一句保留台词前开始；否则从本集 0 秒开始
                if line.get("recap_end") is not None:
                    self.episode_in[ep] = max(float(line["recap_end"]), line["start"] - CUT_IN_PAD_S)
                else:
                    self.episode_in[ep] = 0.0

    def _cut_in(self, index: int) -> float:
        line = self.lines[index]
        prev = self.lines[index - 1] if index > 0 else None
        floor = prev["end"] if prev and prev["episode"] == line["episode"] else 0.0
        return max(floor, line["start"] - CUT_IN_PAD_S)

    def _cut_out(self, index: int, clip_end: bool) -> float:
        line = self.lines[index]
        pad = CLIP_END_PAD_S if clip_end else CUT_OUT_PAD_S
        limit = self.duration.get(line["episode"], line["end"] + pad)
        return min(limit, line["end"] + min(float(line.get("pause_after") or 0), pad))

    def segments(self, start_id: str, end_id: str, skips: list[tuple[str, str]] = ()) -> list[dict[str, Any]]:
        a, b = self.pos[start_id], self.pos[end_id]
        removed: set[int] = set()
        for s_from, s_to in skips:
            removed.update(range(self.pos[s_from], self.pos[s_to] + 1))
        kept = [i for i in range(a, b + 1) if i not in removed]
        if not kept:
            return []
        blocks: list[list[int]] = [[kept[0]]]
        for i in kept[1:]:
            if i == blocks[-1][-1] + 1:
                blocks[-1].append(i)
            else:
                blocks.append([i])
        result: list[dict[str, Any]] = []
        for block_index, block in enumerate(blocks):
            first, last = block[0], block[-1]
            is_clip_end = block_index == len(blocks) - 1
            ep_first, ep_last = self.lines[first]["episode"], self.lines[last]["episode"]
            t_in = self._cut_in(first)
            t_out = self._cut_out(last, is_clip_end)
            if ep_first == ep_last:
                result.append({"episode": ep_first, "start": t_in, "end": t_out})
                continue
            result.append({"episode": ep_first, "start": t_in, "end": self.duration[ep_first]})
            for ep in range(ep_first + 1, ep_last):
                if ep in self.duration:
                    result.append({"episode": ep, "start": self.episode_in.get(ep, 0.0), "end": self.duration[ep]})
            result.append({"episode": ep_last, "start": self.episode_in.get(ep_last, 0.0), "end": t_out})
        merged: list[dict[str, Any]] = []
        for part in result:
            if part["end"] - part["start"] < 0.2:
                continue
            if merged and merged[-1]["episode"] == part["episode"] and abs(merged[-1]["end"] - part["start"]) < 0.05:
                merged[-1]["end"] = part["end"]
            else:
                merged.append(dict(part))
        for part in merged:
            part["source"] = self.source[part["episode"]]
        return merged

    @staticmethod
    def total(segments: list[dict[str, Any]]) -> float:
        return sum(part["end"] - part["start"] for part in segments)


def _overlap(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> float:
    shared = 0.0
    for x in a:
        for y in b:
            if x["episode"] == y["episode"]:
                shared += max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"]))
    shorter = min(Timeline.total(a), Timeline.total(b)) or 1.0
    return shared / shorter


def build_candidates(story_map: dict[str, Any], timeline: Timeline, mode: str,
                     minimum: float, maximum: float, seed: int = 0) -> list[dict[str, Any]]:
    """为每个起点 × 两类结尾生成候选方案。

    选点方法 v2（2026-11-12 复盘）：开头顺序由模型给的高光强度名次（rank，越小越强）
    主导，时长只作为「落在 [minimum, maximum] 区间」的硬门槛，不再用随机 target 去凑。
    同一起点、同一结尾类型在达标区间内优先取**最短**的方案——短=冲突密度高、节奏紧、
    开头钩子不被后面整集稀释。这样模型判断最强的高光一定排在成片最前，不被时长撞运气覆盖。
    """
    candidates: list[dict[str, Any]] = []
    for rank, highlight in enumerate(story_map["highlights"]):
        start = highlight["start_line"]
        start_pos = timeline.pos[start]
        if mode == "continuous":
            for end_type in END_TYPES:
                best = None
                for end in story_map["end_points"]:
                    if end["type"] != end_type or timeline.pos[end["line"]] <= start_pos:
                        continue
                    segments = timeline.segments(start, end["line"])
                    duration = Timeline.total(segments)
                    if not minimum <= duration <= maximum:
                        continue
                    # 区间内取最短：时长越小越优先
                    if best is None or duration < best["duration"]:
                        best = {"end": end, "segments": segments, "skips": [], "duration": duration}
                if best:
                    candidates.append({
                        "mode": mode, "rank": rank, "highlight": highlight, "end_type": end_type,
                        "end": best["end"], "skips": best["skips"], "segments": best["segments"],
                        "duration": best["duration"],
                    })
        else:
            # 跳集：枚举同一高光的多种跳法组合，每种一条差异视频，最多 MAX_JUMP_PER_HIGHLIGHT 条。
            for variant in _enumerate_jump_variants(story_map, timeline, highlight, minimum, maximum):
                candidates.append({"mode": mode, "rank": rank, "highlight": highlight, **variant})
    # 排序完全由 (高光强度名次, 结尾类型) 决定；偶数名次先告一段落、奇数名次先悬念，
    # 让相邻成片的结尾类型交替，但强度名次始终是第一位。
    candidates.sort(key=lambda c: (c["rank"], END_TYPES.index(c["end_type"]) if c["rank"] % 2 == 0 else -END_TYPES.index(c["end_type"])))
    return candidates


def _enumerate_jump_variants(story_map: dict[str, Any], timeline: Timeline, highlight: dict[str, Any],
                             minimum: float, maximum: float) -> list[dict[str, Any]]:
    """为一个高光枚举多种跳集方案：不同的"可跳段组合 × 结束点" = 不同的差异视频。

    放量的核心（2026-11-12 方案）。本地只负责排列组合与机械约束（跳点数、时长、不重叠、
    可跳段落在起点与结束点之间）；剧情通不通由后续的模型复核把关，这里不替模型判断。
    每个高光最多返回 MAX_JUMP_PER_HIGHLIGHT 条，按"跳点少→衔接稳、时长短→节奏紧"排序取前列。
    """
    start = highlight["start_line"]
    start_pos = timeline.pos[start]
    pos = timeline.pos

    variants: list[dict[str, Any]] = []
    seen_signatures: set[tuple[Any, ...]] = set()
    for end in story_map["end_points"]:
        end_pos = pos.get(end["line"])
        if end_pos is None or end_pos <= start_pos:
            continue
        # 落在本条片（起点→该结束点）区间内、且不贴着首尾的可跳段
        inside = [s for s in story_map["skippable"]
                  if pos[s["from_line"]] > start_pos + 2 and pos[s["to_line"]] < end_pos - 1]
        inside.sort(key=lambda s: pos[s["from_line"]])
        for combo in _skip_combinations(timeline, inside, MAX_SKIPS_PER_VARIANT):
            if not combo:  # 一处都不跳就是连续版，不作为跳集
                continue
            skip_pairs = [(s["from_line"], s["to_line"]) for s in combo]
            segments = timeline.segments(start, end["line"], skip_pairs)
            duration = Timeline.total(segments)
            if not minimum <= duration <= maximum:
                continue
            signature = tuple(sorted(skip_pairs))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            variants.append({
                "end_type": end["type"], "end": end, "skips": combo,
                "segments": segments, "duration": duration,
            })
    # 跳点越少越稳、时长越短节奏越紧：都作为优先项
    variants.sort(key=lambda v: (len(v["skips"]), v["duration"]))
    return variants[:MAX_JUMP_PER_HIGHLIGHT]


def _skip_combinations(timeline: Timeline, skippable: list[dict[str, Any]], max_skips: int):
    """枚举互不重叠、互不相邻的可跳段组合（含空组合），每个组合内按时间排序。

    相邻（中间无保留台词）的两段若同时跳，会并成一处，所以要求跳段之间至少隔一句，
    保证"跳点数 = 组合里的段数"，便于后面控制拼接点数量。
    """
    pos = timeline.pos
    results: list[list[dict[str, Any]]] = [[]]

    def grow(current: list[dict[str, Any]], start_index: int) -> None:
        if len(current) >= max_skips:
            return
        for i in range(start_index, len(skippable)):
            seg = skippable[i]
            # 与已选的最后一段之间至少隔一句，避免并成一处
            if current and pos[seg["from_line"]] <= pos[current[-1]["to_line"]] + 1:
                continue
            nxt = current + [seg]
            results.append(nxt)
            grow(nxt, i + 1)

    grow([], 0)
    return results


def pick_with_review(candidates: list[dict[str, Any]], count: int,
                     review: Callable[[dict[str, Any]], dict[str, Any]], max_reviews: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按顺序复核候选，通过的才入选；起点优先各不相同，几乎相同的方案不重复做。

    返回 (入选方案, 被淘汰方案)。复核次数受 max_reviews 限制，避免失控调用。
    """
    chosen: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reviewed = 0
    for allow_same_start in (False, True):
        for candidate in candidates:
            if len(chosen) >= count or reviewed >= max_reviews:
                return chosen, rejected
            if candidate in chosen or candidate in rejected:
                continue
            if not allow_same_start and any(c["highlight"]["start_line"] == candidate["highlight"]["start_line"] for c in chosen):
                continue
            if any(_overlap(candidate["segments"], other["segments"]) > 0.8 for other in chosen):
                continue
            reviewed += 1
            result = review(candidate)
            candidate["review"] = result
            (chosen if result["passed"] else rejected).append(candidate)
    return chosen, rejected


def select_candidates(candidates: list[dict[str, Any]], count: int,
                      taken: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """先保证起点各不相同；起点用完后才允许同一起点换另一类结尾。排除几乎相同的方案。"""
    taken = list(taken or [])
    chosen: list[dict[str, Any]] = []
    used_starts: set[str] = set()
    for allow_same_start in (False, True):
        for candidate in candidates:
            if len(chosen) >= count:
                return chosen
            if candidate in chosen:
                continue
            start = candidate["highlight"]["start_line"]
            if not allow_same_start and start in used_starts:
                continue
            if any(_overlap(candidate["segments"], other["segments"]) > 0.8 for other in chosen + taken):
                continue
            chosen.append(candidate)
            used_starts.add(start)
    return chosen


# ---------------------------------------------------------------------------
# 第七步：逐条复核（每条一次小调用）
# ---------------------------------------------------------------------------

REVIEW_PROMPT = """你是短剧推广视频的审片员。下面是一条推广视频实际包含的全部台词（按播放顺序），观众是刷到这条视频、从没看过这部剧的人。
台词由语音识别得到，可能有错别字，按上下文理解。【跳过】标记表示这里删掉了一段原片，后面直接接上。

请只判断三件事：
1. 开头：只看前几句。要同时满足两点才算合格，缺一不可——
   (a) 没看过前情的观众能在 3 秒内看懂谁和谁在冲突；
   (b) 开头够抓人：有强冲突、强表态或明确利害，画面上像有对峙/动手/当众羞辱/抓现行。
   如果只是"能看懂但平淡"（例如一句交代、过渡、密谋低语、客套），opening_ok 填 false，并在 opening_issue 里说明开头不够强。
2. 跳点：每个【跳过】之后，观众能否大致看懂（知道时间或场景变了，不缺理解后文必需的信息）？没有跳点时返回空数组。
3. 结尾：最后几句属于哪一类——
   告一段落（这一轮冲突有了结果，不觉得被掐断）、
   悬念（新冲突刚冒头，想看后续）、
   不能停（话没说完、问了没答、动作做到一半）。
发现问题时用一句话说明问题在哪；没有问题时 issue 填空字符串。

# 视频台词
{material}
"""


def _review_schema() -> dict[str, Any]:
    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}

    s = {"type": "string"}
    return obj({
        "opening_ok": {"type": "boolean"},
        "opening_issue": s,
        "jumps": {"type": "array", "items": obj({"index": {"type": "integer"}, "ok": {"type": "boolean"}, "issue": s})},
        "ending_type": {"type": "string", "enum": ["告一段落", "悬念", "不能停"]},
        "ending_issue": s,
    })


def clip_material(candidate: dict[str, Any], timeline: Timeline) -> str:
    start = timeline.pos[candidate["highlight"]["start_line"]]
    end = timeline.pos[candidate["end"]["line"]]
    skipped: dict[int, int] = {}
    for jump_index, skip in enumerate(candidate["skips"], 1):
        for i in range(timeline.pos[skip["from_line"]], timeline.pos[skip["to_line"]] + 1):
            skipped[i] = jump_index
    rows: list[str] = []
    marked: set[int] = set()
    for i in range(start, end + 1):
        if i in skipped:
            if skipped[i] not in marked:
                marked.add(skipped[i])
                rows.append(f"【跳过{skipped[i]}】")
            continue
        rows.append(timeline.lines[i]["text"])
    return "\n".join(rows)


def review_candidate(candidate: dict[str, Any], timeline: Timeline, call: ModelCall) -> dict[str, Any]:
    prompt = REVIEW_PROMPT.format(material=clip_material(candidate, timeline))
    response = call("review", prompt, _review_schema(), "short_drama_clip_review")
    data = response.get("data") or {}
    jumps = data.get("jumps") or []
    issues = []
    if not data.get("opening_ok"):
        issues.append(f"开头：{data.get('opening_issue') or '看不懂或没有抓力'}")
    for jump in jumps:
        if not jump.get("ok"):
            issues.append(f"跳点{jump.get('index')}：{jump.get('issue') or '接不上'}")
    if data.get("ending_type") == "不能停":
        issues.append(f"结尾：{data.get('ending_issue') or '停在不能停的位置'}")
    return {
        "passed": not issues,
        "issues": issues,
        "ending_type": data.get("ending_type"),
        "raw": data,
        "model_call": {k: response.get(k) for k in ("model", "usage", "elapsed_s")},
    }
