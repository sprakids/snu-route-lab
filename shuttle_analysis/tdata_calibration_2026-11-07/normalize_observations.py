"""Audit cached public responses; never reads credentials or calls the network."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import csv, json, hashlib, math, re

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'observations'
NETWORK=ROOT.parent/'course_demand_2026-11-06/sources/city_network_used.json'
NAMES={'100100250':'5511','100100251':'5513','100100253':'5516','120900011':'관악02-1','120900012':'관악02-2'}
FAMILIES={'sum_load':'a18SumLoadPsngNum','average':'a18Num','maximum':'maxA18Num','runs':'a18FcntNum'}

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def numeric(value):
    if value is None:return None
    assert isinstance(value,(int,float,str)) and not isinstance(value,bool)
    if isinstance(value,str):assert re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value),repr(value)
    number=float(value);assert math.isfinite(number) and number>=0
    return number
def write_csv(p,rows):
    assert rows
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    assert not OUT.exists(),'Preserve previous results; select a new directory explicitly'
    plan=load(ROOT/'analysis_plan.json');network=load(NETWORK)
    bbox=plan['campus_bbox'];current={};links=[]
    for route in network['routes']:
        for index,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):
            key=(route['id'],int(a['seq']),a['id'],b['id'])
            assert key not in current
            inside=bbox['lat_min']<=a['lat']<=bbox['lat_max'] and bbox['lon_min']<=a['lon']<=bbox['lon_max']
            row={'route_id':route['id'],'route_name':NAMES[route['id']],'sta_sn':int(a['seq']),
                 'from_stop_id':a['id'],'to_stop_id':b['id'],'from_stop_name':a['name'],'to_stop_name':b['name'],
                 'from_lat':a['lat'],'from_lon':a['lon'],'to_lat':b['lat'],'to_lon':b['lon'],
                 'direction':a.get('direction',''),'campus_origin':inside,'current_link_index0':index}
            current[key]=row;links.append(row)
    assert len(current)==259
    rows=[];audits=[];content_hashes={};all_checks=[]
    for split,dates in [('train',plan['train_dates']),('evaluation',plan['evaluation_dates'])]:
        for date in dates:
            directory=ROOT/'collected'/date;receipt=load(directory/'collection_receipt.json')
            assert receipt['status']=='complete' and receipt['end_proved_by_empty_page']
            source=directory/'target_routes.json';assert sha(source)==receipt['target_file_sha256']
            data=load(source);seen=set();families={f:Counter() for f in FAMILIES};day_checks=[]
            for r in data:
                assert r['stdrDe']==date
                key=(r['routeId'],int(r['staSn']),r['fromStaId'],r['toStaId'])
                assert key in current and key not in seen,(date,key)
                seen.add(key);base=current[key]
                values=[]
                for hour in range(24):
                    vals={f:numeric(r.get(f'{prefix}{hour:02d}h')) for f,prefix in FAMILIES.items()}
                    for f,v in vals.items():families[f]['null' if v is None else 'zero' if v==0 else 'positive']+=1
                    if vals['sum_load'] is not None:values.append(vals['sum_load'])
                    rows.append({'date':date,'split':split,'weekday':'월화수목금토일'[datetime.strptime(date,'%Y%m%d').weekday()],
                                 **base,'hour':hour,**vals})
                daily=numeric(r.get('a18SumLoadPsng'));known_sum=sum(values)
                day_checks.append({'date':date,'route_id':key[0],'sta_sn':key[1],
                                   'known_hour_count':len(values),'daily_sum_load':daily,
                                   'known_hour_sum':known_sum,'daily_minus_known_sum':None if daily is None else daily-known_sum})
            assert seen==set(current),'Date-specific missing or changed route geometry'
            canonical=sorted(data,key=lambda r:(r['routeId'],int(r['staSn']),r['fromStaId'],r['toStaId']))
            clean=[{k:v for k,v in r.items() if k!='stdrDe'} for r in canonical]
            fingerprint=hashlib.sha256(json.dumps(clean,sort_keys=True).encode()).hexdigest()
            content_hashes[date]=fingerprint
            audits.append({'date':date,'split':split,'segments':len(data),'hour_cells':len(data)*24,
                           'families':{f:dict(c) for f,c in families.items()},'source_sha256':sha(source),
                           'values_excluding_date_sha256':fingerprint,
                           'daily_sum_mismatches':sum(x['daily_minus_known_sum'] not in (0,None) for x in day_checks)})
            all_checks.extend(day_checks)
    duplicates=defaultdict(list)
    for date,fingerprint in content_hashes.items():duplicates[fingerprint].append(date)
    duplicate_dates=[dates for dates in duplicates.values() if len(dates)>1]
    assert not duplicate_dates,'Identical responses across dates require review before date evaluation'
    OUT.mkdir()
    write_csv(OUT/'hourly_observations.csv',rows);write_csv(OUT/'current_links.csv',links)
    write_csv(OUT/'daily_sum_crosschecks.csv',all_checks)
    report={'status':'PASS_OBSERVED_SCHEMA_AND_JOIN','dates':audits,'total_hour_cells':len(rows),
            'target_links':len(links),'campus_origin_links':sum(x['campus_origin'] for x in links),
            'campus_links_by_route':dict(Counter(x['route_name'] for x in links if x['campus_origin'])),
            'joined_links_every_date':len(current),'sta_sn_empirical_match':'current from-stop seq, all dates',
            'repeated_endpoint_pairs':len(links)-len({(x['route_id'],x['from_stop_id'],x['to_stop_id']) for x in links}),
            'duplicate_date_value_sets':duplicate_dates,'null_replaced_by_zero':False,
            'provider_hour_semantics_confirmed':False,'network_calls':0,
            'analysis_plan_sha256':sha(ROOT/'analysis_plan.json'),'network_snapshot_sha256':sha(NETWORK),
            'normalized_csv_sha256':sha(OUT/'hourly_observations.csv')}
    dump(OUT/'quality_audit.json',report)
    print(json.dumps({'status':report['status'],'dates':len(audits),'links':len(links),
                      'campus_links':report['campus_origin_links'],'hour_cells':len(rows),
                      'non_null_sum_load':sum(x['sum_load'] is not None for x in rows),
                      'daily_sum_mismatches':sum(x['daily_minus_known_sum'] not in (0,None) for x in all_checks)},ensure_ascii=False))

if __name__=='__main__':main()
