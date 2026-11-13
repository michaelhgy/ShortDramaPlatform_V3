"""One picture encode from completed template pixels; no asset-library reads."""
from pathlib import Path
from server.ffmpeg_diagnostics import event, current
from copy import deepcopy
from server.ffmpeg_templates.precompose import main_graph, transfer_apply
from server.ffmpeg_templates.encoding import delivery_encode
from .pipeline import Pipeline, namespace
from server.ffmpeg_templates.renderer import save


def ending(cache,frames):
    if cache.get('loop_frames'):return None
    for tail in reversed(list(cache.get('tails',{}).values())):
        t=tail['transition'];b=t['boundary_frame'];d=t['duration_frames']
        if t['start_frame']<frames<b+d:
            n=max(0,min(d,frames-b));n=n//2*2
            return {**tail,'kind':'ending','start':t['start_frame'],'end':min(t['end_frame'],frames),'duration':n}
    return None


def repeated_parts(cache,frames):
    """Repeat references, not rendered pixels. Footage/audio keep their clock."""
    cycle=cache.get('loop_frames')
    if not cycle:
        if frames>cache['frames']:raise ValueError('模板缓存长度不足且未声明可循环')
        return [x for x in cache['parts'] if x['start']<frames]
    result=[]
    for offset in range(0,frames,cycle):
        for original in cache['parts']:
            if offset+original['start']>=frames:break
            item=deepcopy(original);item['start']+=offset;item['end']+=offset
            if 'render_start' in item:item['render_start']+=offset
            result.append(item)
    return result


def branch_graph(root,item,source,inputs,prefix):
    index=sum(x=='-i' for x in inputs)
    if item['kind']=='affine':
        inputs+=['-threads','4','-i',str(root/item['file'])]
        return transfer_apply(source,f'{index}:v',prefix,prefix+'out'),prefix+'out'
    folder=root/item['directory'];inputs+=['-threads','4','-i',str(folder/item['base']),*item['inputs']]
    graph=transfer_apply(source,f'{index}:v',prefix,prefix+'rgb')+f';[{prefix}rgb]format=yuv420p[{prefix}base];'
    bindings={'0:v':prefix+'base','out':prefix+'ready'}
    bindings.update({f'{k+1}:v':f'{index+1+k}:v' for k in range(sum(x=='-i' for x in item['inputs']))})
    graph+=namespace((folder/item['runtime']).read_text(encoding='utf8'),prefix+'fx_',bindings)
    graph+=f';[{prefix}ready]format=gbrp[{prefix}out]'
    return graph,prefix+'out'


