"""Small real capability checks, cached for one application process.

Checking the encoder list is insufficient: drivers can reject actual encoding,
decoding or Vulkan. No business files or device settings are changed here.
"""
from functools import lru_cache
import os
from pathlib import Path
import subprocess
import tempfile


def _run(ff, args):
    try:
        p=subprocess.run([str(ff),'-hide_banner','-nostdin','-v','error','-n',*map(str,args)],
                         capture_output=True,timeout=30,
                         **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        return p.returncode,p.stdout,p.stderr.decode('utf8','replace')[-2000:]
    except (OSError,subprocess.TimeoutExpired) as e:
        return -1,b'',str(e)


def capabilities(ff):
    path=Path(ff).resolve();s=path.stat()
    return dict(_probe(str(path),s.st_mtime_ns,s.st_size))


@lru_cache(maxsize=8)
def _probe(ff, modified, size):
    from server.ffmpeg_templates.encoding import cache_encode
    from server.ffmpeg_finals.gpu_transfer import transfer_graph
    result={'hevc_cache':False,'vulkan_h264':False,
            'vulkan_hevc':False,'vulkan_transfer':False,'diagnostics':{}}
    with tempfile.TemporaryDirectory(prefix='v3-gpu-check-') as folder:
        root=Path(folder)
        for kind in ('h264','hevc'):
            path=root/(kind+'.mkv')
            encoding=(['-c:v','h264_nvenc','-pix_fmt','yuv420p'] if kind=='h264'
                      else cache_encode('hevc_nvenc'))
            code,_,error=_run(ff,['-f','lavfi','-i','testsrc2=s=320x240:r=30',
                                 '-frames:v','3','-an',*encoding,path])
            result['diagnostics'][kind]={'returncode':code,'diagnostic':error}
            if not code:
                vcode,_,verror=_run(ff,[*vulkan_args(),*vulkan_decode_args(),'-i',path,
                                      '-map','0:v:0','-f','null','-'])
                result['vulkan_'+kind]=vcode==0
                result['diagnostics']['vulkan_'+kind]={'returncode':vcode,'diagnostic':verror}
        graph=transfer_graph(root,{'source_width':32,'source_height':64,'frames':1},32,64)
        script=root/'transfer.ffgraph';script.write_text(graph,encoding='utf8')
        code,data,error=_run(ff,[*vulkan_args(),'-filter_complex_threads','2',
            '-f','lavfi','-i','color=c=white:s=32x64:r=30,format=gbrp',
            '-f','lavfi','-i','color=c=white:s=64x64:r=30,format=gbrp',
            '-filter_complex_script',script,'-map','[out]','-frames:v','1',
            '-pix_fmt','yuv420p','-c:v','rawvideo','-f','rawvideo','pipe:1'])
        result['vulkan_transfer']=code==0 and data==b'\xeb'*(32*64)+b'\x80'*(32*64//2)
        result['diagnostics']['vulkan_transfer']={'returncode':code,'diagnostic':error}
        result['hevc_cache']=result['vulkan_hevc'] and result['vulkan_transfer']
    return result


def vulkan_args():
    return ['-init_hw_device','vulkan=vk:NVIDIA','-filter_hw_device','vk']


def vulkan_decode_args():
    return ['-hwaccel','vulkan','-hwaccel_device','vk','-hwaccel_output_format','vulkan']


def device_failure(error):
    """Only hardware failures permit CPU fallback; bad media must still fail."""
    text=str(error).lower()
    # FFmpeg's stream mapping can mention Vulkan/libplacebo even when the
    # actual failure is a corrupt input packet.
    if any(marker in text for marker in (
        'invalid nal unit','error while decoding stream','corrupt decoded frame',
        'error submitting a packet to the decoder','invalid data found when processing input',
    )):
        return False
    return any(marker in text for marker in (
        'vulkan', 'libplacebo', 'hwupload', 'hwdownload',
        'cuvid', 'cuda', 'device creation failed', 'failed setup for format',
        'no device available for decoder', 'hardware accelerator failed',
    ))
