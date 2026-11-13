"""Continuous random frame partitions, fixed before any output is created."""
import math
import random

FPS=30
MAX_FRAMES=30*FPS
LOW_FRAMES=15*FPS
HIGH_FRAMES=28*FPS


def time_segments(duration,seed):
    if not math.isfinite(duration) or duration<1:raise ValueError('原片至少需要1秒有效视频')
    frames=max(FPS,round(duration*FPS))
    if duration<=30:return [{'start_frame':0,'frames':min(MAX_FRAMES,frames)}]
    rng=random.Random(seed)
    count=max(math.ceil(frames/HIGH_FRAMES),min(frames//LOW_FRAMES,round(frames/rng.randint(20*FPS,24*FPS))))
    lengths=[];left=frames
    for index in range(count):
        remaining=count-index-1
        length=rng.randint(max(LOW_FRAMES,left-remaining*HIGH_FRAMES),min(HIGH_FRAMES,left-remaining*LOW_FRAMES))
        lengths.append(length);left-=length
    rng.shuffle(lengths);cursor=0;result=[]
    for length in lengths:
        result.append({'start_frame':cursor,'frames':length});cursor+=length
    assert cursor==frames
    return result


def processing_plan(crops,segments):
    return {'version':1,'outputs':[{'crop_index':i,**segment} for segment in segments for i in range(len(crops))]}


def validate_plan(meta,crops):
    plan=meta['processing_plan'];segments=meta['time_segments'];cursor=0
    if plan.get('version')!=1 or not segments:raise ValueError('风景分段配方版本或时间轴无效')
    for segment in segments:
        if (set(segment)!={'start_frame','frames'} or type(segment['start_frame']) is not int
                or type(segment['frames']) is not int or segment['start_frame']!=cursor or not 1<=segment['frames']<=MAX_FRAMES):
            raise ValueError('风景分段时间轴不连续或超过30秒，保留原片')
        cursor+=segment['frames']
    if cursor!=round(meta['duration']*FPS) or plan!=processing_plan(crops,segments):raise ValueError('风景分段未完整覆盖原片，保留原片')
    return plan['outputs']
