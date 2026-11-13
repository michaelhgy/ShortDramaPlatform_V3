"""Build the main video/audio timeline directly in the final FFmpeg graph.

Each source frame is encoded once with the existing template composition.
The template clock remains the final video's clock across insertion boundaries.
"""
from pathlib import Path


def has_insertions(job):
    return any(item.get('kind') == 'insertion' for item in (job.get('insertions') or {}).get('segments', []))


def timeline_graph(job, start, frames, *, video=True, audio=False):
    """Return inputs, graph, video label and audio label for an exact frame range."""
    inputs, graph, labels = [], [], []
    cursor = 0
    stop = start + frames
    for segment in job['insertions']['segments']:
        end = cursor + segment['frames']
        left, right = max(start, cursor), min(stop, end)
        if right <= left:
            cursor = end
            continue
        index = len(labels)
        offset = left - cursor
        count = right - left
        seconds = count / 30
        is_source = segment['kind'] == 'source'
        path = Path(job['source_path']) if is_source else Path(segment['path'])
        seek = ((segment.get('source_start_frame', 0) if is_source else 0) + offset) / 30
        inputs += ['-threads', '2', '-ss', f'{seek:.9f}', '-i', str(path)]
        if video:
            graph.append(f'[{index}:v]fps=30:start_time=0,scale=1080:2400:force_original_aspect_ratio=increase,'
                         f'crop=1080:2400,setsar=1,format=yuv420p,'
                         f'tpad=stop_mode=clone:stop_duration=1,trim=end_frame={count},'
                         f'settb=1/30,setpts=N[insv{index}]')
        if audio:
            sound = job.get('source_has_audio', job.get('has_audio', False)) if is_source else segment.get('has_audio', False)
            if sound:
                graph.append(f'[{index}:a:0]aresample=48000:async=1:first_pts=0,'
                             f'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,'
                             f'apad,atrim=duration={seconds:.9f},asetpts=PTS-STARTPTS[insa{index}]')
            else:
                graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={seconds:.9f},'
                             f'asetpts=PTS-STARTPTS[insa{index}]')
        labels.append(index)
        cursor = end
    if not labels or cursor < stop:
        raise ValueError('插片时间轴未完整覆盖请求范围')
    if video and audio:
        pads = ''.join(f'[insv{i}][insa{i}]' for i in labels)
        graph.append(f'{pads}concat=n={len(labels)}:v=1:a=1[ins_video][ins_audio]')
    elif video:
        pads = ''.join(f'[insv{i}]' for i in labels)
        graph.append(f'{pads}concat=n={len(labels)}:v=1:a=0[ins_video]')
    else:
        pads = ''.join(f'[insa{i}]' for i in labels)
        graph.append(f'{pads}concat=n={len(labels)}:v=0:a=1[ins_audio]')
    return inputs, ';'.join(graph), 'ins_video', 'ins_audio'


def bind_timeline(inputs, graph, job, frames, *, audio=False):
    """Replace the first source input while preserving all template input indices."""
    extra, timeline, video_label, audio_label = timeline_graph(
        job, job.get('_timeline_start_frame', 0), frames, audio=audio)
    source_end = inputs.index('-i') + 2
    shifted = len([item for item in extra if item == '-i']) - 1
    import re
    def remap(match):
        index, stream = int(match[1]), match[2]
        return f'[{video_label}]' if index == 0 and stream == 'v' else f'[{index + shifted}:{stream}]'
    graph = re.sub(r'\[(\d+):(v|a)\]', remap, graph)
    return [*extra, *inputs[source_end:]], timeline + ';' + graph, audio_label
