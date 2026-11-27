"""Read-only comparison of one user-reported queue and existing public models."""
from pathlib import Path
from bisect import bisect_right
from datetime import datetime
import hashlib
import json
import math
import statistics
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PUBLIC = ROOT / 'simulation_viewer_2026-11-07/public'
sys.path.insert(0, str(ROOT / 'app'))
from automatic_queue import AutomaticQueue, queue_at


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock(second):
    return f'{int(second)//3600:02}:{int(second)//60%60:02}:{second%60:06.3f}'


def replay_summary(version, scenario, target, observed):
    folder = PUBLIC / f'data/capacity_v{version}'
    common = read(folder / 'common.json')
    replay_path = folder / f'{scenario}-mon.json'
    replay = read(replay_path)
    node = common['hot_nodes']['admin_snu']
    assert common['nodes'][node]['stop_id'] == 'snu-410'
    rows = replay['queue_timeline'][node]
    times = [r[0] for r in rows]
    assert times == sorted(times)

    def point(second):
        index = bisect_right(times, second) - 1
        return rows[index][1] if index >= 0 else 0.0

    # Exactly the map's last-event-at-or-before lookup, without interpolation.
    q = point(target)
    breaks = [target, *[s for s in times if target < s < target+60], target+60]
    vals = [point(s) for s in breaks[:-1]]
    minute_mean = math.fsum(point(a)*(b-a) for a,b in zip(breaks, breaks[1:]))/60
    events = [dict(zip(replay['event_columns'], e)) for e in replay['events'] if e[1] == node]
    previous = [e for e in events if e['time'] <= target]
    upcoming = [e for e in events if e['time'] > target]
    return {
        'dataset': f'capacity_v{version}', 'scenario': scenario,
        'unit': 'weighted_expected_trip_events',
        'queue_at_165300': q,
        'difference_model_minus_observed': q-observed,
        'difference_percent_of_observed': (q-observed)/observed*100,
        'queue_at_165330': point(target+30),
        'within_minute_model_queue_min_max': [min(vals), max(vals)],
        'within_minute_time_weighted_mean': minute_mean,
        'minute_range_is_prediction_interval': False,
        'observed_within_minute_model_min_max': min(vals) <= observed <= max(vals),
        'previous_model_vehicle': previous[-1] if previous else None,
        'next_model_vehicle': upcoming[0] if upcoming else None,
        'replay_sha256': digest(replay_path),
        'public_gzip_file': str(replay_path.relative_to(PUBLIC)).replace('\\', '/')+'.gz',
        'public_gzip_sha256': digest(Path(str(replay_path)+'.gz')),
    }


def operational_summary(at, observed):
    manifest = read(PUBLIC / 'routing-model/latest.json')
    path = PUBLIC / manifest['payload_path'].lstrip('/')
    assert digest(path) == manifest['sha256']
    model = AutomaticQueue(None, path=path)
    assert model.config['model_only'] and model.config['live_beta'] == 0
    route_id = 'shuttle-41841'
    route = model.data['routes'][route_id]
    index = next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410' and s['board_allowed'])
    profiles, _, midnight = model.profiles(route_id, at.timestamp(), {}, False, at.timestamp())
    target = at.timestamp()-midnight
    central = [p for p in profiles if p['scenario']['demand']==1.0]
    values = [queue_at(p,index,target) for p in profiles]
    central_values = [queue_at(p,index,target) for p in central]
    q = statistics.mean(central_values)
    # A minute envelope of the central phase average; no probabilistic coverage claim.
    second_means = [statistics.mean(queue_at(p,index,target+s) for p in central) for s in range(60)]
    return {
        'model_id': model.config['id'], 'payload_sha256': digest(path),
        'source_scenario': model.data['latest_simulation']['scenario'],
        'unit': model.data['unit'], 'central_demand': 1.0,
        'central_reserve': central[0]['scenario']['reserve'],
        'central_effective_capacity': central[0]['capacity'],
        'central_phase_count': len(central), 'sensitivity_profile_count': len(profiles),
        'queue_at_165300': q, 'central_phase_queue_values': central_values,
        'difference_model_minus_observed': q-observed,
        'difference_percent_of_observed': (q-observed)/observed*100,
        'all_profile_queue_range': [min(values), max(values)],
        'range_kind': 'assumption_sensitivity_not_confidence_interval',
        'within_minute_central_mean_range_at_integer_seconds': [min(second_means), max(second_means)],
        'queue_at_165330': second_means[30],
        'observed_queue': False, 'recalibrated_with_observation': False,
    }


def main():
    obs = read(HERE / 'queue_admin_snu_1653.json')
    at = datetime.fromisoformat(obs['comparison_representative_timestamp'])
    assert at.weekday()==0
    target = at.hour*3600+at.minute*60+at.second
    observed = obs['reported_queue_people']
    replays = [replay_summary(v,s,target,observed) for v in (5,6) for s in ('regular','peak')]
    for scenario in ('regular','peak'):
        a,b=[r for r in replays if r['scenario']==scenario]
        assert a['queue_at_165300']==b['queue_at_165300']
    result = {
        'observation_id': obs['observation_id'],
        'comparison_at': at.isoformat(), 'observed_queue_people': observed,
        'timestamp_caveat': 'The report has minute precision; :00 is a representative comparison, not a confirmed observation second.',
        'operational_routing_model': operational_summary(at,observed),
        'map_replays': replays,
        'model_changes_made': False,
        'interpretation': 'One externally reported queue count; not an onboard-count anchor, waiting-time measurement, accuracy estimate or calibration.',
    }
    (HERE / 'queue_comparison_1653.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'operational':result['operational_routing_model'],'map_replays':[{k:r[k] for k in ('dataset','scenario','queue_at_165300','within_minute_model_queue_min_max','within_minute_time_weighted_mean','queue_at_165330')} for r in replays]},ensure_ascii=False))


if __name__=='__main__':
    main()
