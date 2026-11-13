from pathlib import Path

from PIL import Image
import pytest

from server.content_template_renderer import (
    TitleTooLongError,
    available_template_ids,
    fit_title,
    render_overlay,
)


def test_all_four_templates_fit_the_requested_title_in_one_or_two_lines(tmp_path: Path):
    title = "靠一碗福饺，我逆风扭转人生"
    assert len(available_template_ids()) == 4
    for template_id in available_template_ids():
        result = render_overlay(template_id, title, tmp_path / f"{template_id}.png")
        assert result["title"] == title
        assert len(result["layout"]["lines"]) in (1, 2)
        image = Image.open(result["output"])
        assert image.mode == "RGBA"
        assert image.size == (1080, 1920)
        assert image.getbbox() is not None


def test_fit_title_strips_book_title_wrappers():
    result = fit_title("《妆匣渡古今》", "mumu-original")
    assert result["text"] == "妆匣渡古今"
    assert result["lines"] == ["妆匣渡古今"]


def test_fit_title_uses_two_lines_before_rejecting_long_text():
    result = fit_title("这是一个很长很长的短剧标题名称，男女主角经历重重波折终于逆风翻盘", "mumu-red")
    assert len(result["lines"]) == 2


def test_fit_title_rejects_unrenderable_title():
    with pytest.raises(TitleTooLongError):
        fit_title("这是一个没有任何标点并且长度远远超过标题板可以容纳范围的剧名文本" * 3, "mumu-red")


def test_short_title_uses_more_of_the_available_title_area():
    long_title = fit_title("摆渡五年无人问，一朝停船全岛求", "mumu-original")
    short_title = fit_title("白条试人心", "mumu-original")
    assert short_title["font_size"] > long_title["font_size"]
    assert short_title["lines"] == ["白条试人心"]
