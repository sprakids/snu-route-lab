"""Read-only review of the explicitly handed-off collector snapshot.

No fetching, calibration, source overwrite, or application/model mutation.
Output grains are provider observations, contiguous section visits, and paired
observations. None of these is an independent passenger or a boarding outcome.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import csv
import gzip
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
VALID = {'3', '4', '5', '6'}
MAX_AGE = 300
MAX_GAP = 300


def local(at):
    return datetime.fromtimestamp(at, KST)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantile(rows, p):
    if not rows:
        return None
    rows = sorted(rows)
    return rows[min(len(rows)-1, int((len(rows)-1)*p))]


def csvout(name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (ROOT/name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def identity(text):
    return hashlib.sha256(text.encode()).hexdigest()[:14]


def main():
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:
        assert sha(ROOT/f['path']) == f['sha256'], f['path']
    stops = json.loads((ROOT/'route_stops.json').read_text(encoding='utf-8'))
    byseq = {rid: {int(s['seq']): s for s in rows} for rid, rows in stops.items()}
    raw, archives, route_fetches = [], Counter(), []
    for spec in manifest['files']:
        if not spec['path'].startswith('collector-'):
            continue
        records = [json.loads(line) for line in gzip.decompress((ROOT/spec['path']).read_bytes()).splitlines() if line.strip()]
        assert len(records) == spec['archive_records']
        n = 0
        for record in records:
            archives[spec['day']] += 1
            for entry in record.get('route_records', []):
                route_fetches.append(dict(day=spec['day'], route_id=entry['route_id'], at=entry['at'], error=entry.get('error')))
            for vehicle in record.get('vehicles', []):
                raw.append(dict(vehicle, day=spec['day']))
                n += 1
        assert n == spec['vehicle_observation_rows_not_independent_samples']

    raw.sort(key=lambda v: v['captured_at'])
    unique, conflicts = {}, 0
    for row in raw:
        key = row['day'], row['route_id'], row['id'], row['provided_at']
        if key in unique:
            old = unique[key]
            conflicts += (str(row['section_order']), row['crowd_code']) != (str(old['section_order']), old['crowd_code'])
        else:
            # Earliest capture determines freshness, rather than the last time a
            # stalled provider observation was re-fetched.
            unique[key] = row
    ambiguous={tuple(k) for k in json.loads((ROOT/'ambiguous_provider_keys.private.json').read_text(encoding='utf-8'))}
    assert len(ambiguous)==1, 'Reconcile provider-key conflicts with the independent audit' 
    samples = list(unique.values())
    names = {v['route_id']: v['route_name'] for v in raw}
    clean, excluded = [], Counter()
    for row in samples:
        age = row['captured_at'] - row['provided_at']
        try:
            seq = int(row['section_order'])
        except (ValueError, TypeError):
            seq = -1
        reason = ('conflicting_provider_state' if (row['route_id'],row['id'],row['provided_at']) in ambiguous else 'provider_day_mismatch' if local(row['provided_at']).date().isoformat() != row['day'] else
                  'provider_future_time' if age < 0 else 'provider_older_than_300s' if age > MAX_AGE else
                  'unmatched_section_order' if seq not in byseq.get(row['route_id'], {}) else None)
        if reason:
            excluded[reason] += 1
            continue
        stop = byseq[row['route_id']][seq]
        clean.append(dict(row, seq=seq, direction=stop['direction'], stop_name=stop['name'], stop_id=stop['id'], lag=age))
    assert len(clean) + sum(excluded.values()) == len(samples)

    tracks = defaultdict(list)
    for row in clean:
        tracks[row['day'], row['route_id'], row['id']].append(row)
    visits, transitions, high_spells, provider_gaps = [], [], [], []
    blocked = Counter()
    for (day, rid, vehicle), rows in tracks.items():
        rows.sort(key=lambda v: v['provided_at'])
        run = 0
        prior = None
        visit = None
        active_high = None
        def close_high(reason, recovery=None):
            nonlocal active_high
            if active_high is None:
                return
            first, last = active_high[0], active_high[-1]
            high_spells.append(dict(day=day, route_id=rid, route=names[rid], vehicle_hash=identity(vehicle),
                run_hash=identity(f'{day}:{rid}:{vehicle}:{first["run"]}'), direction=first['direction'],
                first_high_kst=local(first['provided_at']).isoformat(), last_high_kst=local(last['provided_at']).isoformat(),
                first_high_seq=first['seq'], first_high_stop=first['stop_name'], last_high_seq=last['seq'], last_high_stop=last['stop_name'],
                high_observation_n=len(active_high), observed_high_span_seconds=last['provided_at']-first['provided_at'],
                recovery_observed=bool(recovery), recovery_kst=local(recovery['provided_at']).isoformat() if recovery else '',
                recovery_seq=recovery['seq'] if recovery else '', recovery_stop=recovery['stop_name'] if recovery else '',
                last_high_to_recovery_seconds=recovery['provided_at']-last['provided_at'] if recovery else '', end_reason=reason))
            active_high = None
        for row in rows:
            gap = row['provided_at']-prior['provided_at'] if prior else None
            reset = prior is None or gap > MAX_GAP or row['seq'] < prior['seq'] or row['direction'] != prior['direction']
            if prior:
                provider_gaps.append(dict(day=day, route_id=rid, route=names[rid], seconds=gap))
            if reset:
                close_high('track_gap_turn_or_end')
                run += 1
            row['run'] = run
            if reset or visit is None or row['seq'] != visit['seq']:
                previous_visit = visit
                visit = dict(day=day, route_id=rid, route=names[rid], seq=row['seq'], stop_id=row['stop_id'], stop_name=row['stop_name'],
                             direction=row['direction'], vehicle_hash=identity(vehicle), run_hash=identity(f'{day}:{rid}:{vehicle}:{run}'),
                             first=row, last=row, observations=[row])
                visits.append(visit)
                if previous_visit and not reset:
                    a, b = previous_visit['last'], row
                    distance = b['seq']-a['seq']
                    valid = a['crowd_code'] in VALID and b['crowd_code'] in VALID
                    transitions.append(dict(day=day, route_id=rid, route=names[rid], direction=row['direction'],
                        vehicle_hash=identity(vehicle), run_hash=visit['run_hash'], from_seq=a['seq'], to_seq=b['seq'],
                        from_stop=a['stop_name'], to_stop=b['stop_name'], from_stop_id=a['stop_id'], to_stop_id=b['stop_id'],
                        from_time_kst=local(a['provided_at']).isoformat(), to_time_kst=local(b['provided_at']).isoformat(),
                        hour=local(b['provided_at']).hour, half_hour=local(b['provided_at']).strftime('%H:')+('00' if local(b['provided_at']).minute<30 else '30'),
                        observation_gap_seconds=gap, seq_gap=distance, adjacent=distance == 1, valid_grades=valid,
                        from_grade=a['crowd_code'], to_grade=b['crowd_code'],
                        change=('increase' if int(b['crowd_code'])>int(a['crowd_code']) else 'decrease' if int(b['crowd_code'])<int(a['crowd_code']) else 'same') if valid else 'unavailable'))
            else:
                visit['last'] = row
                visit['observations'].append(row)
            if row['crowd_code'] in {'5','6'}:
                if active_high is None:
                    active_high=[]
                active_high.append(row)
            elif row['crowd_code'] in VALID:
                close_high('observed_lower_grade', row)
            else:
                close_high('grade_unavailable')
            prior = row
        close_high('track_end_right_censored')

    passage_rows = []
    for v in visits:
        valid_rows = [x for x in v['observations'] if x['crowd_code'] in VALID]
        representative = valid_rows[0] if valid_rows else v['first']
        passage_rows.append({k:v[k] for k in ['day','route_id','route','seq','stop_id','stop_name','direction','vehicle_hash','run_hash']} |
            dict(first_observed_kst=local(v['first']['provided_at']).isoformat(),last_observed_kst=local(v['last']['provided_at']).isoformat(),
                 hour=local(representative['provided_at']).hour, grade=representative['crowd_code'],
                 provider_observations=len(v['observations']), observed_span_seconds=v['last']['provided_at']-v['first']['provided_at']))
    csvout('section_visits.csv', passage_rows)
    csvout('paired_section_observations.csv', transitions)
    csvout('high_grade_spells.csv', high_spells)

    rawgroups, samplegroups, visitgroups = defaultdict(list), defaultdict(list), defaultdict(list)
    for target, source in [(rawgroups,raw),(samplegroups,samples),(visitgroups,passage_rows)]:
        for row in source:
            target[row['day'],row['route_id']].append(row)
    daily = []
    for day, rid in sorted(rawgroups):
        r, u, v = rawgroups[day,rid], samplegroups[day,rid], visitgroups[day,rid]
        codes=Counter(x['grade'] for x in v)
        knownkeys={(x['id'],x['provided_at']) for x in r if x.get('full_known') is True}
        knownfull={(x['id'],x['provided_at']) for x in r if x.get('full_known') is True and x.get('full') is True}
        rawlag=[x['captured_at']-x['provided_at'] for x in r]
        gaps=[x['seconds'] for x in provider_gaps if x['day']==day and x['route_id']==rid]
        daily.append(dict(day=day,weekday=local(r[0]['captured_at']).strftime('%A'),route_id=rid,route=names[rid],
            capture_start_kst=local(min(x['captured_at'] for x in r)).isoformat(),capture_end_kst=local(max(x['captured_at'] for x in r)).isoformat(),
            raw_rows=len(r),unique_provider_observations=len(u),duplicate_provider_rows=len(r)-len(u),
            unique_vehicles=len({x['id'] for x in u}),raw_unavailable_grade=sum(x['crowd_code'] not in VALID for x in r),
            provider_unavailable_grade=sum(x['crowd_code'] not in VALID for x in u),
            section_visits=len(v),visit_grade_3=codes['3'],visit_grade_4=codes['4'],visit_grade_5=codes['5'],visit_grade_6=codes['6'],visit_grade_unavailable=sum(n for c,n in codes.items() if c not in VALID),
            provider_lag_median_seconds=statistics.median(rawlag),provider_lag_p90_seconds=quantile(rawlag,.9),provider_lag_max_seconds=max(rawlag),
            provider_gap_median_seconds=statistics.median(gaps) if gaps else '',provider_gap_p90_seconds=quantile(gaps,.9),provider_gap_gt300_n=sum(g>300 for g in gaps),
            known_full_provider_observations=len(knownkeys),known_full_true=len(knownfull),legacy_full_true_rows=sum(x.get('full') is True and x.get('full_known') is not True for x in r)))
    csvout('route_daily_quality_and_crowding.csv',daily)

    def aggregate_edges(keys):
        groups=defaultdict(list)
        for row in transitions:
            if row['adjacent']:
                groups[tuple(row[k] for k in keys)].append(row)
        result=[]
        for key, group in sorted(groups.items()):
            comparable=[x for x in group if x['valid_grades']]
            c=Counter(x['change'] for x in comparable)
            result.append(dict(zip(keys,key)) | dict(candidate_pairs=len(group),comparable_pairs=len(comparable),increase=c['increase'],decrease=c['decrease'],same=c['same'],unavailable_pairs=len(group)-len(comparable),
                unique_vehicles=len({x['vehicle_hash'] for x in comparable}),unique_runs=len({x['run_hash'] for x in comparable}),
                median_observation_gap_seconds=statistics.median(x['observation_gap_seconds'] for x in group),max_observation_gap_seconds=max(x['observation_gap_seconds'] for x in group)))
        return result
    edgekeys=['day','route_id','route','direction','from_seq','from_stop','to_seq','to_stop']
    edge_day=aggregate_edges(edgekeys)
    csvout('adjacent_changes_by_day.csv',edge_day)
    csvout('adjacent_changes_by_hour.csv',aggregate_edges(edgekeys+['hour']))
    profiles=defaultdict(Counter)
    for row in passage_rows:
        key=tuple(row[k] for k in ['day','route_id','route','direction','seq','stop_id','stop_name','hour'])
        profiles[key][row['grade'] if row['grade'] in VALID else 'unavailable']+=1
    csvout('stop_direction_hour_grades.csv',[dict(zip(['day','route_id','route','direction','seq','stop_id','stop_name','hour'],key)) | dict(section_visits=sum(c.values()),grade_3=c['3'],grade_4=c['4'],grade_5=c['5'],grade_6=c['6'],unavailable=c['unavailable']) for key,c in sorted(profiles.items())])

    day_summary=[]
    for day in manifest['dates']:
        ds=[x for x in daily if x['day']==day]
        tr=[x for x in transitions if x['day']==day]
        comp=[x for x in tr if x['adjacent'] and x['valid_grades']]
        hs=[x for x in high_spells if x['day']==day]
        day_summary.append(dict(day=day,archive_batches=archives[day],raw_rows=sum(x['raw_rows'] for x in ds),unique_provider_observations=sum(x['unique_provider_observations'] for x in ds),
            capture_start_kst=min(x['capture_start_kst'] for x in ds),capture_end_kst=max(x['capture_end_kst'] for x in ds),
            section_visits=sum(x['section_visits'] for x in ds),grade_unavailable_visits=sum(x['visit_grade_unavailable'] for x in ds),
            adjacent_candidates=sum(x['adjacent'] for x in tr),adjacent_comparable=len(comp),increase=sum(x['change']=='increase' for x in comp),decrease=sum(x['change']=='decrease' for x in comp),same=sum(x['change']=='same' for x in comp),
            multi_section_pairs=sum(not x['adjacent'] for x in tr),high_spells=len(hs),observed_recovery_spells=sum(x['recovery_observed'] for x in hs),known_full_provider_observations=sum(x['known_full_provider_observations'] for x in ds),known_full_true=sum(x['known_full_true'] for x in ds)))
    csvout('date_coverage_and_changes.csv',day_summary)
    sensitivity=[]
    for limit in [120,180,300]:
        t=[x for x in transitions if x['adjacent'] and x['valid_grades'] and x['observation_gap_seconds']<=limit]
        sensitivity.append(dict(max_observation_gap_seconds=limit,adjacent_comparable=len(t),increase=sum(x['change']=='increase' for x in t),decrease=sum(x['change']=='decrease' for x in t),same=sum(x['change']=='same' for x in t)))
    csvout('gap_threshold_sensitivity.csv',sensitivity)
    fetch_groups=defaultdict(list)
    for row in route_fetches:
        fetch_groups[row['day'],row['route_id']].append(row)
    fetch_summary=[]
    for (day,rid), group in sorted(fetch_groups.items()):
        times=sorted({x['at'] for x in group});gaps=[b-a for a,b in zip(times,times[1:])]
        fetch_summary.append(dict(day=day,route_id=rid,route=names.get(rid,rid),saved_fetch_records=len(group),saved_error_records=sum(bool(x['error']) for x in group),fetch_gap_median_seconds=statistics.median(gaps) if gaps else '',fetch_gap_p90_seconds=quantile(gaps,.9),fetch_gap_max_seconds=max(gaps) if gaps else ''))
    csvout('saved_route_fetch_intervals.csv',fetch_summary)

    model_file=Path(manifest['model_path'])
    model=json.loads(model_file.read_text(encoding='utf-8'))
    city=model['city_wait']
    model_rows=[x for rows in city['profiles'].values() for x in rows]
    model_summary=dict(model_id=model['release']['model_id'],sha256=sha(model_file),algorithm_id=city['algorithm_id'],scenario=city['scenario'],
        services=len(city['services']),profiles=len(city['profiles']),profile_rows=len(model_rows),bin_minutes=city['bin_minutes'],phase_seconds=city['phase_seconds'],
        nonzero_extra_delay_rows=sum(x[1] is not None and x[1]>0 for x in model_rows),censored_profile_rows=sum(x[4]>0 for x in model_rows),note=city['note'])
    model_hash=sha(model_file)
    for f in manifest['files']:
        assert sha(ROOT/f['path'])==f['sha256']
    assert sha(model_file)==model_hash
    assert sum(x['raw_rows'] for x in daily)==len(raw)==sum(f.get('vehicle_observation_rows_not_independent_samples',0) for f in manifest['files'])
    assert sum(x['unique_provider_observations'] for x in daily)==len(samples)
    assert sum(x['section_visits'] for x in daily)==len(visits)
    assert all(x['increase']+x['decrease']+x['same']==x['comparable_pairs'] for x in edge_day)
    assert all(x['seq_gap']==1 for x in transitions if x['adjacent'])
    summary=dict(status='PASS',raw_rows=len(raw),provider_observations=len(samples),duplicate_provider_rows=len(raw)-len(samples),provider_key_conflict_rows=conflicts,ambiguous_provider_keys_excluded=len(ambiguous),
        included_provider_observations=len(clean),provider_exclusions=dict(excluded),section_visits=len(visits),paired_sections=len(transitions),
        adjacent_comparable=sum(x['adjacent'] and x['valid_grades'] for x in transitions),high_spells=len(high_spells),observed_recovery_spells=sum(x['recovery_observed'] for x in high_spells),
        input_hashes_verified=len(manifest['files']),source_files_unchanged=True,model_modified=False,app_modified=False,new_deployment_for_analysis=False,
        maximum_provider_age_seconds=MAX_AGE,maximum_pair_gap_seconds=MAX_GAP,day_summary=day_summary,model=model_summary,
        focus_increases=sorted([x for x in edge_day if x['increase']>0],key=lambda x:(x['day']=='2026-11-09',x['increase'],x['comparable_pairs']),reverse=True)[:20],
        focus_decreases=sorted([x for x in edge_day if x['decrease']>0],key=lambda x:(x['day']=='2026-11-09',x['decrease'],x['comparable_pairs']),reverse=True)[:20])
    (ROOT/'analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['focus_increases','focus_decreases','day_summary','model']},ensure_ascii=False))


if __name__=='__main__':
    main()
