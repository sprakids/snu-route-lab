"""Compare archived vehicle detections with V12 service; export no vehicle identifiers."""
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta
import gzip
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent
ROOT = MODEL.parent
sys.path[:0] = [str(MODEL), str(ROOT/'collector'), str(ROOT/'empirical_transport_261116162001')]
from export_history import credentials
from traces import get as shuttle_archive
from extract_observations import campus_keys, clock, extract, load_network


def read(p):
    with gzip.open(p, 'rt', encoding='utf8') as f:
        return json.load(f)


def main():
    cutoff=datetime.fromisoformat('2026-11-27T15:15:00+09:00')
    cred = credentials()
    assert cred['url'].rstrip('/') == 'https://snu-route-collector.touchline-atlas-june.workers.dev'
    archived = json.loads((MODEL/'terminal_transitions.json').read_bytes())
    common = read(MODEL/'viewer-data/common.json.gz')
    network = load_network()
    campus = campus_keys(network)
    route_indices = {(rid,s['seq']):i for rid,stops in common['city_route_stops'].items() for i,s in enumerate(stops)}
    ref_ids = {(r['id'],s['seq']):s['id'] for r in network['routes'] for s in r['stops']}
    for (rid,seq),i in route_indices.items():
        assert common['city_route_stops'][rid][i]['id'] == ref_ids[(rid,seq)]
    archive_dirs = [ROOT/'collected_data_review_2026-11-12/raw', ROOT/'empirical_transport_261116162001/private',
                    ROOT/'empirical_transport_R261116170142/private']
    quality = {}
    with TemporaryDirectory() as tmp, (HERE/'시내버스_동일차량_운행시간.csv').open('w',newline='',encoding='utf-8-sig') as city, (HERE/'행정관_차량위치_시각구간.csv').open('w',newline='',encoding='utf-8-sig') as shuttle:
        rides = csv.writer(city)
        rides.writerow(['날짜','노선ID','출발정류장순번','도착정류장순번','관측출발시각','관측도착시각','관측경과초','모형구간초','모형빼기실측_초','양끝검출간격합_초'])
        windows = csv.writer(shuttle)
        windows.writerow(['날짜','노선','사건','실측구간시작_자정후초','실측구간끝_자정후초','기준_구간내모의차량수','피크_구간내모의차량수','시각근거'])
        models = {}
        for index in range((date(2026,11,27)-date(2026,11,6)).days+1):
            dt = date(2026,11,6)+timedelta(days=index)
            if dt.weekday()>=5: continue
            day=dt.isoformat()
            wd=('mon','tue','wed','thu','fri')[dt.weekday()]
            q=quality[day]={}
            if wd not in models:
                clocks={}
                for sc in ('regular','peak'):
                    d=read(MODEL/f'viewer-data/{sc}-{wd}.json.gz')
                    for rid,node_key in [('41841','admin_snu'),('41843','admin_daehak')]:
                        n=common['hot_nodes'][node_key]
                        for kind,col in [('enter',2),('exit',4)]:
                            clocks[sc,rid,kind]=sorted(row[col] for row in d['terminal_presence'] if row[0]==n)
                models[wd]=clocks
            # The original Nov 25 evidence was exported before that day's service had ended.
            sh=archived.get(day) if day<'2026-11-25' else None
            if not sh or sh['status']!=200:
                sh=shuttle_archive(day,cred)
            q['shuttle_status']=sh['status']
            for rid,details in sh.get('routes',{}).items():
                for e in details['events']:
                    lo,hi=e['interval']
                    if day==cutoff.date().isoformat() and hi>15*3600+15*60:continue
                    counts=[]
                    for sc in ('regular','peak'):
                        seq=models[wd][sc,rid,e['type']]
                        counts.append(sum(lo<=t<=hi for t in seq))
                    windows.writerow([day,rid,e['type'],lo,hi,*counts,'위치수신 구간'])
            filename=day+'.jsons.gz'
            path=next((folder/filename for folder in archive_dirs if (folder/filename).exists()), None)
            if path is None:
                path=Path(tmp)/filename
                req=Request(cred['url']+'/export?day='+day,headers={'Authorization':'Bearer '+cred['token'],'User-Agent':'SNU-Route-Lab/0.4'})
                try:
                    with urlopen(req,timeout=55) as r: path.write_bytes(r.read())
                except HTTPError as err:
                    if err.code!=404:raise
                    q['city_status']=404
                    continue
            raw=extract(path,day,network)
            q.update(city_status=200,city_sha256=raw['source_sha256'],city_batches=raw['quality']['batches'],
                     all_stop_detections=len(raw['passages']))
            trips=defaultdict(list)
            for row in raw['passages']:
                trips[row['trip']].append(row)
            included=Counter()
            for group in trips.values():
                group.sort(key=lambda x:x['at'])
                for a,b in zip(group,group[1:]):
                    rid=a['r']
                    if max(a['seen'],b['seen'])>cutoff.timestamp():continue
                    if (rid,a['s']) not in campus and (rid,b['s']) not in campus:continue
                    if (rid,a['s']) not in route_indices or (rid,b['s']) not in route_indices:continue
                    seconds=b['at']-a['at']
                    if not (0<b['s']-a['s']<=12 and 0<seconds<=1800):continue
                    arrival=clock(a['at'])
                    if not 15<=arrival.hour<19:continue
                    offsets=common['route_info'][rid]['offsets']
                    i,j=route_indices[rid,a['s']],route_indices[rid,b['s']]
                    modeled=offsets[j]-offsets[i]
                    rides.writerow([day,rid,a['s'],b['s'],arrival.strftime('%H:%M:%S'),clock(b['at']).strftime('%H:%M:%S'),
                                    round(seconds,3),round(modeled,3),round(modeled-seconds,3),a['detection_gap']+b['detection_gap']])
                    included[rid]+=1
            q['peak_ride_pairs']=sum(included.values())
            print(day,q.get('peak_ride_pairs',0),flush=True)
    (HERE/'차량자료_수집범위.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
