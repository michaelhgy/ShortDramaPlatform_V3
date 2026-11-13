"""Durable publishing images, independent of source files and production cleanup."""
import base64
import binascii
import hashlib
import io
import os
import tempfile
import re
import warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES=15*1024*1024

class PublishCoverStore:
    def __init__(self,root):self.root=Path(root)

    def path(self,image_id):
        if not isinstance(image_id,str) or not re.fullmatch(r'[a-f0-9]{64}',image_id):
            raise ValueError('自定义封面编号无效，请重新选择图片')
        path=self.root/(image_id+'.jpg')
        if not path.is_file():raise ValueError('已保存的自定义封面图片缺失，请重新选择图片')
        return path

    def import_image(self,data_url):
        if not isinstance(data_url,str) or len(data_url)>MAX_BYTES*4//3+128:
            raise ValueError('封面图片最大15MB')
        header,sep,encoded=data_url.partition(',')
        if not sep or header not in ('data:image/jpeg;base64','data:image/png;base64','data:image/webp;base64'):
            raise ValueError('请选择JPG、PNG或WebP封面图片')
        try:
            raw=base64.b64decode(encoded,validate=True)
            if not raw or len(raw)>MAX_BYTES:raise ValueError('封面图片为空或超过15MB')
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in ('JPEG','PNG','WEBP'):raise ValueError('请选择JPG、PNG或WebP封面图片')
                    if source.width*source.height>40_000_000:raise ValueError('封面图片分辨率过大，最多4000万像素')
                    image=ImageOps.exif_transpose(source).convert('RGBA')
                    background=Image.new('RGBA',image.size,'white')
                    image=Image.alpha_composite(background,image).convert('RGB')
                    image.thumbnail((2160,2160),Image.Resampling.LANCZOS)
                    stream=io.BytesIO();image.save(stream,format='JPEG',quality=95)
        except (binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
            raise ValueError('图片无法读取，请选择有效的JPG、PNG或WebP图片') from exc
        content=stream.getvalue();key=hashlib.sha256(content).hexdigest()
        self.root.mkdir(parents=True,exist_ok=True)
        target=self.root/(key+'.jpg')
        if target.exists():
            if target.read_bytes()!=content:raise ValueError('封面图片保存异常，请重试')
        else:
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=self.root,suffix='.tmp',delete=False) as output:
                    temporary=Path(output.name);output.write(content)
                os.replace(temporary,target)
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
        return {'id':key,'url':f'/api/v2/publishing/covers/{key}.jpg','width':image.width,'height':image.height}
