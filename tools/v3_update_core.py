"""Version-bound, journalled updates of V3 application files; no business data."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import stat
import sys
import uuid
import zipfile

PRODUCT='ShortDramaPlatform V3'
MAIN='ShortDramaPlatformV3.exe'
ROOT_FILES={MAIN,'build-metadata.json','ffmpeg-runtime.json'}


class UpdateError(RuntimeError):pass


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def write(path,value):
    path=Path(path);temporary=path.with_suffix('.pending')
    with temporary.open('w',encoding='utf8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)


def version(value):
    try:
        parts=value.split('.')
        if len(parts) not in (3,4) or any(not p.isascii() or not p.isdecimal() for p in parts):raise ValueError
        numbers=tuple(map(int,parts))
        if any(not 0<=n<=65535 for n in numbers):raise ValueError
        return numbers+(0,)*(4-len(numbers))
    except (AttributeError,ValueError):raise UpdateError('版本号格式无效')


def relative(name):
    if not isinstance(name,str) or '\\' in name or ':' in name:raise UpdateError('更新清单含非法路径')
    p=PurePosixPath(name)
    if not p.parts or p.is_absolute() or p.as_posix()!=name or any(x in ('.','..') or x.endswith(('.', ' ')) for x in p.parts):
        raise UpdateError('更新清单含非法路径')
    for part in p.parts:
        if any(ord(c)<32 for c in part) or any(c in '<>"|?*' for c in part):raise UpdateError('更新清单含非法路径')
        if part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
            raise UpdateError('更新清单含保留文件名')
    if p.parts[0] not in ROOT_FILES|{'_internal','使用手册','使用说明','使用说明.html'}:
        raise UpdateError('更新清单超出V3程序目录范围：'+name)
    if p.parts[0] in ROOT_FILES|{'使用说明.html'} and len(p.parts)!=1:raise UpdateError('更新清单路径冲突')
    return name


def safe(root,name):
    relative(name);root=Path(root).absolute();p=root/name
    current=p
    while True:
        if current.is_symlink() or current.is_junction():raise UpdateError('程序路径包含链接，不能安全更新：'+str(current))
        if current==root:break
        current=current.parent
    return p


def validate_manifest(m):
    if m.get('schema_version')!=1 or m.get('product')!=PRODUCT:raise UpdateError('更新包产品身份不正确')
    if version(m['base_version'])>=version(m['target_version']):raise UpdateError('更新目标版本必须更新')
    for group in ('base_files','target_files'):
        files=m[group];seen=set()
        for name,entry in files.items():
            relative(name)
            if name.casefold() in seen:raise UpdateError('更新清单文件名冲突')
            seen.add(name.casefold())
            if type(entry['size']) is not int or entry['size']<0:raise UpdateError('更新清单文件大小无效')
            h=entry['sha256']
            if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise UpdateError('更新清单校验值无效')
        if not {MAIN,'build-metadata.json'}<=files.keys():raise UpdateError('更新清单缺少主程序身份')
    old=m['base_files'];new=m['target_files']
    folded={n.casefold():n for n in new}
    if any(folded.get(n.casefold(),n)!=n for n in old):raise UpdateError('不支持仅大小写变化的程序路径')
    changed=sorted(k for k,v in new.items() if old.get(k)!=v)
    removed=sorted(old.keys()-new.keys())
    if m['changed']!=changed or m['removed']!=removed:raise UpdateError('更新差异清单不一致')
    return m


def matches(path,entry):return path.is_file() and path.stat().st_size==entry['size'] and digest(path)==entry['sha256']


def verify(root,files,progress=lambda s:None):
    for i,(name,entry) in enumerate(files.items()):
        if i%100==0:progress(f'核对程序文件 {i}/{len(files)}')
        if not matches(safe(root,name),entry):raise UpdateError('程序文件缺失或已变化，请使用完整安装包修复：'+name)


def running_in(root):
    if os.name!='nt':return []
    import ctypes
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
    ids=(w.DWORD*65536)();needed=w.DWORD()
    if not psapi.EnumProcesses(ids,ctypes.sizeof(ids),ctypes.byref(needed)):raise UpdateError('无法检查运行中的程序，请稍后重试')
    found=[];base=os.path.normcase(str(Path(root).resolve()))+os.sep
    for pid in ids[:needed.value//ctypes.sizeof(w.DWORD)]:
        if not pid or pid==os.getpid():continue
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:continue
        try:
            length=w.DWORD(32768);buffer=ctypes.create_unicode_buffer(length.value)
            if (kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length))
                    and os.path.normcase(buffer.value).startswith(base)
                    and os.path.normcase(buffer.value)!=os.path.normcase(sys.executable)):found.append(pid)
        finally:kernel.CloseHandle(handle)
    return found


def ensure_closed(root):
    if running_in(root):raise UpdateError('V3或其任务仍在运行。请等任务结束并正常退出软件，再点更新；不会强制关闭程序。')


@contextmanager
def exclusive(root):
    p=root/'.v3-update.lock'
    if p.is_symlink() or p.is_junction():raise UpdateError('更新锁路径不安全')
    f=p.open('a+b');locked=False
    try:
        if os.name=='nt':
            import msvcrt
            if p.stat().st_size==0:f.write(b'0');f.flush()
            f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);locked=True
            except OSError:raise UpdateError('已有更新程序正在处理这个安装目录')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
            except OSError:raise UpdateError('已有更新程序正在处理这个安装目录')
        yield
    finally:
        if locked:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)
        f.close()


def registry_location():
    if os.name!='nt':return None
    import winreg
    key=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{BC107354-3709-407F-BD46-15E4D0433BA9}_is1'
    for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key,0,winreg.KEY_READ|view) as k:
                return Path(winreg.QueryValueEx(k,'InstallLocation')[0]),key,view
        except FileNotFoundError:pass
    return None


def registry_snapshot(root):
    found=registry_location()
    if not found or found[0].resolve()!=root.resolve():return None
    import winreg
    values={}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,found[1],0,winreg.KEY_READ|found[2]) as key:
        for name in ('DisplayVersion','DisplayName','Inno Setup: App Version'):
            try:value,kind=winreg.QueryValueEx(key,name);values[name]=[value,kind]
            except FileNotFoundError:pass
    return values


def registry_set(root,values,target=None,product_version=None):
    if values is None:return
    found=registry_location()
    if not found or found[0].resolve()!=root.resolve():raise UpdateError('安装登记位置发生变化，已停止更新')
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,found[1],0,winreg.KEY_SET_VALUE|found[2]) as key:
        for name,(value,kind) in values.items():
            if target is not None:
                display=product_version or target
                value=('短剧推广运营系统 V3 '+display+('（'+target+'）' if product_version else '')) if name=='DisplayName' else display
            winreg.SetValueEx(key,name,0,kind,value)


def restore(root,txn,journal):
    m=validate_manifest(journal['manifest'])
    if journal['root']!=str(root):raise UpdateError('恢复记录与安装位置不一致')
    names=set(m['changed'])|set(m['removed'])|{MAIN}
    # Validate the entire recovery set before replacing anything, including
    # backups. Do not overwrite files someone changed after an interruption.
    for name in names:
        p=safe(root,name);old=m['base_files'].get(name);new=m['target_files'].get(name)
        if old and not matches(safe(txn/'backup',name),old):raise UpdateError('恢复备份不完整，现场已保留：'+name)
        if p.exists() and not any(e and matches(p,e) for e in (old,new)):raise UpdateError('中断后文件又有变化，不能自动覆盖：'+name)
    for name in sorted(names-{MAIN})+[MAIN]:
        p=safe(root,name);old=m['base_files'].get(name)
        if old:
            if matches(p,old):continue
            p.parent.mkdir(parents=True,exist_ok=True)
            temporary=p.with_name(p.name+'.v3-restore-'+uuid.uuid4().hex)
            shutil.copy2(safe(txn/'backup',name),temporary);os.replace(temporary,p)
        elif p.exists():p.unlink()
    registry_set(root,journal.get('registry'))
    journal['state']='rolled_back';write(txn/'journal.json',journal)


def recover(root,progress):
    history=root/'.v3-updates'
    if history.is_symlink() or history.is_junction():raise UpdateError('更新备份目录不安全')
    if not history.exists():return
    for txn in sorted(history.iterdir()):
        if txn.is_symlink() or txn.is_junction():raise UpdateError('更新备份目录不安全')
        path=txn/'journal.json'
        if not path.exists():continue
        j=read(path)
        if j['state']=='applying':
            progress('恢复上次中断的更新文件');restore(root,txn,j)
        elif j['state']=='preparing':
            j['state']='abandoned';write(path,j)
        elif j['state'] not in ('committed','rolled_back','abandoned'):raise UpdateError('更新记录状态无效，请保留现场')


def apply(root,bundle,expected_hash,progress=lambda s:None,hook=lambda s:None):
    root=Path(os.path.abspath(root));bundle=Path(bundle)
    if not root.is_dir() or root.is_symlink() or root.is_junction():raise UpdateError('请选择已有V3程序的真实安装目录')
    safe(root,MAIN);ensure_closed(root)
    if digest(bundle)!=expected_hash:raise UpdateError('更新包校验失败，请重新复制完整更新程序')
    with zipfile.ZipFile(bundle) as archive:
        m=validate_manifest(json.loads(archive.read('manifest.json')))
        required={'manifest.json',*('files/'+n for n in m['changed'])}
        if len(archive.namelist())!=len(required) or set(archive.namelist())!=required:raise UpdateError('更新包文件清单不一致')
        for name in m['changed']:
            item=archive.getinfo('files/'+name)
            if item.file_size!=m['target_files'][name]['size'] or stat.S_ISLNK(item.external_attr>>16):raise UpdateError('更新包文件信息无效')
        with exclusive(root):
            recover(root,progress)
            metadata=safe(root,'build-metadata.json')
            if not metadata.is_file():raise UpdateError('这个目录不是已安装的V3，请先使用完整安装包')
            actual=read(metadata)
            if actual.get('product')!=PRODUCT:raise UpdateError('请选择V3安装目录，不能更新V2')
            if actual.get('version')==m['target_version']:
                verify(root,m['target_files'],progress)
                return {'status':'already_current','version':m['target_version']}
            if actual.get('version')!=m['base_version']:raise UpdateError('此更新包只适用于'+m['base_version']+'，当前为'+str(actual.get('version'))+'；请使用对应更新包或完整安装包。')
            verify(root,m['base_files'],progress)
            names=set(m['changed'])|set(m['removed'])|{MAIN}
            for name in names:
                p=safe(root,name)
                if name not in m['base_files'] and p.exists():raise UpdateError('新增文件位置已被占用，已保留原文件：'+name)
                if p.exists():
                    try:
                        with p.open('r+b'):pass
                    except OSError:raise UpdateError('程序文件被占用或不可写，尚未开始更新：'+name)
            needed=sum(m['target_files'][n]['size'] for n in m['changed'])+sum(m['base_files'][n]['size'] for n in names if n in m['base_files'])+16*1024*1024
            if shutil.disk_usage(root).free<needed:raise UpdateError('安装盘剩余空间不足，尚未替换任何程序文件')
            ensure_closed(root)
            txn=root/'.v3-updates'/(m['base_version']+'_to_'+m['target_version']+'_'+uuid.uuid4().hex)
            txn.mkdir(parents=True);journal={'root':str(root),'state':'preparing','manifest':m,'registry':registry_snapshot(root)}
            write(txn/'journal.json',journal)
            progress('准备更新文件与恢复备份')
            for name in names:
                if name in m['base_files']:
                    dest=safe(txn/'backup',name);dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(safe(root,name),dest)
                    if not matches(dest,m['base_files'][name]):raise UpdateError('备份时程序文件发生变化，未开始替换：'+name)
            for name in m['changed']:
                dest=safe(txn/'staged',name);dest.parent.mkdir(parents=True,exist_ok=True)
                with archive.open('files/'+name) as source,dest.open('xb') as target:shutil.copyfileobj(source,target)
                if not matches(dest,m['target_files'][name]):raise UpdateError('更新文件校验失败，未开始替换：'+name)
            if MAIN not in m['changed']:
                dest=safe(txn/'staged',MAIN);dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(safe(txn/'backup',MAIN),dest)
            ensure_closed(root);hook('prepared')
            # Block normal application launch until every other file and its
            # registration have been validated. Never terminate a process.
            journal['state']='applying';write(txn/'journal.json',journal)
            try:
                os.replace(safe(root,MAIN),txn/'launch-blocked.exe');hook('blocked')
                for name in sorted(names-{MAIN}):
                    p=safe(root,name)
                    if name in m['target_files']:
                        p.parent.mkdir(parents=True,exist_ok=True);os.replace(safe(txn/'staged',name),p)
                    elif p.exists():p.unlink()
                    hook('file:'+name)
                verify(root,{n:m['target_files'][n] for n in m['changed'] if n!=MAIN},progress)
                registry_set(root,journal['registry'],m['target_version'],m.get('target_product_version'))
                source=safe(txn/'staged',MAIN)
                if not matches(source,m['target_files'][MAIN]):raise UpdateError('更新后的主程序校验失败')
                os.replace(source,safe(root,MAIN));hook('activated')
                journal['state']='committed';write(txn/'journal.json',journal)
            except Exception as error:
                progress('更新未完成，正在恢复原程序')
                try:restore(root,txn,journal)
                except Exception as recovery:raise UpdateError('更新失败，自动恢复未完成。请退出软件后重新运行更新程序；备份保留在'+str(txn)+'。原因：'+str(recovery)) from error
                raise UpdateError('更新失败，原程序已恢复：'+str(error)) from error
    return {'status':'updated','version':m['target_version'],'backup':str(txn/'backup'),'changed_files':len(m['changed']),'removed_files':len(m['removed'])}
