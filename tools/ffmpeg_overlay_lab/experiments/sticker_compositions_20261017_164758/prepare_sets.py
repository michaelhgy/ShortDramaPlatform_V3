"""Preserve AI comparison sheets; extract paired sets and show on one real frame."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

WORK_ROOT = Path(__file__).resolve().parent
ROOT = WORK_ROOT / 'review_v2'
FONT = '/mnt/c/Windows/Fonts/msyh.ttc'


def run(args: list[str]) -> bytes:
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def ffmpeg(inputs: list[Path], graph: str, output: Path) -> None:
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-filter_complex_threads', '1']
    for path in inputs:
        args += ['-i', str(path)]
    graph_path = output.with_suffix('.ffgraph')
    graph_path.write_text(graph, encoding='utf-8')
    args += ['-filter_complex_script', str(graph_path), '-map', '[out]', '-frames:v', '1',
             '-threads', '1', '-update', '1']
    if output.suffix == '.jpg':
        args += ['-q:v', '2']
    run(args + [str(output)])


def probe(path: Path) -> dict:
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))['streams'][0]


def add_label(graph: str, label: Path, x: int, y: int, size: int = 23) -> str:
    return graph + f',drawtext=fontfile={FONT}:textfile={label}:fontsize={size}:fontcolor=0xf4f2ec:x={x}:y={y}'


def content_bounds(alpha: bytes, width: int, height: int, left: int, right: int, lower: bool) -> list[int]:
    y0, y1 = (height // 2, height) if lower else (0, height // 2)
    points = [(x, y) for y in range(y0, y1)
              for x, value in enumerate(alpha[y*width+left:y*width+right], start=left) if value > 8]
    assert points
    x0, x1 = max(left, min(x for x, y in points)-4), min(right, max(x for x, y in points)+5)
    y0, y1 = max(y0, min(y for x, y in points)-4), min(y1, max(y for x, y in points)+5)
    return [x0, y0, x1-x0, y1-y0]


def place_paired_regions(copied: Path, output: Path, spec: dict, bounds: list[list[int]]) -> dict:
    # The AI study supplies the related artwork; fit both regions with ONE scale,
    # retaining relative line weight and keeping the actor/subtitle region clear.
    scale = min(1032/max(b[2] for b in bounds), 400/max(b[3] for b in bounds))
    sizes = [[round(b[2]*scale), round(b[3]*scale)] for b in bounds]
    anchors = {'01': ['left', 'right'], '02': ['center', 'center'],
               '03': ['center', 'center'], '04': ['right', 'left'],
               '05': ['center', 'center'], '06': ['offset_left', 'offset_right']}
    xs = []
    for (width, height), anchor in zip(sizes, anchors[spec['id']]):
        x = {'left': 24, 'right': 1080-width-24, 'center': (1080-width)//2,
             'offset_left': round(1080*.40-width/2),
             'offset_right': round(1080*.67-width/2)}[anchor]
        xs.append(max(24, min(1080-width-24, x)))
    graph = '[0:v]format=rgba,split=2[t][b];'
    for index, name in enumerate(('t', 'b')):
        x, y, width, height = bounds[index]
        sw, sh = sizes[index]
        graph += f'[{name}]crop={width}:{height}:{x}:{y},scale={sw}:{sh}:flags=lanczos[{name}a];'
    graph += 'color=c=black@0:s=1080x2400:r=1:d=1,format=rgba[bg];'
    graph += f'[bg][ta]overlay={xs[0]}:24:format=rgb:alpha=straight:shortest=1[p];'
    graph += f'[p][ba]overlay={xs[1]}:{2400-24-sizes[1][1]}:format=rgb:alpha=straight:shortest=1[out]'
    ffmpeg([copied], graph, output)
    return {'source_region_bounds': bounds, 'common_uniform_scale': scale,
            'scaled_sizes': sizes, 'top_xy': [xs[0], 24],
            'bottom_xy': [xs[1], 2400-24-sizes[1][1]],
            'method': 'same-theme top/bottom kept together; scaled uniformly and anchored within edge regions'}


def main() -> None:
    ROOT.mkdir(exist_ok=False)
    plan = json.loads((WORK_ROOT / 'prompts.json').read_text(encoding='utf-8'))
    sources = {item['id']: item for item in json.loads((WORK_ROOT / 'sources.json').read_text(encoding='utf-8'))}
    for folder in ('boards', 'sets', 'previews'):
        (ROOT / folder).mkdir(exist_ok=True)
    reports, board_reports = [], []
    for board in plan['boards']:
        source = Path(sources[board['id']]['source'])
        copied = ROOT / 'boards' / (board['id'] + '.png')
        if copied.exists():
            raise FileExistsError(copied)
        shutil.copy2(source, copied)
        info = probe(copied)
        digest = hashlib.sha256(copied.read_bytes()).hexdigest()
        assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
        board_reports.append({'id': board['id'], 'source': str(source), 'copy': str(copied),
                              'sha256': digest, 'width': info['width'], 'height': info['height'],
                              'tool_wall_seconds': sources[board['id']]['tool_wall_seconds']})
        board_alpha = run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(copied), '-frames:v', '1',
                           '-vf', 'alphaextract', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'])
        for column, spec in enumerate(board['sets']):
            left, right = info['width'] * column // 3, info['width'] * (column + 1) // 3
            asset = ROOT / 'sets' / (spec['id'] + '_' + spec['name'] + '.png')
            bounds = [content_bounds(board_alpha, info['width'], info['height'], left, right, lower)
                      for lower in (False, True)]
            # Art on a study sheet can cross the conceptual column boundary.
            # Use reviewed source rectangles to preserve the complete clouds
            # and flowers and exclude disconnected fragments of the neighbor.
            reviewed = {'02': [[445, 75, 572, 185], [480, 870, 520, 190]],
                        '03': [[1016, 110, 409, 152], [1000, 720, 425, 340]]}
            if spec['id'] in reviewed:
                assert (info['width'], info['height']) == (1448, 1086)
                bounds = reviewed[spec['id']]
            placement = place_paired_regions(copied, asset, spec, bounds)
            alpha = run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(asset), '-frames:v', '1',
                         '-vf', 'alphaextract', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'])
            assert len(alpha) == 1080 * 2400 and min(alpha) == 0 and max(alpha) > 0
            center = alpha[600*1080:1800*1080]
            assert max(center) <= 8, f'Unexpected central artwork: {spec["id"]}'
            label = ROOT / 'previews' / (spec['id'] + '_label.txt')
            label.write_text(spec['id'] + ' ' + spec['name'], encoding='utf-8')
            actual = ROOT / 'previews' / (spec['id'] + '_同帧.png')
            ffmpeg([WORK_ROOT / '同帧底图_6秒.png', asset],
                   '[1:v]format=rgba,colorchannelmixer=aa=0.70[art];'
                   '[0:v][art]overlay=0:0:format=rgb:alpha=straight:shortest=1[out]', actual)
            for kind, image in [('film', actual), ('neutral', asset)]:
                graph = '[0:v]scale=360:800:flags=lanczos,format=rgba[art];'
                graph += 'color=c=0x263244:s=360x850:r=1:d=1,format=rgba[bg];'
                graph += '[bg][art]overlay=0:50:format=rgb:alpha=straight:shortest=1'
                ffmpeg([image], add_label(graph, label, 16, 10) + '[out]',
                       ROOT / 'previews' / (spec['id'] + '_' + kind + '_card.png'))
            detail = '[0:v]split=2[a][b];[a]crop=1080:520:0:0,scale=540:260[t];'
            detail += '[b]crop=1080:520:0:1880,scale=540:260[d];[t][d]vstack=2[art];'
            detail += 'color=c=0x263244:s=540x580:r=1:d=1,format=rgba[bg];'
            detail += '[bg][art]overlay=0:55:format=rgb:alpha=straight:shortest=1'
            ffmpeg([asset], add_label(detail, label, 18, 14, 26) + '[out]',
                   ROOT / 'previews' / (spec['id'] + '_detail_card.png'))
            reports.append({**spec, 'asset': str(asset), 'source_board': board['id'],
                            'crop_x_range': [left, right], 'canvas': [1080, 2400],
                            'fully_transparent_fraction': round(alpha.count(0)/len(alpha), 6),
                            'center_alpha_max': max(center), 'preview_opacity': 0.70,
                            'placement': placement})
    for kind, filename in [('film', '六套上下构图_同帧对照.jpg'),
                           ('neutral', '六套上下构图_透明层预览.jpg'),
                           ('detail', '六套上下构图_上下细节.jpg')]:
        inputs = [ROOT / 'previews' / (item['id'] + '_' + kind + '_card.png') for item in reports]
        graph = '[0:v][1:v][2:v]hstack=3[top];[3:v][4:v][5:v]hstack=3[bottom];[top][bottom]vstack=2[out]'
        ffmpeg(inputs, graph, ROOT / filename)
    result = {'tool': 'built-in image_gen', 'generation_calls': 2,
              'source_boards': board_reports, 'sets': reports,
              'visual_acceptance': 'USER_PENDING', 'note': 'Six direction studies, not a validated 500-set library'}
    (ROOT / 'review_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'sets': len(reports), 'central_regions_clear': True,
                      'generation_calls': 2, 'root': str(ROOT)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
