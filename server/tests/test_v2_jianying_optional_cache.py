import json
from pathlib import Path

from server.final_engine.jianying59_final.composition import _attach_native_mask_paths
from server.jianying_resource_paths import attach_cached_path_if_present
from server.template_engine.jianying59_template.track01 import _attach_native_paths_and_filter


def test_optional_cached_path_leaves_resource_id_usable_when_cache_is_missing(tmp_path: Path) -> None:
    material: dict[str, object] = {"resource_id": "6791700809454195207", "path": "stale-path"}
    assert attach_cached_path_if_present(material, tmp_path / "missing") is None
    assert material == {"resource_id": "6791700809454195207"}


def test_template_rectangle_mask_does_not_require_a_downloaded_cache(tmp_path: Path) -> None:
    content = tmp_path / "draft_content.json"
    content.write_text(json.dumps({
        "materials": {"masks": [{"id": "rectangle", "resource_type": "rectangle", "resource_id": "6791700809454195207"}]},
        "tracks": [{"name": "T01_OUTER_VIDEO", "segments": [{"extra_material_refs": ["rectangle"]}]}],
    }), encoding="utf-8")

    class Decision:
        filter_resource_id = "7486736825369840907"
        filter_name = "日光肤"
        filter_strength = 0.01

    _attach_native_paths_and_filter(content_path=content, decision=Decision(), user_data_root=tmp_path / "User Data")
    result = json.loads(content.read_text(encoding="utf-8"))
    rectangle = result["materials"]["masks"][0]
    effect = result["materials"]["effects"][0]
    assert "path" not in rectangle
    assert effect["resource_id"] == "7486736825369840907"
    assert effect["path"] == ""


def test_final_rectangle_mask_does_not_require_a_downloaded_cache(tmp_path: Path) -> None:
    content = tmp_path / "draft_content.json"
    content.write_text(json.dumps({
        "materials": {"masks": [{"id": "rectangle", "resource_type": "rectangle", "resource_id": "6791700809454195207", "path": "stale-path"}]},
    }), encoding="utf-8")
    _attach_native_mask_paths(content, tmp_path / "User Data")
    result = json.loads(content.read_text(encoding="utf-8"))
    assert "path" not in result["materials"]["masks"][0]
