"""Render the project's plain Markdown rules for offline reading, without JS."""
from __future__ import annotations
import html
from pathlib import Path
import re
import shutil

STYLE = """body{margin:32px auto;max-width:1080px;padding:0 24px 60px;
font:16px/1.85 'Microsoft YaHei',sans-serif;color:#253246;background:#f8fafc}
h1{font-size:30px}h2{margin-top:38px;border-top:1px solid #dce3ec;padding-top:20px}
h3{margin-top:26px}a{color:#165cc5}table{border-collapse:collapse;width:100%;background:white}
th,td{padding:10px 12px;border:1px solid #dce3ec;text-align:left;vertical-align:top}
th{background:#eaf0f8}code{background:#e9edf3;padding:2px 5px;border-radius:3px}
blockquote{border-left:4px solid #7895bf;margin-left:0;padding-left:16px}
pre{white-space:pre-wrap}li{margin:6px 0}"""


def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    def link(m):
        target = m[2]
        if target.endswith(".md"):
            target = target[:-3] + ".html"
        return f'<a href="{target}">{m[1]}</a>'
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, s)


def render(text):
    out = []; mode = None; fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            out.append("</pre>" if fenced else "<pre>"); fenced = not fenced; continue
        if fenced:
            out.append(html.escape(line)); continue
        current = "table" if line.startswith("|") else "ul" if line.startswith("- ") else "ol" if re.match(r"^\d+\. ", line) else None
        if mode != current:
            if mode: out.append(f"</{mode}>")
            if current: out.append(f"<{current}>")
            mode = current
        if current == "table":
            if re.fullmatch(r"[\s|:\-]+", line): continue
            out.append("<tr>" + "".join("<td>"+inline(c.strip())+"</td>" for c in line.strip("|").split("|"))+"</tr>")
        elif current:
            out.append("<li>"+inline(re.sub(r"^(?:-|\d+\.) ", "", line))+"</li>")
        elif line.startswith("#"):
            match = re.match(r"^(#{1,6}) (.*)", line)
            if match: out.append(f"<h{len(match[1])}>{inline(match[2])}</h{len(match[1])}>")
        elif line.startswith("> "): out.append("<blockquote>"+inline(line[2:])+"</blockquote>")
        elif line.strip(): out.append("<p>"+inline(line)+"</p>")
    if mode: out.append(f"</{mode}>")
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V3 业务与功能说明</title><style>'+STYLE+'</style>'+"\n".join(out)+"</html>"


def publish(root, package):
    root, package = Path(root), Path(package)
    files = [Path("docs/V3业务与功能说明.md"), Path("docs/7-多机部署现状.md")]
    files += sorted((root / "docs/功能档案").rglob("*.md"))
    # Linked issue records are useful evidence, but exclude all test media.
    files += sorted((root / "docs/事项档案").glob("*V3*.md"))
    files.append(Path("docs/archive/2026-10-20打包前多机部署说明.md"))
    for item in files:
        relative = item.relative_to(root) if item.is_absolute() else item
        source = root / relative
        if not source.exists(): continue
        target = package / "使用说明" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.with_suffix(".html").write_text(render(source.read_text(encoding="utf-8")), encoding="utf-8")
    user_guide = root / "docs" / "V3使用手册"
    guide_entry = "使用说明/docs/V3业务与功能说明.html"
    guide_title = "V3 业务与功能说明"
    if (user_guide / "index.html").is_file():
        shutil.copytree(user_guide, package / "使用手册", dirs_exist_ok=True)
        guide_entry = "使用手册/index.html"
        guide_title = "V3 详细使用手册"
    (package / "使用说明.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={guide_entry}">'
        f'<a href="{guide_entry}">打开 {guide_title}</a></html>', encoding="utf-8")


if __name__ == "__main__":
    import sys
    publish(Path(__file__).resolve().parents[1], Path(sys.argv[1]))
