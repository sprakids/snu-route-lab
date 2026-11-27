"""Read existing plans/ledgers only. No simulation or model imports/mutations."""
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent
MODEL = ANALYSIS / '261116161819'
PUBLIC = ANALYSIS / 'simulation_viewer_2026-11-07/public'
RUN = MODEL / 'runs/anchor-combined-regular-mon/attempt_01'
NODE = 42
DEST = 'daehak'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def grouped(counter):
    return [dict(key=list(k) if isinstance(k, tuple) else k, weight=v)
            for k, v in counter.most_common()]


def mode(plan):
    if not plan[6]:
        return 'terminal_walk'
    return 'shuttle_first' if plan[6][0]['rid'].startswith('shuttle') else 'city_first'


def first_route(plan):
    return plan[6][0]['rid'] if plan[6] else 'terminal_walk'


paths = {
    'prepared': MODEL / 'frozen/prepared_capacity44_pair.json.gz',
    'audit_R_mon_regular': RUN / 'audit-regular-mon.json.gz',
    'curve_R_mon_regular': RUN / 'regular-mon.json.gz',
    'curve_V11_mon_regular': PUBLIC / 'data/capacity_v11/regular-mon.json',
    'physical_paths': MODEL / 'physical_paths_e3e9b7863828.json.gz',
    'config': MODEL / 'config.json',
    'behavior_source': MODEL / 'behavioral_policy.py',
    'preference_source': MODEL / 'preferences.py',
    'engine_source': MODEL / 'engine.py',
    'freeze_manifest': MODEL / 'future_evaluation_plan.json',
    'observation': ANALYSIS / 'field_observations_2026-11-23/full_departure_admin_daehak_1659.json',
    'qualitative_context': ANALYSIS / 'field_observations_2026-11-23/qualitative_daehak_walk_rain_context.json',
    'previous_comparison': ANALYSIS / 'field_observations_2026-11-23/queue_1659_daehak_comparison.json',
    'published_latest_local': PUBLIC / 'routing-model/latest.json',
}
input_hashes = {k: dict(path=str(p), sha256=sha(p)) for k, p in paths.items()}
bundle = read(paths['prepared'])
audit = read(paths['audit_R_mon_regular'])
curves = {
    'R261116161819': read(paths['curve_R_mon_regular']),
    'V11': read(paths['curve_V11_mon_regular']),
}
config = read(paths['config'])
manifest = read(paths['freeze_manifest'])
plans = bundle['prepared']['plans']['월']
plan_by_id = {p[0]: p for p in plans}
patience_by_id = {}
for trip in audit['legs']:
    # Split mass can create multiple exported leg records with the same id.
    # Only join the persistent personal trait, and verify it agrees across splits.
    uid, value = trip['id'], trip['student_patience_seconds']
    if uid in patience_by_id:
        assert math.isclose(patience_by_id[uid], value, abs_tol=1e-9), uid
    patience_by_id[uid] = value
assert len(plan_by_id) == len(plans)


def destination(parent):
    return bundle['destination_keys'][str(parent)]


def curve_points(data):
    # Match the viewer: keep the final update at coincident timestamps.
    points = {float(r[0]): float(r[1]) for r in data['queue_timeline'][NODE]}
    times = sorted(points)

    def at(t):
        i = bisect_right(times, t) - 1
        return points[times[i]] if i >= 0 else 0.

    return points, times, at


def stock(t):
    visits = [w for w in audit['wait_audit']
              if w['node'] == NODE and w['arrival'] <= t < w['end']]
    total = sum(w['weight'] for w in visits)
    by_dest, by_mode, by_route, by_changes = Counter(), Counter(), Counter(), Counter()
    known_release = 0.
    for w in visits:
        parent = w['parent_id']
        plan = plan_by_id[parent]
        by_dest[destination(parent)] += w['weight']
        by_mode[mode(plan)] += w['weight']
        by_route[first_route(plan)] += w['weight']
        # Count is recorded at visit close. Zero there implies zero prior changes now.
        by_changes[w['realized_change_count']] += w['weight']
        release = w.get('student_first_release')
        if release is not None and release['time'] <= t:
            known_release += w['weight']
    age = [(t - w['physical_stop_entry'], w['weight']) for w in visits]
    patience = [(patience_by_id[w['id']], w['weight']) for w in visits]
    at = curve_points(curves['R261116161819'])[2]
    assert math.isclose(total, at(t), abs_tol=1e-6), (t, total, at(t))
    assert set(by_dest) == {'daehak'}
    assert set(by_changes) == {0}
    return dict(
        second=t, weighted_queue=total, audit_fragment_count=len(visits),
        by_destination=dict(by_dest), by_source_first_mode=dict(by_mode),
        by_source_first_route=dict(by_route),
        prior_changes_at_visit_close=dict(by_changes),
        known_flexibility_release_weight_at_snapshot=known_release,
        mean_elapsed_stop_wait_seconds=sum(v*w for v, w in age) / total,
        max_elapsed_stop_wait_seconds=max(v for v, _ in age),
        mean_personal_patience_seconds=sum(v*w for v, w in patience) / total,
        min_personal_patience_seconds=min(v for v, _ in patience),
        max_personal_patience_seconds=max(v for v, _ in patience),
    )


daehak = [p for p in plans if destination(p[0]) == DEST]
mass = sum(p[3] for p in daehak)
mode_mass, route_mass = Counter(), Counter()
for p in daehak:
    mode_mass[mode(p)] += p[3]
    route_mass[first_route(p)] += p[3]
