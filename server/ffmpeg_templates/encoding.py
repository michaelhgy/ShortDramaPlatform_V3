"""Bounded video sizes, calibrated against the user's existing H.264 finals."""


def cache_encode(encoder):
    # RGB transfer contains colour and transmission side by side. Keep 4:4:4
    # chroma for thin borders/feathering, but do not store lossless full frames.
    if encoder=='hevc_nvenc':
        return ['-c:v','hevc_nvenc','-preset','p4','-rc','vbr','-b:v','8M',
                '-maxrate','12M','-bufsize','16M','-pix_fmt','yuv444p','-profile:v','rext']
    base=(['-c:v','h264_nvenc','-preset','p4','-rc','vbr'] if encoder=='h264_nvenc'
          else ['-c:v','libx264','-preset','veryfast'])
    return base+['-b:v','8M','-maxrate','12M','-bufsize','16M','-pix_fmt','yuv444p',
                 '-profile:v','high444p' if encoder=='h264_nvenc' else 'high444']


def delivery_encode(encoder):
    base=(['-c:v','h264_nvenc','-preset','p4','-rc','vbr'] if encoder=='h264_nvenc'
          else ['-c:v','libx264','-preset','veryfast'])
    return base+['-b:v','2500k','-maxrate','4000k','-bufsize','5000k','-pix_fmt','yuv420p','-r','30',
                 '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart']
