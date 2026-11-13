from copy import deepcopy

DEFAULTS = {
    'width': 1080, 'height': 2400, 'fps': 30,
    'duration_seconds': 600, 'duration_jitter': 30,
    'template_usage_limit': 20,
    'scenery_count': 6, 'scenery_count_jitter': 0, 'scenery_usage_limit': 5,
    'scenery_group_gap_percent': [15, 70],
    'height_large_percent': [28, 33], 'height_small_percent': [20, 25],
    'mask_percent': [40, 55], 'feather_percent': [55, 80],
    'sticker_alpha_percent': 80,
    'overlay_sticker_enabled': False, 'overlay_sticker_count': [24, 48],
    'overlay_sticker_opacity_percent': 2,
    'photo_layer_enabled': False, 'photo_layer_count': [6, 6],
    'photo_layer_opacity_percent': 2, 'photo_usage_limit': 5,
    'effect_count': [3, 5], 'effect_segment_seconds': [30, 60],
    'effect_strength_percent': [90, 100], 'effect_pair_percent': [15, 30],
    'effect_transition_seconds': [1, 2], 'border_width': [5, 10],
}
# Editorial recommendations only. Validation below enforces units and geometry.
RANGES = {
    'template_usage_limit': (1, 1000),
    'duration_seconds': (10, 1800), 'duration_jitter': (0, 300),
    'scenery_count': (4, 30), 'scenery_count_jitter': (0, 10), 'scenery_usage_limit': (1, 1000),
    'scenery_group_gap_percent': (1, 95),
    'height_large_percent': (28, 33), 'height_small_percent': (20, 25),
    'mask_percent': (40, 55), 'feather_percent': (55, 80),
    'sticker_alpha_percent': (1, 80), 'effect_count': (1, 23),
    'overlay_sticker_count': (1, 64), 'overlay_sticker_opacity_percent': (1, 100),
    'photo_layer_count': (1, 30), 'photo_layer_opacity_percent': (1, 100),
    'photo_usage_limit': (1, 1000),
    'effect_segment_seconds': (10, 180), 'effect_strength_percent': (1, 100),
    'effect_pair_percent': (0, 30), 'effect_transition_seconds': (1, 2), 'border_width': (5, 10),
}

def validate(value):
    from .parameter_info import FIELDS
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError('模板参数不完整或包含未知字段，请重新读取参数')
    out = deepcopy(value)
    for key, default in DEFAULTS.items():
        if type(default) is bool:
            if type(out[key]) is not bool: raise ValueError(f'{key} 必须为启用或关闭')
            continue
        values = out[key] if isinstance(default, list) else [out[key]]
        if not isinstance(values, list) or len(values) != (2 if isinstance(default, list) else 1):
            raise ValueError(f'{key} 必须是最小值和最大值')
        label=FIELDS[key][0] if key in FIELDS else key
        if any(type(v) is not int or abs(v)>2**53-1 for v in values):
            raise ValueError(f'{label} 必须填写可精确表示的整数')
        if key in ('width','height','fps'):
            if out[key]!=default:raise ValueError('当前输出规格固定为1080×2400、30帧')
        elif key.endswith('_percent'):
            low=1 if key in ('height_large_percent','height_small_percent') else 0
            if any(not low<=v<=100 for v in values):raise ValueError(f'{label} 是百分比，必须为{low}—100')
        elif key in ('duration_jitter','scenery_count_jitter'):
            if any(v<0 for v in values):raise ValueError(f'{label} 不能为负数')
        elif any(v<1 for v in values):raise ValueError(f'{label} 必须为正整数')
        if values[0] > values[-1]: raise ValueError(f'{label} 下限不能大于上限')
    if out['border_width'][1]>out['width']:raise ValueError('边条宽度不能超过画面本身的1080像素')
    if out['duration_seconds']-out['duration_jitter']<1:
        raise ValueError('模板时长减去时长误差后必须至少为1秒')
    if out['scenery_count']-out['scenery_count_jitter'] < 4:
        raise ValueError('风景抽取条数减去误差后至少为4条')
    return out