source_composition = dict(
    weekday='월', total_weight=mass,
    first_mode_weight=dict(mode_mass), first_mode_fraction={k: v/mass for k, v in mode_mass.items()},
    first_route_weight=dict(route_mass), first_route_fraction={k: v/mass for k, v in route_mass.items()},
    interpretation='Inherited synthetic source plans. Not observed modal shares; internal access shuttles included in shuttle_first.',
)

balances = {}
for label, data in curves.items():
    points, times, at = curve_points(data)
    before = at(60600.)
    positive = negative = 0.
    for t in times:
        if 60600. < t < 61200.:
            delta = points[t] - before
            positive += max(delta, 0.)
            negative += max(-delta, 0.)
            before = points[t]
    switch_source = audit if label == 'R261116161819' else data
    switches = [s for s in switch_source['switches'] if s[1] == NODE and 60600. < s[0] < 61200.]
    actions = Counter()
    for s in switches:
        actions[(s[9], s[5], s[6])] += s[2]
    balances[label] = dict(
        interval='after16:50 service to before17:00 service',
        start_queue=at(60600.), end_queue=at(61200. - 1e-6),
        positive_curve_variation=positive, negative_curve_variation=negative,
        mass_balance_error=at(60600.)+positive-negative-at(61200.-1e-6),
        switch_actions=grouped(actions),
        note='Positive/negative curve variations are net changes, not automatically gross arrival/departure counts. Arrival-time alternative choices can avoid queue entry.',
    )
    assert abs(balances[label]['mass_balance_error']) < 1e-6

v11_rechecks = sum(s['weight'] for s in balances['V11']['switch_actions'] if s['key'][0] == 'queue_recheck')
assert math.isclose(v11_rechecks, balances['V11']['negative_curve_variation'], abs_tol=1e-5)
# These V11 exits transfer to another service. They are not terminal home walks.
assert all(s['key'][1] == 'transit' for s in balances['V11']['switch_actions'])
r_left = Counter()
for w in audit['wait_audit']:
    if w['node'] == NODE and 60600. < w['end'] < 61200.:
        r_left[w['outcome']] += w['weight']

walk = next(o for o in bundle['alternatives']['42|daehak'] if not o['stages'])
profile = read(paths['physical_paths'])[walk['walk'][0]]
meters = walk['walk_meters']
base = .3 * math.exp(-(meters - 1000.) / 150.)
walking = dict(
    option=walk, physical_profile=profile, destination_representative_point=bundle['prepared']['common']['destinations'].get('daehak'),
    base_relative_consideration_weight=base, reciprocal_relative_to_le500m=1/base,
    zero_full_bus_age300_seconds_conditional_prior=1-(1-base)*math.exp(-300/1800),
    zero_full_bus_age1200_seconds_conditional_prior=1-(1-base)*math.exp(-1200/1800),
    interpretation='Base weight is neither an actual walking probability nor an initial mode share. Age/experienced-full-bus relief changes it at eligible later choice opportunities. Shuttle initial choice returns before such comparisons.',
)

selected_frozen = {}
for name in ['behavioral_policy.py', 'preferences.py', 'engine.py', 'prepare.py', 'config.json']:
    selected_frozen[name] = dict(actual=sha(MODEL/name), expected=manifest['frozen_sha256'][name])
    assert selected_frozen[name]['actual'] == selected_frozen[name]['expected'], name
assert all(sha(paths[k]) == item['sha256'] for k, item in input_hashes.items())
report = dict(
    schema='daehak_read_only_mode_choice_diagnosis_v1',
    computed_at_utc=datetime.now(timezone.utc).isoformat(),
    context='User-reported usual walking preference plus heavy-rain preference shift and one post-full-departure residual queue observation.',
    provenance=input_hashes,
    weekday_scope='Existing Monday regular template, not a reconstruction of actual2026-11-23 weather/traffic.',
    source_composition=source_composition,
    audit_trip_export_records=len(audit['legs']), unique_personal_trait_ids=len(patience_by_id),
    queue_stock=[stock(t) for t in [61140., 61200.-1e-6, 61200.+1e-6]],
    pre17_queue_balance=balances,
    R_stop_outcomes_strictly_between1650and1700=dict(r_left),
    terminal_walk_option=walking,
    relevant_config={k: config[k] for k in [
        'initial_assignment_policy', 'shuttle_patience_median_seconds', 'city_patience_median_seconds',
        'patience_log_sigma', 'patience_uses_elapsed_plus_forecast', 'initial_trunk_preservation',
        'review_requires_current_queue_pressure', 'walking_kmh', 'walk_coefficient_median']},
    invariants=dict(selected_model_sources_match_frozen_manifest=selected_frozen, all_read_inputs_unchanged=True,
        model_conditions_rerun=0, model_files_changed=False, parameters_fitted=False, production_writes=False),
    limitations=[
        'Post-full-departure queue1 does not identify pre-boarding demand, actual capacity, gross demand, or walking mode share.',
        'Rain is user-reported context; no rain coefficient or measured population preference shift was estimated.',
        'Model17:00 service and actual16:59 service are different clock/phase observations; their post-service counts are only a nearby-phase diagnostic.',
        'R versus V11 differs in several mechanisms; the ledger contrast is not a controlled one-factor causal effect.',
        'Weighted queue amounts are person-equivalent mass, not integer headcounts or unique trip totals.',
    ],
)
out = HERE / 'diagnosis.json'
assert not out.exists(), out
out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps({
    'first_mode_fractions':source_composition['first_mode_fraction'],
    'direct_daehak_first_fraction':source_composition['first_route_fraction']['shuttle-daehak'],
    'pre17_stock':report['queue_stock'][1],
    'balances':balances,
    'R_outcomes_1650to1700':dict(r_left),
    'walk_base_relative_weight':base,
    'inputs_unchanged':True,
}, ensure_ascii=False), flush=True)
