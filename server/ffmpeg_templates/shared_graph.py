"""Share identical fixed-input work between the two template transfer branches.

Only whitelisted preparation filters are folded. Named/commanded filters and
picture mixes keep their original order and arithmetic. No persistent cache
format, quality setting, timeline or effect parameter is changed here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re


PREPARATION = frozenset({'trim','settb','setpts','format','fps','scale','setsar',
                         'crop','split','alphamerge','colorchannelmixer',
                         'alphaextract','extractplanes','lut','lutrgb','loop','null'})


def tokens(text, delimiter):
    result=[];start=0;quoted=False;escaped=False
    for i,c in enumerate(text):
        if escaped:escaped=False;continue
        if c=='\\':escaped=True;continue
        if c=="'":quoted=not quoted
        elif c==delimiter and not quoted:
            result.append(text[start:i].strip());start=i+1
    if quoted:raise ValueError('Unclosed FFmpeg filter quote')
    result.append(text[start:].strip())
    return result


def share(inputs, graph, decoder_threads=2):
    """Return equivalent inputs/graph plus an inspectable work-reduction record."""
    groups=[];begin=0;index=0;aliases={};seen_inputs={};flat=[]
    values=list(map(str,inputs))
    while index<len(values):
        if values[index]!='-i':index+=1;continue
        group=values[begin:index+2]
        if len(group)<2:raise ValueError('Missing FFmpeg input path')
        key=tuple(group)
        if key not in seen_inputs:
            number=len(groups);seen_inputs[key]=number
            # Avoid one automatic decoder thread pool per identical input.
            if decoder_threads and '-threads' not in group:
                group=['-threads',str(decoder_threads),*group]
            groups.append(group);flat+=group
        aliases[f'{len(aliases)}:v']=f'{seen_inputs[key]}:v'
        index+=2;begin=index
    if begin!=len(values):raise ValueError('Unexpected trailing input options')
    original_count=len(aliases);nodes=[];seen={};original_nodes=0
    for statement in tokens(graph,';'):
        if not statement:continue
        original_nodes+=1
        head=re.match(r'^(?:\[[^\]]+\])*',statement)[0]
        tail=re.search(r'(?:\[[^\]]+\])+$',statement)
        if not tail:raise ValueError('Every shared graph chain needs explicit output labels')
        ins=[aliases[x] for x in re.findall(r'\[([^\]]+)\]',head)]
        outs=re.findall(r'\[([^\]]+)\]',tail[0])
        filters=statement[len(head):tail.start()].strip()
        names=[part.split('=',1)[0] for part in tokens(filters,',')]
        eligible=bool(ins) and all(name in PREPARATION for name in names)
        signature=(tuple(ins),filters,len(outs))
        if eligible and signature in seen:
            labels=seen[signature]
        else:
            labels=[f'sh{len(nodes)}_{i}' for i in range(len(outs))]
            nodes.append((ins,filters,labels))
            if eligible:seen[signature]=labels
        aliases.update(zip(outs,labels))
    # Explicit splits share frames while preserving independent consumers.
    target=aliases['out'];counts=Counter(x for ins,_,_ in nodes for x in ins)
    counts[target]+=1;used=defaultdict(int);parts=[]
    def consume(label):
        i=used[label];used[label]+=1
        return label if counts[label]==1 else f'{label.replace(":","_")}_use{i}'
    def split(label):
        if counts[label]>1:
            parts.append(f'[{label}]split={counts[label]}'+''.join(f'[{label.replace(":","_")}_use{i}]' for i in range(counts[label])))
        elif counts[label]==0:parts.append(f'[{label}]nullsink')
    for i in range(len(groups)):split(f'{i}:v')
    for ins,filters,outs in nodes:
        parts.append(''.join(f'[{consume(x)}]' for x in ins)+filters+''.join(f'[{x}]' for x in outs))
        for label in outs:split(label)
    parts.append(f'[{consume(target)}]null[out]')
    return flat,';'.join(parts),{'inputs_before':original_count,'inputs_after':len(groups),
                              'chains_before':original_nodes,'chains_after':len(nodes),
                              'decoder_threads':decoder_threads}