def ending_graph(renderer,job,root,item,count,index):
    n=item['duration'];branches=item['branches'] if n else item['branches'][:1]
    inputs=source_input(job,item['start']);graphs=[main_graph(count,source_fps=job.get('source_fps'))]
    labels=[f'input{i}' for i in range(len(branches))]
    graphs.append('[main]'+(f'split={len(branches)}'+''.join(f'[{x}]' for x in labels) if len(branches)>1 else 'null[input0]'))
    outputs=[]
    for i,(branch,label) in enumerate(zip(branches,labels)):
        g,out=branch_graph(root,branch,label,inputs,f'br{i}_');graphs.append(g);outputs.append(out)
    if not n:graphs.append(f'[{outputs[0]}]format=yuv420p[out]');return inputs,';'.join(graphs)
    t=item['transition'];start=t['boundary_frame']-n//2
    commands=[];through=len(branches)==3
    for frame in range(count):
        local=item['start']+frame-start+1
        if through:
            weights={'fadea':1-max(0,min(1,local/(n//2))),
                     'fadeb':1-max(0,min(1,(local-n//2)/(n//2))), 'choose':1 if local<n//2 else 0}
        else:weights={'fade':max(0,min(1,1-local/n))}
        commands.append(f'{max(0,(frame-.0001)/30):.9f} '+','.join(f'blend@{k} all_opacity {v:.12f}' for k,v in weights.items())+';')
    file=renderer.folder/f'ending_{index}.txt';file.write_text('\n'.join(commands),encoding='utf8')
    path=file.resolve().as_posix().replace(':','\\:').replace("'","'\\''")
    graphs.append(f"[{outputs[0]}]sendcmd=f='{path}'[commanded]")
    if through:
        graphs += [f'[{outputs[2]}]split=2[x][y]',
                   '[commanded][x]blend@fadea=all_mode=normal:all_opacity=1[a]',
                   f'[y][{outputs[1]}]blend@fadeb=all_mode=normal:all_opacity=1[b]',
                   '[a][b]blend@choose=all_mode=normal:all_opacity=1,format=yuv420p[out]']
    else:graphs.append(f'[commanded][{outputs[1]}]blend@fade=all_mode=normal:all_opacity=1,format=yuv420p[out]')
    return inputs,';'.join(graphs)


def listing(folder,name,paths):
    path=folder/(name+'.txt')
    path.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in paths),encoding='utf8')
    return path


def source_input(job,start=0):
    job['_timeline_start_frame'] = start
    if job.get('still_image'):return ['-loop','1','-framerate','30','-i',job['source_path']]
    return ['-threads','2','-ss',str(start/30),'-i',job['source_path']]


def audio_args(job):
    if job.get('has_audio'):
        return ['-map','0:a:0','-c:a','aac','-b:a','192k','-af','aresample=async=1:first_pts=0,apad']
    return ['-an']


def encode_command(p,name,inputs,graph,frames,output,job,audio=False,device_args=(),timeline_frames=None):
    from .insertion import has_insertions, bind_timeline
    if has_insertions(job):
        source_count = min(timeline_frames if timeline_frames is not None else frames, job['frames'] - job.get('_timeline_start_frame', 0))
        inputs, graph, audio_label = bind_timeline(inputs, graph, job, source_count, audio=audio and job['has_audio'])
        sound = ['-map', f'[{audio_label}]', '-c:a', 'aac', '-b:a', '192k'] if audio and job['has_audio'] else ['-an']
    else:
        sound = audio_args(job) if audio else ['-an']
    script=p.r.folder/(name+'.ffgraph');script.write_text(graph,encoding='utf8')
    args=[*device_args,'-filter_complex_threads','8',*inputs,'-filter_complex_script',script,'-map','[out]',
          *sound,'-frames:v',frames,'-t',str(frames/30),*delivery_encode(p.r.encoder),output]
    p.command(name,args,frames,'复用已完成模板，编码成片')


def render_cached(renderer,job,cache):
    from .insertion import has_insertions
    frames=job['frames'];root=Path(cache['root']);p=Pipeline(renderer,frames,load_assets=False)
    p.acceleration={'transfer':'cpu','reason':'source_dependent_effects'}
    # Pipeline's command runner is reused; this path never uses its old layer methods.
    p.total=frames*2
    relevant=repeated_parts(cache,frames)
    tail=ending(cache,frames)
    output=renderer.folder/'final.mp4'
    if all(x['kind']=='affine' for x in relevant) and tail is None:
        file=listing(renderer.folder,'completed_template',[root/x['file'] for x in relevant])
        hardware=getattr(renderer,'hardware',{})
        from .gpu_transfer import supports,transfer_graph
        p.acceleration={'transfer':'cpu','reason':'device_unavailable' if not hardware.get('vulkan_transfer')
                        else 'source_format' if not supports(job) else 'cpu_selected'}
        if not has_insertions(job) and hardware.get('vulkan_transfer') and supports(job) and getattr(renderer,'transfer_backend','vulkan')=='vulkan':
            from server.ffmpeg_hardware import vulkan_args,vulkan_decode_args,device_failure
            graph=transfer_graph(renderer.folder,job)
            cache_gpu=hardware.get('vulkan_hevc') and all(x.get('codec')=='hevc' for x in relevant)
            source_gpu=hardware.get('vulkan_'+str(job.get('source_codec_name')),False)
            args=[*(vulkan_decode_args() if source_gpu else []),*source_input(job),
                  *(vulkan_decode_args() if cache_gpu else []),
                  '-threads','8','-f','concat','-safe','0','-i',file]
            gpu_output=renderer.folder/'final_gpu.mp4'
            try:
                if current(): current().update_context(acceleration={'transfer':'vulkan','cache_decode':'vulkan' if cache_gpu else 'cpu','source_decode':'vulkan' if source_gpu else 'cpu'})
                encode_command(p,'compose_gpu',args,graph,frames,gpu_output,job,audio=True,device_args=vulkan_args())
                p.acceleration={'transfer':'vulkan','cache_decode':'vulkan' if cache_gpu else 'cpu',
                                'source_decode':'vulkan' if source_gpu else 'cpu','scale':'vulkan'}
                return gpu_output,p
            except RuntimeError as error:
                if not device_failure(error):raise
                # Keep the attempted output and logs; never overwrite them.
                event('acceleration_fallback', error=str(error), previous='vulkan', fallback='cpu_transfer')
                save(renderer.folder/'acceleration_fallback.json',{'diagnostic':str(error),'fallback':'cpu_transfer'})
                p.acceleration={'transfer':'cpu','reason':'gpu_runtime_failure'}
        if has_insertions(job):
            p.acceleration={'transfer':'cpu','reason':'insertion_timeline','encoding':renderer.encoder}
        if current(): current().update_context(acceleration=p.acceleration)
        graph=main_graph(frames,source_fps=job.get('source_fps'))+';'+transfer_apply('main','1:v','a_','rgb')+';[rgb]format=yuv420p[out]'
        args=[*source_input(job),'-threads','8','-f','concat','-safe','0','-i',file]
        encode_command(p,'compose',args,graph,frames,output,job,audio=True)
    else:
        if tail:
            relevant=[x for x in relevant if x['end']<=tail['start'] or x['start']>=tail['end']]
            relevant.append(tail);relevant.sort(key=lambda x:x['start'])
        grouped=[]
        for item in relevant:
            if item['kind']=='affine' and grouped and grouped[-1]['kind']=='affine_group' and grouped[-1]['end']==item['start']:
                grouped[-1]['items'].append(item);grouped[-1]['end']=item['end']
            elif item['kind']=='affine':grouped.append({'kind':'affine_group','items':[item],'start':item['start'],'end':item['end']})
            else:grouped.append(item)
        if current(): current().update_context(acceleration=p.acceleration)
        rendered=[]
        for i,item in enumerate(grouped):
            start=item['start'];count=min(item['end'],frames)-start
            target=renderer.folder/f'compiled_part_{i:03d}.mp4'
            if item['kind']=='ending':
                args,graph=ending_graph(renderer,job,root,item,count,i)
            elif item['kind']=='affine_group':
                file=listing(renderer.folder,f'completed_template_{i}',[root/x['file'] for x in item['items']])
                args=[*source_input(job,start),'-threads','8','-f','concat','-safe','0','-i',file]
                graph=main_graph(count,source_fps=job.get('source_fps'))+';'+transfer_apply('main','1:v','a_','rgb')+';[rgb]format=yuv420p[out]'
            else:
                folder=root/item['directory'];n=item['render_frames'];a=item['trim'][0]
                args=[*source_input(job,item['render_start']),'-threads','8','-i',folder/item['base'],*item['inputs']]
                graph=main_graph(n,source_fps=job.get('source_fps'))+';'+transfer_apply('main','1:v','a_','rgb')+';[rgb]format=yuv420p[preparedbase];'
                runtime=(folder/item['runtime']).read_text(encoding='utf8')
                count_inputs=sum(x=='-i' for x in item['inputs'])
                bindings={'0:v':'preparedbase','out':'rendered'}
                bindings.update({f'{k+1}:v':f'{k+2}:v' for k in range(count_inputs)})
                graph+=namespace(runtime,'ready_',bindings)
                graph+=f';[rendered]trim=start_frame={a}:end_frame={a+count},settb=1/30,setpts=N[out]'
            encode_command(p,f'compose{i:03d}',args,graph,count,target,job,
                           timeline_frames=item.get('render_frames') if item['kind'] not in ('ending','affine_group') else None)
            rendered.append(target)
        output=p.mux(rendered,job)
    return output,p
