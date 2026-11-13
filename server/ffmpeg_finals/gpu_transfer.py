"""Scale, RGB transfer and colour conversion on one Vulkan device.

The atlas contains source | K | T. Keep the original integer truncation and
saturating addition; coloured transmission is not ordinary scalar alpha.
"""
from pathlib import Path

SHADER = """//!HOOK MAIN
//!BIND HOOKED
//!WIDTH HOOKED.w 3 /
//!HEIGHT HOOKED.h
vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec3 v = floor(HOOKED_tex(vec2(uv.x/3.0, uv.y)).rgb*255.0+0.5);
    vec3 k = floor(HOOKED_tex(vec2((uv.x+1.0)/3.0, uv.y)).rgb*255.0+0.5);
    vec3 t = floor(HOOKED_tex(vec2((uv.x+2.0)/3.0, uv.y)).rgb*255.0+0.5);
    return vec4(min(floor(v*t/255.0)+k, vec3(255.0))/255.0, 1.0);
}
"""

COMMON = ("upscaler=bicubic:downscaler=bicubic:sigmoid=0:disable_linear=1:"
          "deband=0:peak_detect=0:dithering=none:tonemapping=clip:gamut_mode=clip:"
          "color_trc=bt709:color_primaries=bt709:apply_filmgrain=0:apply_dolbyvision=0:"
          "extra_opts='upscaler_param1=0\\:upscaler_param2=0.6\\:"
          "downscaler_param1=0\\:downscaler_param2=0.6'")


def filter_path(path):
    return Path(path).resolve().as_posix().replace('\\','\\\\').replace(':','\\:').replace("'","'\\''")


def supports(job):
    """Keep unusual SAR, rotation, HDR and untagged colour on the old path."""
    return (not job.get('still_image') and (job.get('source_width') or 0)>0
            and (job.get('source_height') or 0)>0 and job.get('source_pix_fmt')=='yuv420p'
            and job.get('source_sar') in ('1:1','0:1')
            and job.get('source_color_space') in ('bt709','bt470bg','smpte170m')
            and job.get('source_color_trc') in (None,'unknown','bt709','smpte170m','gamma22','gamma28')
            and not job.get('source_rotation')
            and job.get('source_field_order') in (None,'unknown','progressive'))


def crop_geometry(iw,ih,width=1080,height=2400):
    # Match force_original_aspect_ratio=increase and the integer RGB crop.
    sw=max(width,(iw*height+ih//2)//ih)
    sh=max(height,(ih*width+iw//2)//iw)
    return ((sw-width)//2*iw/sw,(sh-height)//2*ih/sh,width*iw/sw,height*ih/sh)


def transfer_graph(folder,job,width=1080,height=2400):
    shader=Path(folder)/'rgb_transfer.glsl';shader.write_text(SHADER,encoding='utf8')
    x,y,w,h=crop_geometry(job['source_width'],job['source_height'],width,height)
    clock=f"trim=end_frame={job['frames']},settb=1/30,setpts=N"
    return (
        f'[0:v]fps=30,tpad=stop_mode=clone:stop_duration=1,{clock},setsar=1,'
        'setparams=color_trc=bt709:color_primaries=bt709[s];'
        '[1:v]settb=1/30,setpts=N,'
        'setparams=color_trc=bt709:color_primaries=bt709[t];'
        f'[s][t]libplacebo=inputs=2:w={width*3}:h={height}:format=gbrp:'
        f"pos_x='if(eq(idx,0),0,{width})':pos_y=0:"
        f"pos_w='if(eq(idx,0),{width},{width*2})':pos_h={height}:"
        f"crop_x='if(eq(idx,0),{x:.12f},0)':crop_y='if(eq(idx,0),{y:.12f},0)':"
        f"crop_w='if(eq(idx,0),{w:.12f},iw)':crop_h='if(eq(idx,0),{h:.12f},ih)':"
        f'fit_mode=fill:colorspace=gbr:range=pc:{COMMON},format=vulkan[atlas];'
        f"[atlas]libplacebo=w={width}:h={height}:format=yuv420p:"
        f"custom_shader_path='{filter_path(shader)}':colorspace=bt709:range=tv:"
        # The three-panel atlas gives libplacebo a wider display aspect.
        # The shader crops it back to one panel; discard that intermediate
        # pixel aspect after all resizing so players display square pixels.
        f'{COMMON},hwdownload,format=yuv420p,setsar=1[out]'
    )
