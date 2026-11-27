"""Compare a stop's pooled map queue to a minute-precision user report."""
from pathlib import Path
from bisect import bisect_right
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import math
import urllib.request

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / 'simulation_viewer_2026-11-07/public'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('observation', type=Path)
    parser.add_argument('--verify-public', action='store_true')
    args = parser.parse_args()
    obs = read(args.observation)
    reported = obs.get('reported_queue_people')
    reported_range = obs.get('reported_queue_people_range')
    lower, upper = reported_range if reported_range is not None else (reported,reported)
    assert isinstance(lower,(int,float)) and isinstance(upper,(int,float)) and 0 <= lower <= upper
    at = datetime.fromisoformat(obs['comparison_representative_timestamp'])
    day = ('mon','tue','wed','thu','fri','sat','sun')[at.weekday()]
    second = at.hour*3600+at.minute*60+at.second
    results, files = [], set()
    for version in (5,6):
        folder = PUBLIC / f'data/capacity_v{version}'
        common_path = folder / 'common.json'
        common = read(common_path)
        node = common['hot_nodes'][obs['simulation_stop_key']]
        assert common['nodes'][node]['stop_id'] == obs['stop_id']
        files.add(Path(str(common_path)+'.gz'))
        for scenario in ('regular','peak'):
            replay_path = folder / f'{scenario}-{day}.json'
            replay = read(replay_path)
            files.add(Path(str(replay_path)+'.gz'))
            rows = replay['queue_timeline'][node]
            times = [r[0] for r in rows]
            assert times == sorted(times)
            def point(t):
                index = bisect_right(times,t)-1
                return rows[index][1] if index >= 0 else 0.0
            breaks = [second,*[t for t in times if second<t<second+60],second+60]
            vals = [point(t) for t in breaks[:-1]]
            q = point(second)
            results.append({
                'dataset':f'capacity_v{version}', 'scenario':scenario,
                'node':node, 'queue_at_representative_second':q,
                'difference_model_minus_report':q-reported if reported is not None else None,
                'difference_model_minus_report_interval':[q-upper,q-lower],
                'distance_from_reported_interval':max(lower-q,q-upper,0),
                'queue_at_plus_30_seconds':point(second+30),
                'minute_model_queue_min_max':[min(vals),max(vals)],
                'minute_time_weighted_mean':math.fsum(point(a)*(b-a) for a,b in zip(breaks,breaks[1:]))/60,
                'report_in_minute_temporal_envelope':min(vals)<=reported<=max(vals) if reported is not None else None,
                'reported_interval_overlaps_minute_temporal_envelope':max(lower,min(vals)) <= min(upper,max(vals)),
                'envelope_is_confidence_interval':False,
                'replay_sha256':sha(replay_path),
                'stop':common['nodes'][node],
                'unit':'weighted_expected_trip_events',
            })
    checks = []
    if args.verify_public:
        def verify(path):
            rel = path.relative_to(PUBLIC).as_posix()
            with urllib.request.urlopen('https://snu-shuttle-simulation.vercel.app/'+rel,timeout=20) as response:
                raw = response.read()
            match = hashlib.sha256(raw).hexdigest() == sha(path)
            assert match,rel
            return {'path':rel,'sha256':sha(path),'public_matches_local':match}
        with ThreadPoolExecutor(max_workers=4) as pool:
            checks = list(pool.map(verify,sorted(files)))
    output = {
        'observation_id':obs['observation_id'], 'comparison_at':at.isoformat(),
        'reported_queue_people':reported,
        'reported_queue_people_range':reported_range,
        'interval_midpoint_treated_as_exact_observation':False,
        'stop_mapping_assumption':obs.get('stop_mapping_assumption'),
        'pooled_queue_not_sum_of_independent_route_queues':True,
        'representative_second_not_confirmed_observation_second':True,
        'replays':results, 'public_file_checks':checks,
        'checked_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'model_or_collector_changed':False,
        'onboard_counts_or_actual_waiting_times_inferred':False,
    }
    target = args.observation.with_name(args.observation.stem+'_comparison.json')
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(target),'public_files_verified':len(checks),'replays':[{k:r[k] for k in ('dataset','scenario','queue_at_representative_second','minute_model_queue_min_max','minute_time_weighted_mean')} for r in results]},ensure_ascii=False))


if __name__=='__main__':
    main()
