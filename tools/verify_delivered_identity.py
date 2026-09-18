"""只读诊断：对"最终交付的 10 张剧照"再做一次身份核对，看有没有重复演员。

为什么不看清单而看成品：清单记的是"候选帧"的身份，而裁切时可能改用了同槽位里
另一帧（为了拉开画面差异），两者的脸不一定是同一个。所以必须用**最终图片**复核。

用法：
    py -3.12 tools/verify_delivered_identity.py
"""

from __future__ import annotations

import itertools
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.template_engine.jianying59_template import drama_face, drama_identity  # noqa: E402
from server.template_engine.jianying59_template.photo_prep import prepare_drama_photos  # noqa: E402

ACCOUNT_DAY_DIR = Path(
    r"D:\短剧推广运营系统\生产文件\9月18日\小黄叽啾咪\神农宝库，医武镇九州\素材"
)


def main() -> int:
    import cv2
    import numpy

    with tempfile.TemporaryDirectory(prefix="delivered_") as temporary:
        decision = prepare_drama_photos(
            account_day_dir=ACCOUNT_DAY_DIR, output_dir=Path(temporary) / "剧照", seed=20260918,
        )
        records = []
        for item in decision.items:
            image = cv2.imdecode(numpy.fromfile(item.output, dtype=numpy.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            faces = drama_face.detect_faces(image)
            if not faces:
                records.append((item.index, None, 0.0, item))
                continue
            biggest = max(faces, key=lambda face: face.area)
            identity = drama_identity.identity_of(image, biggest)
            records.append((item.index, identity, biggest.width, item))

    with_identity = [(index, identity) for index, identity, _width, _item in records if identity is not None]
    print(f"10 张成片里可判定身份的有 {len(with_identity)} 张\n")

    print(f"{'#1':>3} {'#2':>3} {'相似度':>8}")
    duplicates = []
    for (left_index, left_identity), (right_index, right_identity) in itertools.combinations(with_identity, 2):
        score = left_identity.similarity(right_identity)
        if score >= drama_identity.SAME_PERSON_THRESHOLD:
            duplicates.append((score, left_index, right_index))
    for score, left_index, right_index in sorted(duplicates, reverse=True):
        print(f"{left_index:>3} {right_index:>3} {score:>8.3f}")
    if not duplicates:
        print("   （没有超过阈值的配对）")

    # 简单的贪心聚类，得到"实际有几个人"
    clusters: list[list] = []
    for index, identity in with_identity:
        placed = False
        for cluster in clusters:
            if identity.is_same_person(cluster[0][1]):
                cluster.append((index, identity))
                placed = True
                break
        if not placed:
            clusters.append([(index, identity)])
    print(f"\n最终 10 张里实际出现的人数（相似度阈值 {drama_identity.SAME_PERSON_THRESHOLD}）：{len(clusters)}")
    for cluster in sorted(clusters, key=len, reverse=True):
        print(f"   出现 {len(cluster)} 张：第 {', '.join(str(index) for index, _ in cluster)} 张")

    if duplicates:
        print(f"\n⚠️ 有 {len(duplicates)} 对照片被判为同一个人——去重没生效或阈值偏低。")
        return 1
    print("\n✅ 没有发现重复演员。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
