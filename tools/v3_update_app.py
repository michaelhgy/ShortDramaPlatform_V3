"""Small standalone updater UI and a deterministic silent acceptance entry."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import queue
from tools.v3_update_core import apply,registry_location,read


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install-dir',type=Path)
    parser.add_argument('--silent',action='store_true')
    parser.add_argument('--result',type=Path)
    args=parser.parse_args()
    resources=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    descriptor=read(resources/'update-bundle.json')
    bundle=resources/'update-payload.zip'
    if args.silent:
        if not args.install_dir or not args.result:parser.error('--silent requires --install-dir and --result')
        try:result=apply(args.install_dir,bundle,descriptor['sha256'])
        except Exception as e:result={'status':'error','error':str(e)}
        args.result.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        return 1 if result['status']=='error' else 0
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    window=tk.Tk();window.title('V3 轻量更新');window.geometry('660x390');window.resizable(False,False)
    frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='短剧推广运营系统 V3 · 轻量更新',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text=f"产品版本：{descriptor.get('product_version') or 'V3'}    适用发布编号：{descriptor['base_version']}  →  {descriptor['target_version']}",padding=(0,12)).pack(anchor='w')
    ttk.Label(frame,text='先等当前任务结束，再正常退出V3。更新失败会恢复原程序文件。\n账号、素材、模板、成片等业务数据保持原位。',justify='left').pack(anchor='w')
    found=registry_location()
    suggested=args.install_dir or (found[0] if found else Path(os.environ.get('LOCALAPPDATA',''))/'ShortDramaPlatform_V3')
    selected=tk.StringVar(value=str(suggested));status=tk.StringVar(value='请确认V3安装目录，然后点击“开始更新”。')
    row=ttk.Frame(frame);row.pack(fill='x',pady=18)
    field=ttk.Entry(row,textvariable=selected,width=63);field.pack(side='left',fill='x',expand=True)
    def browse():
        folder=filedialog.askdirectory(parent=window,title='选择V3安装目录')
        if folder:selected.set(folder)
    choose=ttk.Button(row,text='选择目录',command=browse);choose.pack(side='right',padx=(8,0))
    ttk.Label(frame,textvariable=status,wraplength=600,justify='left').pack(anchor='w',fill='x')
    events=queue.Queue();active=False
    def worker():
        try:
            value=apply(Path(selected.get()),bundle,descriptor['sha256'],lambda s:events.put(('progress',s)))
            events.put(('done',value))
        except Exception as e:events.put(('error',str(e)))
    def start():
        nonlocal active
        active=True;button.config(state='disabled');choose.config(state='disabled');field.config(state='disabled')
        status.set('正在检查版本和程序文件，请稍候…');threading.Thread(target=worker,daemon=False).start()
    button=ttk.Button(frame,text='开始更新',command=start);button.pack(anchor='e',pady=20)
    def poll():
        nonlocal active
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='progress':status.set(value);continue
                active=False;button.config(state='normal');choose.config(state='normal');field.config(state='normal')
                if kind=='error':status.set(value);messagebox.showerror('未完成更新',value,parent=window)
                else:
                    text=('当前程序已是此更新包的目标版本，无需重复更新。' if value['status']=='already_current' else '更新完成，现在可以从原快捷方式启动V3。恢复备份已保留。')
                    status.set(text);messagebox.showinfo('更新完成',text,parent=window)
        except queue.Empty:pass
        window.after(100,poll)
    def close():
        if active:messagebox.showinfo('正在更新','请等更新或自动恢复完成后再关闭。',parent=window)
        else:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);poll();window.mainloop();return 0


if __name__=='__main__':raise SystemExit(main())
