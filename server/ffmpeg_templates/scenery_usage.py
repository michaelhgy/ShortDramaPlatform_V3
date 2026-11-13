"""Scenery identity follows positive-length entries in the saved playback timeline."""


def scheduled_materials(track):
    sources={m['id']:m for m in track['materials']}
    selected={}
    for item in track['sequence']:
        frames=item['frames']
        if type(frames) is not int or frames<0:raise ValueError('风景时间轴片段帧数无效')
        if not frames:continue
        identity=item['id']
        if identity not in sources:raise ValueError('风景时间轴引用了未登记的素材')
        selected.setdefault(identity,sources[identity])
    return list(selected.values())


def scheduled_scenery(plan):
    selected={}
    for track in plan['tracks']:
        for source in scheduled_materials(track):selected.setdefault(source['id'],source)
    return list(selected.values())
