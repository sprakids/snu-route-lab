"""Apply saved empirical road-speed references to a new, isolated replay.

The mixed weekend/partial-Monday reference is a retrospective sensitivity, not
a fitted weekday forecast. Original v5 data/cache and official plans are kept.
"""
from pathlib import Path
import argparse, copy, csv, gzip, hashlib, json, math, statistics, time

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'empirical_speed_2026-11-09'
OUT=WORK/'public_data'
SOURCES=ROOT.parent/'collaboration/city_observation_review_20261109154207/transport_observations'
REVISION='empirical_road_reference_20261109_v1'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metres(a,b):return math.hypot((a[0]-b[0])*111195,(a[1]-b[1])*111195*math.cos(math.radians((a[0]+b[0])/2)))


def prepare_variant():
    WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
    source=ROOT/'city_bus_model_2026-11-08/prepared.json.gz'
    empirical=SOURCES/'empirical_transport_candidates.json'
    hashes={'original_prepared':digest(source),'empirical_candidates':digest(empirical),'builder':digest(Path(__file__))}
    cached=WORK/'prepared.json.gz'
    if cached.exists():
        result=json.loads(gzip.decompress(cached.read_bytes()));assert result['empirical_input_hashes']==hashes;return result
    bundle=json.loads(gzip.decompress(source.read_bytes()));d=json.loads(empirical.read_text(encoding='utf-8'))
    common=bundle['prepared']['common'];routes=bundle['prepared']['routes'];refs=d['pooled_speed_reference']
    original=copy.deepcopy(common['route_info']);city=[];changes=[]
    for rid,info in common['route_info'].items():
        if not info.get('city'):continue
        old=list(info['offsets']);new=[0.]
        for k,pid in enumerate(info['segments']):
            a,b=routes[rid]['stops'][k:k+2];ref=refs.get(f"{rid}:{b['seq']}")
            motion=common['motion_profiles'][str(pid)];minimum=motion['duration'];length=motion['d'][-1]
            seconds=max(minimum,length/(ref['speed_kmh']/3.6)) if ref else old[k+1]-old[k]
            new.append(new[-1]+seconds)
            source_row=dict(route_id=rid,route=routes[rid]['name'],from_seq=a['seq'],to_seq=b['seq'],from_stop=a['name'],to_stop=b['name'],
                source='saved_provider_day_median_reference' if ref else 'unchanged_frozen_v5',source_dates=ref['dates'] if ref else [],
                road_m=length,reference_speed_kmh=ref['speed_kmh'] if ref else None,
                old_seconds=old[k+1]-old[k],new_seconds=seconds,kinematic_minimum_seconds=minimum,
                campus_corridor=info['segment_time_sources'][k].get('campus_stop_corridor_40',False),
                applies_additional_dwell=False,actual_completed_trip_time=False)
            changes.append(source_row);info['segment_time_sources'][k]={**info['segment_time_sources'][k],
                'previous_source':info['segment_time_sources'][k]['source'],'source':source_row['source'],
                'speed_kmh':source_row['reference_speed_kmh'],'applied_seconds':seconds,'empirical_source_dates':source_row['source_dates']}
            if ref:city.append(dict(rid=rid,k=k,points=common['paths'][pid],length=length,reference=ref))
        info['offsets']=new
        # Prefix of partial routes determines the arrival at the first modeled
        # stop. Keep it unchanged here rather than alter an unverified clock.
        info['empirical_prefix_changed']=False

    # Only nearly coincident endpoints plus matching road length AND shape can
    # transfer a city-road reference to a shuttle corridor. This is a road proxy,
    # never an observed shuttle drive or an observed shuttle stop dwell.
    proxy=[]
    def point_distance(p,line):
        lat=p[0];best=float('inf')
        for a,b in zip(line,line[1:]):
            x=(b[1]-a[1])*math.cos(math.radians(lat))*111195;y=(b[0]-a[0])*111195
            px=(p[1]-a[1])*math.cos(math.radians(lat))*111195;py=(p[0]-a[0])*111195
            at=max(0,min(1,(px*x+py*y)/(x*x+y*y))) if x*x+y*y else 0
            best=min(best,math.hypot(px-at*x,py-at*y))
        return best
    for rid,info in common['route_info'].items():
        if info.get('city'):continue
        old=list(info['offsets']);new=[0.]
        for k,pid in enumerate(info['segments']):
            line=common['paths'][pid];motion=common['motion_profiles'][str(pid)];length=motion['d'][-1]
            candidates=[c for c in city if metres(line[0],c['points'][0])<=50 and metres(line[-1],c['points'][-1])<=50 and .85<=length/c['length']<=1.15]
            qualified=[]
            sample=line[::max(1,len(line)//15)]+[line[-1]]
            for c in candidates:
                if max(point_distance(p,c['points']) for p in sample)<=35:qualified.append(c)
            ref=min(qualified,key=lambda c:abs(length-c['length'])) if qualified else None
            seconds=max(motion['duration'],length/(ref['reference']['speed_kmh']/3.6)) if ref else old[k+1]-old[k]
            new.append(new[-1]+seconds)
            if ref:proxy.append(dict(route_id=rid,segment=k,matched_city_route=ref['rid'],matched_city_segment=ref['k'],
                reference_speed_kmh=ref['reference']['speed_kmh'],source_dates=ref['reference']['dates'],
                old_seconds=old[k+1]-old[k],new_seconds=seconds,source='city_observed_road_proxy_not_shuttle_observation'))
        info['offsets']=new
    common['city_speed_revision']=REVISION
    common['empirical_speed_reference']={
        'revision':REVISION,'label':'기록된 구간속도 참고 보정 · 주말/월요일 일부 혼합 민감도',
        'source_cutoff':d['source_cutoff_kst'],'source_days':['2026-11-07','2026-11-08','2026-11-09'],
        'weekday_forecast_validated':False,'completed_trip_time_calibrated':False,
        'shuttle_reference_kind':'geometry-matched city road proxy, not direct shuttle observation',
        'campus_max_kmh':40,'external_max_kmh':65,'prefix_clock_unchanged':True,
        'external_background_passengers_included':False}
    bundle['empirical_input_hashes']=hashes
    cached.write_bytes(gzip.compress(json.dumps(bundle,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    (WORK/'segment_time_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (WORK/'shuttle_road_proxies.json').write_text(json.dumps(proxy,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result=dict(status='PASS',revision=REVISION,city_segments=len(changes),observed_reference_city_segments=sum(c['reference_speed_kmh'] is not None for c in changes),
        changed_city_segments=sum(abs(c['new_seconds']-c['old_seconds'])>1e-6 for c in changes),shuttle_proxy_segments=len(proxy),
        changed_shuttle_proxy_segments=sum(abs(c['new_seconds']-c['old_seconds'])>1e-6 for c in proxy),
        original_cache_sha256=hashes['original_prepared'],external_background_passengers_included=False,
        date_conditioning='pooled_saved_day_medians_retrospective_reference',prefix_clock_changed=False)
    (WORK/'preparation_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    assert digest(source)==hashes['original_prepared'];print(json.dumps(result),flush=True)
    return bundle


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--day',choices=['월','화','수','목','금']);parser.add_argument('--scenario',choices=['regular','peak']);args=parser.parse_args()
    bundle=prepare_variant()
    if args.prepare_only:return
    import city_capacity_model as model
    import capacity_model as base
    model.WORK=WORK;model.OUT=OUT;base.OUT=OUT
    common=bundle['prepared']['common'];common['data_version']=6;common['policies']={'city':{'label':'관측 도로속도 참고 보정'}}
    plans={r['rid']:r['metadata'] for r in bundle['city_sources']['plans']['routes']}
    for row in common['city_services']:
        row['official_origin']=plans[row['route_id']]['stStationNm'];row['official_end']=plans[row['route_id']]['edStationNm']
    base.public('common.json',common)
    started=time.perf_counter();charts={}
    for scenario in ([args.scenario] if args.scenario else base.SCENARIOS):
        charts[scenario]={}
        for day in ([args.day] if args.day else base.DAYS):
            data=model.simulate(bundle,day,scenario)
            charts[scenario][base.DAYS[day]]={k:data[k] for k in ['hourly','daily','report']}
    if not args.day and not args.scenario:
        old=base.read(ROOT/'public/data/capacity_v5/charts.json')
        base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':old['legacy_wait_charts'],'adaptive':True,'city_capacity_applied':True})
    receipt='run_verification.json' if not args.day and not args.scenario else f'run-{args.scenario or "all"}-{base.DAYS.get(args.day,"all")}.json'
    base.save(WORK/receipt,dict(status='PASS',revision=REVISION,elapsed_seconds=time.perf_counter()-started,
        runs=[r['report'] for days in charts.values() for r in days.values()],original_v5_unchanged=True))


if __name__=='__main__':main()
