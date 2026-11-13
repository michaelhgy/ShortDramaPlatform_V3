"""Names are search hints. A confirmed platform ID is the persistent binding."""
import re
import unicodedata
from difflib import SequenceMatcher


def normalized_name(value):
    text=unicodedata.normalize('NFKC',str(value or '')).casefold()
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith(('P','S')))


def search_terms(names):
    full=[]; fallback=[]
    for name in names:
        name=str(name or '').strip()
        if not name:continue
        compact=normalized_name(name)
        spaced=' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',name),flags=re.UNICODE))
        for value in (compact,spaced,name):
            if value and value not in full:full.append(value)
        if len(compact)>6:
            for value in (compact[:6],compact[-6:]):
                if value not in fallback:fallback.append(value)
    return full+fallback[:4]


def rank_candidates(candidates,names):
    normalized=[normalized_name(n) for n in names if normalized_name(n)]
    unique={str(c['id']):c for c in candidates if c.get('id')}
    rows=[]
    for candidate in unique.values():
        key=normalized_name(candidate.get('name'))
        score=max((SequenceMatcher(None,key,n).ratio() for n in normalized),default=0)
        rows.append({**candidate,'score':round(score*100),'exact':bool(key and key in normalized)})
    rows.sort(key=lambda c:(not c['exact'],-c['score'],not c.get('usable',False),c.get('name','')))
    # Duplicate exact names are ambiguous even if just one is currently usable.
    exact=[c for c in rows if c['exact']]
    auto=exact[0] if len(exact)==1 and exact[0].get('usable') is True else None
    return rows,auto
