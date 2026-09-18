"""只读诊断：核对"闭眼 / 张嘴"两项指标在真实素材上是否真的判得准。

把指标最低/最高的帧画在同一条上，人眼确认：
- eyeBlink 高的那几张，是不是真的闭着眼；
- jawOpen 高的那几张，是不是真的在喊。

在项目环境里跑（需要 mediapipe）：
    py -3.12 tools/probe_expression_verify.py [每集抽帧数]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.runtime_process import no_window_kwargs  # noqa: E402
from server.template_engine.jianying59_template import drama_expression  # noqa: E402
from server.tool_resolver import resolve_ffmpeg  # noqa: E402

MATERIAL = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)
OUTPUT = Path(tempfile.gettempdir()) / "expression_verify"


def _extract(video: Path, seconds: float, target: Path) -> None:
    subprocess.run(
        [str(resolve_ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.3f}",
         "-i", str(video), "-frames:v", "1", "-q:v", "2", "-y", str(target)],
        capture_output=True, **no_window_kwargs(),
    )


def main() -> int:
    per_video = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    import cv2
    import numpy
    from PIL import Image, ImageDraw

    if not drama_expression.available():
        raise SystemExit("MediaPipe 不可用（缺模型或 mediapipe 未安装）")
    print("MediaPipe 已就绪，开始核对\n")

    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="exprverify_") as temporary:
        temporary_path = Path(temporary)
        for video in sorted(MATERIAL.glob("*.mp4")):
            for index in range(1, per_video + 1):
                seconds = index * 47.0 + 11.0
                frame = temporary_path / "f.jpg"
                _extract(video, seconds, frame)
                if not frame.is_file():
                    continue
                image = cv2.imdecode(numpy.fromfile(str(frame), dtype=numpy.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                expression = drama_expression.measure(image)
                if expression is None:
                    continue
                rows.append({"expr": expression, "image": image, "name": video.name, "seconds": seconds})

    print(f"抽帧 {len(rows)} 张里有表情数据")
    if not rows:
        return 1

    tiles: list[tuple[str, Image.Image]] = []
    for title, key, reverse in (("闭眼度最高", "eyes_closed", True), ("闭眼度最低", "eyes_closed", False),
                                ("张嘴度最高", "mouth_open", True), ("微笑度最高", "smile", True)):
        ordered = sorted(rows, key=lambda item: getattr(item["expr"], key), reverse=reverse)[:3]
        for item in ordered:
            expression = item["expr"]
            shot = Image.fromarray(cv2.cvtColor(item["image"], cv2.COLOR_BGR2RGB))
            width, height = shot.size
            box_height = min(height, int(width * 0.75))
            top = max(0, (height - box_height) // 2)
            shot = shot.crop((0, top, width, top + box_height)).resize((190, 253), Image.LANCZOS)
            draw = ImageDraw.Draw(shot)
            draw.rectangle((0, 0, 190, 34), fill=(0, 0, 0))
            draw.text((4, 4), title, fill=(255, 220, 120))
            draw.text((4, 18), f"eye={expression.eyes_closed:.2f} jaw={expression.mouth_open:.2f} "
                               f"smile={expression.smile:.2f}", fill=(150, 255, 150))
            tiles.append((title, shot))

    sheet = Image.new("RGB", (190 * 3 + 16, 253 * 4 + 20), (18, 18, 22))
    for index, (_title, tile) in enumerate(tiles[:12]):
        sheet.paste(tile, ((index % 3) * 194 + 4, (index // 3) * 257 + 4))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "表情指标核对.png"
    sheet.save(target)
    print(f"拼图：{target}")
    print("第1行=闭眼度最高（应该真的闭眼/眯眼）；第2行=闭眼度最低（应该睁眼）；"
          "第3行=张嘴度最高（应该在喊）；第4行=微笑度最高（应该在笑）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
