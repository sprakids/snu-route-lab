"""Independently compare fixed vehicle identities, paired dispatches and timing across runs."""
from collections import Counter, defaultdict
from pathlib import Path
import gzip
import json
import math

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'261124160531'

def read(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf8') as stream:
        return json.load(stream)

def verify(key):
    old=read(BASE/'viewer-data'/f'{key}.json.gz')
    common=read(BASE/'viewer-data/common.json.gz')
    hot=common['hot_nodes']
    routes={'shuttle-41841':hot['admin_snu'],'shuttle-daehak':hot['admin_daehak']}
    template=None
    result={}
    for condition in ('supply','release','combined'):
        r=read(HERE/'runs'/condition/key/f'{key}.json.gz')
        old_windows={vid:(node,op,dep,cap) for node,vid,op,dep,cap in old['door_windows']}
        new_windows={vid:(node,op,dep,cap) for node,vid,op,dep,cap in r['door_windows']}
        mapped={v:(rid,clock,dep,lead,timed) for v,rid,clock,dep,lead,timed in r['return_template_assignments']}
        if condition=='supply':
            template=new_windows
        elif condition=='combined':
            assert new_windows==template
        else:
            assert not mapped
        assert old_windows.keys()==new_windows.keys()
        pairs=defaultdict(list)
        for vid,(node,op,dep,cap) in old_windows.items():
            n,o,d,c=new_windows[vid]
            assert n==node and c==cap and (o<d if condition!='release' else o<=d)
            if vid in mapped:
                rid,clock,new_dep,lead,timed=mapped[vid]
                assert routes[rid]==n and clock==dep and new_dep==d and math.isclose(d-o,lead,abs_tol=1e-6)
                if not timed:
                    assert math.isclose(d-o,dep-op,abs_tol=1e-6)
            elif condition!='release' and op==dep:
                assert d==dep and 0<d-o<=180
            else:
                assert new_windows[vid]==old_windows[vid]
            pairs[node,dep].append(vid)
        counts=Counter()
        for (n,t),vids in pairs.items():
            if 15*3600<=t<19*3600:
                expected=2 if n==hot['admin_snu'] else 1
                assert len(vids)==expected and len({new_windows[v][2] for v in vids})==1
                assert all(new_windows[v][3]==44 for v in vids)
                counts['snu_pairs' if expected==2 else 'daehak_singles']+=1
        sig=lambda e:(e[1],e[2],e[11],e[12])
        original={sig(e):e for e in old['events']}
        assert len(original)==len(r['events'])==len({sig(e) for e in r['events']})
        for e in r['events']:
            b=original[sig(e)]
            assert e[3]==b[3]
            if e[2] not in mapped:
                vid=e[2]
                if (condition!='release' and vid in new_windows and old_windows[vid][1]==old_windows[vid][2]
                        and e[11]=='shuttle-41841' and e[12]==0):
                    assert abs((b[0]-e[0])-(new_windows[vid][2]-new_windows[vid][1]))<1e-5
                else:
                    assert e[0]==b[0]
        result[condition]=dict(**counts,events=len(original),template_assignments=len(mapped),
                               matched_dwells=sum(int(v[-1]) for v in mapped.values()))
    return result

if __name__=='__main__':
    data={f'{s}-{d}':verify(f'{s}-{d}') for d in ('mon','tue','wed','thu','fri') for s in ('regular','peak')}
    (HERE/'배차_독립검산.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
