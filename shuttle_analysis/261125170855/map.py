"""Reuse the research viewer and add the distinction between presence and boarding."""
import argparse
import bisect
from collections import defaultdict
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'261125164654'
sys.path.insert(0,str(PRIOR))
import local_map as viewer

def prepare():
    viewer.build('candidate')
    p=HERE/'viewer-data/common.json.gz'
    common=viewer.map_stats.maps.read(p)
    common['departure_and_boarding'].update(
        baseline='R261125164654-release',normal_section_minutes=[-5,0,5],
        door_lead_seconds='curb service begins at the later of inferred area arrival and preceding batch departure',
        boarding_service='one FIFO boarding stream per direction at 2 seconds per rider equivalent',
        extended_stay_minutes=[0,90],extended_stay_population='existing stayers from classes ending by 18:00')
    viewer.map_stats.maps.publish(p,common)
    maps=viewer.map_stats.maps
    terminals={common['hot_nodes'][k] for k in ('admin_snu','admin_daehak')}
    for source in (HERE/'runs/candidate').glob('*'):
        key=source.name
        archive=source/f'audit-{key}.json.gz'
        if not archive.is_file():continue
        ledger=maps.read(archive)
        path=HERE/'viewer-data'/f'{key}.json.gz'
        replay=maps.read(path)
        departures={(e[1],e[2]):e[0] for e in replay['events'] if e[1] in terminals}
        stamps={n:sorted({t for (node,v),t in departures.items() if node==n}) for n in terminals}
        cells=defaultdict(list)
        for w in ledger['wait_audit']:
            n=w['node']
            if n not in terminals or w['outcome']!='boarded':continue
            entry=w['physical_stop_entry'];dep=departures[n,w['vehicle']]
            i=bisect.bisect_left(stamps[n],entry)
            first=stamps[n][i]==dep
            cells[n,int(entry//60)].append(((w['end']-entry)/60,w['weight'],first))
        history={n:{} for n in terminals}
        for (n,m),rows in cells.items():
            total=sum(w for _,w,_ in rows)
            acc=0.
            for wait,w,_ in sorted(rows):
                acc+=w
                if acc>=total/2:break
            history[n][m]=[round(total,5),round(wait,4),round(sum(w for _,w,f in rows if f)/total,5)]
        replay['terminal_minute_waits']=history
        maps.publish(path,replay)

BASE_ASSETS = viewer.serve_map.assets


def render_assets(folder):
    BASE_ASSETS(folder)
    page=folder/'viewer.js'
    js=page.read_text(encoding='utf8')
    anchor="const onboard=onboardWaiting(node,state.second);"
    assert js.count(anchor)==1
    js=js.replace(anchor,anchor+"""
    const terminalRows=state.data.terminal_presence;
    let atTerminal=0, atCurb=0;
    for(const [stop,vehicle,arrival,opening,departure] of terminalRows){
      if(stop===node && arrival<=state.second && state.second<departure){
        atTerminal++;
        if(opening<=state.second)atCurb++;
      }
    }
""")
    anchor2="+'명 상당';"
    start=js.index("parked.textContent=");end=js.index(anchor2,start)
    js=js[:end]+js[end:].replace(anchor2,"+'명 상당 · 행정관 부근 '+atTerminal+'대 / 승차 위치 '+atCurb+'대';",1)
    anchor3="+'대 / 승차 위치 '+atCurb+'대';"
    assert js.count(anchor3)==1
    js=js.replace(anchor3,anchor3+"""
    const sample=state.data.terminal_minute_waits?.[node]?.[Math.floor(state.second/60)];
    parked.textContent+=sample
      ? ' · 이 분에 줄에 합류해 여기서 탄 학생의 대기 중앙값 '+fmt(sample[1])+'분 / 다음 출발편 탑승 '+Math.round(100*sample[2])+'%'
      : ' · 이 분에 합류해 여기서 탄 모의 학생 없음';
""")
    page.write_text(js,encoding='utf8')


def start(port):
    viewer.serve_map.assets=render_assets
    viewer.start(port,'candidate')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--build',action='store_true')
    p.add_argument('--port',type=int,default=8800)
    a=p.parse_args()
    viewer.HERE=HERE
    viewer.layout=lambda condition:(HERE,'R'+HERE.name)
    if a.build:prepare()
    else:start(a.port)
