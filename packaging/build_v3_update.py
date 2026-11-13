"""Build a small standalone update EXE from verified V3 release directories."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.v3_update_core import PRODUCT,MAIN,UpdateError,digest,read,relative,validate_manifest,version
ROOT=Path(__file__).resolve().parents[1]


def inventory(root, cache=None):
    result={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or p.is_junction():raise UpdateError('构建目录不允许包含链接')
        if p.is_file():
            name=relative(p.relative_to(root).as_posix());result[name]={'size':p.stat().st_size,'sha256':cache.digest(p) if cache else digest(p)}
    return result


def make_manifest(base,target,cache=None):
    a=read(base/'build-metadata.json');b=read(target/'build-metadata.json')
    if a.get('product')!=PRODUCT or b.get('product')!=PRODUCT:raise UpdateError('只能从V3正式构建生成更新包')
    old=inventory(base,cache);new=inventory(target,cache)
    changed=sorted(k for k,v in new.items() if old.get(k)!=v);removed=sorted(old.keys()-new.keys())
    # Small releases reuse exactly the same dependencies and fixed libraries.
    # Python's base zip belongs to the frozen program and may change with imports.
    def supported(name):return name in {MAIN,'build-metadata.json','使用说明.html','_internal/base_library.zip'} or name.startswith(('_internal/dist/','使用手册/','使用说明/'))
    if any(not supported(n) for n in changed+removed):raise UpdateError('本次改变了运行组件或固定素材，请制作完整安装包：'+', '.join(n for n in changed+removed if not supported(n)))
    return validate_manifest({'schema_version':1,'product':PRODUCT,'base_version':a['version'],'target_version':b['version'],'target_product_version':b.get('product_version',''),
                              'base_files':old,'target_files':new,'changed':changed,'removed':removed})


def payload(manifest,target,path):
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
        for name in manifest['changed']:archive.write(target/name,'files/'+name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-version',required=True)
    p.add_argument('--version',required=True)
    p.add_argument('--existing-target',action='store_true',help='Use an existing verified target instead of rebuilding application code')
    p.add_argument('--inventory-cache',type=Path,help='Builder-only stat-validated hash cache; never used by installed updater')
    args=p.parse_args();version(args.base_version);version(args.version)
    if sys.version_info[:3]!=(3,12,10):raise UpdateError('请使用已验证的Windows CPython3.12.10构建更新程序')
    if version(args.base_version)>=version(args.version):p.error('target version must be newer')
    base=ROOT/'packaging/releases'/args.base_version/'ShortDramaPlatformV3'
    target=ROOT/'packaging/releases'/args.version/'ShortDramaPlatformV3'
    if not base.is_dir():raise UpdateError('缺少基础版本完整构建，请保留已发布的构建目录')
    if not args.existing_target:
        if target.parent.exists():raise UpdateError('目标版本已存在；请使用新版本号，或明确使用--existing-target')
        node=shutil.which('node') or str(Path(os.environ.get('ProgramFiles','C:/Program Files'))/'nodejs/node.exe')
        subprocess.run([node,str(ROOT/'node_modules/typescript/bin/tsc'),'--noEmit','-p',str(ROOT/'tsconfig.release.json')],cwd=ROOT,check=True)
        subprocess.run([node,str(ROOT/'tools/cover-editor-preview/build.cjs'),'--production'],cwd=ROOT,check=True)
        subprocess.run([node,str(ROOT/'node_modules/vite/bin/vite.js'),'build'],cwd=ROOT,check=True)
        # Build only the program directory; do not compile a multi-GB installer.
        subprocess.run([sys.executable,str(ROOT/'packaging/build_v3.py'),'--version',args.version],cwd=ROOT,check=True)
    if not target.is_dir():raise UpdateError('缺少目标版本构建目录')
    cache=None
    if args.inventory_cache:
        sys.path.insert(0,str(ROOT/'packaging'))
        from release_hash_cache import HashCache
        cache=HashCache(args.inventory_cache)
    manifest=make_manifest(base,target,cache)
    if cache:cache.save()
    if manifest['base_version']!=args.base_version or manifest['target_version']!=args.version:raise UpdateError('构建身份与命令版本不一致')
    out=ROOT/'packaging/updates'/(args.base_version+'_to_'+args.version);out.mkdir(parents=True,exist_ok=False)
    work=out/'build';work.mkdir();delivery=out/'交付';delivery.mkdir()
    package=work/'update-payload.zip';payload(manifest,target,package)
    descriptor={'base_version':args.base_version,'target_version':args.version,'product_version':read(target/'build-metadata.json').get('product_version',''),'sha256':digest(package)}
    descriptor_path=work/'update-bundle.json';descriptor_path.write_text(json.dumps(descriptor),encoding='utf8')
    target_identity=read(target/'build-metadata.json')
    product_version=target_identity.get('product_version','')
    name='ShortDramaPlatform_V3_Update_'+(product_version+'_' if product_version else '')+args.base_version+'_to_'+args.version
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed','--name',name,
                    '--paths',str(ROOT),'--icon',str(ROOT/'packaging/assets/v2-application-icon.ico'),
                    '--add-data',str(package)+os.pathsep+'.','--add-data',str(descriptor_path)+os.pathsep+'.',
                    '--distpath',str(delivery),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),
                    str(ROOT/'tools/v3_update_app.py')],cwd=ROOT,check=True)
    exe=delivery/(name+'.exe')
    result={**descriptor,'product_version':product_version,'release_id':args.version,'file':exe.name,'bytes':exe.stat().st_size,'sha256':digest(exe),
            'changed_files':len(manifest['changed']),'removed_files':len(manifest['removed']),
            'changed_bytes':sum(manifest['target_files'][n]['size'] for n in manifest['changed']),
            'source_hashes':{n:digest(ROOT/n) for n in ('tools/v3_update_core.py','tools/v3_update_app.py','packaging/build_v3_update.py')},
            'fixed_resources_reused':True,'builder':'packaging/build_v3_update.py'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (delivery/'更新信息.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (delivery/'SHA256SUMS.txt').write_text(result['sha256']+'  '+exe.name+'\n',encoding='utf8')
    (delivery/'先看这里.txt').write_text(f'''V3 产品版本 {product_version} · 轻量更新 {args.base_version} → {args.version}

先等任务结束，正常退出V3，双击同目录的更新EXE。
程序会寻找已有V3安装位置；也可以手动选择包含ShortDramaPlatformV3.exe的目录。
只适用于{args.base_version}。已是{args.version}时会核对文件并提示无需更新。
不能用于首次安装或其他基础版本；版本不同请使用对应更新包或完整安装包。

只替换变化的程序、界面和说明文件，固定素材和运行组件沿用原安装。
更新前检查版本和原文件，保存备份；失败自动恢复，中断后重新运行同一更新程序恢复再继续。
不会强制关闭软件，不启动业务队列，不迁移或回退账号、素材、模板、成片及数据库。
备份留在安装目录的.v3-updates中，不自动清理；不要手动拷回旧程序覆盖新版业务库。
旧完整安装器的卸载记录不包含轻量包新加的文件；卸载后新增说明、界面文件和恢复备份可能保留。
完整安装包仍用于新电脑、版本不匹配、程序损坏、固定素材或运行组件改变的情况。
大小约{result['bytes']/1e6:.1f}MB；变化文件{len(manifest['changed'])}个，移除旧程序文件{len(manifest['removed'])}个。
''',encoding='utf-8-sig')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
