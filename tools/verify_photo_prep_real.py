"""等级 3 验证：对真实素材真跑一次剧照准备，确认不再报"不是3:4"。

**不写生产数据**：输出目录是系统临时目录。
用法：
    py -3.12 tools/verify_photo_prep_real.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, photo_prep  # noqa: E402

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)


def main() -> int:
    if not ACCOUNT_DAY_DIR.is_dir():
        raise SystemExit(f"素材目录不存在：{ACCOUNT_DAY_DIR}")
    if not drama_face.detector_available():
        raise SystemExit("人脸检测模型不可用，无法做这次验证")

    with tempfile.TemporaryDirectory(prefix="photo_prep_real_") as temporary:
        output = Path(temporary) / "剧照"
        events: list[tuple[str, str]] = []
        decision = photo_prep.prepare_drama_photos(
            account_day_dir=ACCOUNT_DAY_DIR,
            output_dir=output,
            seed=20260918,
            progress=lambda phase, message: events.append((phase, message)),
        )

        from PIL import Image

        print(f"输出目录：{output}")
        print(f"张数：{decision.count}；人脸偏好：{decision.face_preference}")
        manifest_path = Path(decision.output_directory) / "剧照准备清单.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            print(f"挑选档位：{manifest.get('selection_stage')}（strict = 全部达到严格标准）")
            print(f"质量统计：{json.dumps(manifest.get('quality', {}), ensure_ascii=False)}")
            print(f"检测器：人脸={manifest.get('face_detector_available')} "
                  f"表情={manifest.get('expression_detector_available')} "
                  f"身份={manifest.get('identity_model_available')}")
        print()
        print(f"{'#':>3}  {'尺寸':>10}  {'比例':>8}  {'精确3:4':>7}  {'人脸':>4}  {'正面分':>6}  "
              f"{'脸宽':>5}  {'闭眼':>5}  {'微笑':>5}  {'演员':>4}  裁切")
        failures = 0
        face_frames = 0
        for item in decision.items:
            with Image.open(item.output) as image:
                width, height = image.size
            exact = width * 4 == height * 3
            failures += 0 if exact else 1
            face_frames += 1 if item.face_count else 0
            print(f"{item.index:>3}  {width}x{height:<5}  {width / height:>8.6f}  "
                  f"{'是' if exact else '否!!':>7}  {item.face_count:>4}  {item.frontal_score:>6.2f}  "
                  f"{item.face_width:>5.0f}  {item.eyes_closed:>5.2f}  {item.smile:>5.2f}  "
                  f"{'第' + str(item.person_ordinal) + '张' if item.person_ordinal else '—':>4}  "
                  f"{item.crop_mode}")

        print()
        print(f"精确 3:4 失败张数：{failures}（必须为 0）")
        print(f"检测到人脸的张数：{face_frames}/{decision.count}")
        crop_events = [message for phase, message in events if phase == "裁切剧照"]
        print(f"裁切阶段记录：{len(crop_events)} 条，其中以人脸为中心的 "
              f"{sum(1 for message in crop_events if '以人脸为中心' in message)} 条")
        print()
        print("每张的选帧依据（来自任务的裁切阶段记录）：")
        for message in crop_events:
            print("   " + message.split("：", 1)[-1])

        # 把成品缩略拼一张图，方便人眼确认确实是人物照。
        tiles = [Image.open(item.output).convert("RGB").resize((180, 240), Image.LANCZOS) for item in decision.items]
        sheet = Image.new("RGB", (180 * 5 + 24, 240 * 2 + 12), (20, 20, 24))
        for index, tile in enumerate(tiles):
            sheet.paste(tile, ((index % 5) * 184 + 4, (index // 5) * 244 + 4))
        sheet_path = Path(tempfile.gettempdir()) / "photo_prep_real" / "剧照成品_10张.png"
        sheet_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(sheet_path)
        print(f"\n成品拼图：{sheet_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
