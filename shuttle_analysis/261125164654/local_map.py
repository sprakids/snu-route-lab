"""Prepare and serve only the combined research candidate on loopback."""
import argparse
from collections import Counter
from http.server import ThreadingHTTPServer
import re
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'261124160531'
sys.path.insert(0,str(BASE))
import serve_map
assert Path(serve_map.__file__).resolve()==BASE/'serve_map.py'
import map_stats

def layout(condition):
    return (HERE,'R'+HERE.name) if condition=='combined' else (HERE/'release-map','R'+HERE.name+'-release')

def build(condition):
    ref=map_stats.ref
    maps=map_stats.maps
    output,model=layout(condition)
    maps.VERSION=model
    maps.PREVIOUS=BASE
    viewer=output/'viewer-data'
    viewer.mkdir(parents=True,exist_ok=True)
    common=ref.load(BASE/'viewer-data/common.json.gz')
    common['candidate_id']=common['data_version']=model
    common['departure_and_boarding'].update(baseline='R'+BASE.name,normal_section_minutes=[-5,0,5],
                                           experiment_condition=condition)
    if condition=='combined':
        common['departure_and_boarding'].update(
            door_lead_seconds='historical terminal visit templates; unmatched visits use preceding R',
            boarding_service='1 weighted rider per 2 s per open bus, experimental')
    maps.publish(viewer/'common.json.gz',common)
    orig=ref.ref.load_v11()['prepared']['plans']
    dest={day:{p[0]:p[2] for p in rows} for day,rows in orig.items()}
    upper={day:{p[0] for p in rows if p[1] in ('300','301','302') and p[2]=='dorm'} for day,rows in orig.items()}
    del orig
    halves={};runs={};access={}
    for service in ('peak','regular'):
        halves[service]={};runs[service]={};access[service]={}
        for day,did in ref.DAYS.items():
            key=f'{service}-{did}'
            folder=HERE/'runs'/condition/key
            summary=ref.load(folder/'summary.json')
            assert summary['condition']==condition and summary['model']=='R'+HERE.name
            baseline=ref.load(BASE/'runs'/key/'attempt-01/result.json')
            patch={**ref.load(ref.INPUTS/f'{did}.json.gz'),'model':model}
            station_ids={r['plan'][0] for r in patch['replacements'] if r['plan'][2]==maps.STATION}
            audit=folder/f'audit-{key}.json.gz'
            station=Counter()
            for r in ref.load(audit)['legs']:
                if r['id'] in station_ids and not r['unserved']:
                    station[str(int(r['legs'][-1][2]//3600))]+=r['weight']
            assert abs(sum(station.values())-patch['station_demand'])<1e-6
            ref.previous.SAVE(folder/'result.json',dict(model=model,status='verified',rail_included=True,
                              initial=baseline['initial'],station_arrivals=station))
            shutil.copyfile(folder/f'{key}.json.gz',viewer/f'{key}.json.gz')
            halves[service][did],runs[service][did],access[service][did]=maps.case(
                audit,viewer/f'{key}.json.gz',dest[day],upper[day],patch,common,did,service)
    maps.publish(output/'map-stats.json.gz',dict(interval_seconds=1800,scenarios=halves,runs=runs))
    maps.publish(output/'station-access.json.gz',dict(model=model,destination=maps.STATION,
                 station_code='4411',event='arrival at station marker',runs=access))

def start(port,condition):
    output,serve_map.MODEL=layout(condition)
    shared=serve_map.serve.resource
    reports={'/model-guide':('guide.html','text/html'),'/research/guide':('README.md','text/plain'),
             '/research/results':('결과.md','text/plain'),'/research/counts.csv':('현장비교.csv','text/csv'),
             '/research/window.png':('화요일_대기_비교.png','image/png'),
             '/research/returns.csv':('별도날짜_복귀검증.csv','text/csv'),
             '/research/weekdays.csv':('평일검증.csv','text/csv')}
    with TemporaryDirectory(prefix='snu-terminal-map-') as temp:
        assets=Path(temp)
        serve_map.assets(assets)
        page=assets/'index.html'
        label='학생 출발시각만 수정' if condition=='release' else '학생 출발시각과 셔틀 승차를 함께 수정'
        page.write_text(page.read_text(encoding='utf8').replace('하교길 통합 지도',f'하교길 지도 · {label}'),encoding='utf8')
        def resource(path,page_fetch=False):
            path='/'+path.removeprefix('/'+serve_map.MODEL+'/').lstrip('/')
            if path in reports:
                name,mime=reports[path]
                return HERE/name,mime,False
            if path in ('/','/index.html','/viewer.js'):
                return assets/('viewer.js' if path=='/viewer.js' else 'index.html'),None,False
            if path in ('/map-stats.json','/station-access.json') or re.fullmatch(
                    r'/viewer-data/(common|(peak|regular)-(mon|tue|wed|thu|fri))\.json',path):
                return output/(path[1:]+'.gz'),'application/json',True
            return shared(path) if path=='/integrated.css' or path[1:] in serve_map.serve.SHARED or path.startswith(('/assets/','/vendor/')) else None
        serve_map.serve.resource=resource
        with ThreadingHTTPServer(('127.0.0.1',port),serve_map.serve.Handler) as server:
            server.serve_forever()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--build',action='store_true')
    p.add_argument('--port',type=int)
    p.add_argument('--condition',choices=('combined','release'),default='combined')
    args=p.parse_args()
    if args.build:
        build(args.condition)
    else:
        start(args.port or (8798 if args.condition=='combined' else 8799),args.condition)
