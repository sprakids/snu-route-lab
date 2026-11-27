"""Opt-in adapters for an isolated Planner. No active files, network or disk writes."""
from copy import deepcopy
from datetime import datetime
import math

from empirical_transport import KST
from recent_history import TransportHistory, history_rows


def prevent_duplicate_full_risk(pool, base_departure, evidence):
    """Joint training already excludes full-flag vehicles; retain FIFO only."""
    detail = pool.get('city_wait', {}) if pool else {}
    simulation = detail.get('simulation')
    if not evidence.get('known_full_filtered') or not isinstance(simulation, dict):
        return pool
    if simulation.get('available'):
        extra = simulation['extra_wait_seconds']
        if detail.get('simulation_delay_scale_policy') != 'absolute_audited_clock':
            extra *= detail['headway_seconds']/simulation['reference_headway_seconds']
    else:
        extra = 0.
    extra = round(max(0., extra));leave = base_departure+extra
    corrected = {**detail, 'extra_wait_seconds': extra, 'expected_boarding_at': leave,
                 'base_departure_at': base_departure,
                 'empirical_full_risk': {'available': False, 'reason': 'already_conditioned_on_unflagged_joint_opportunities'},
                 'policy': 'audited_fifo_after_joint_known_full_filter', 'duplicate_full_risk_removed': True}
    return {**pool, 'departure_at': leave, 'earliest_departure_at': leave, 'city_wait': corrected,
            'arrival_forecast': {**pool.get('arrival_forecast', {}), 'expected_boarding_at': leave,
                                 'city_wait': corrected}}


def last_passage(transit, rid, seq, ready, asof, eligible=None):
    # An ETA is not a completed passage. Only caller-supplied confirmed stop events.
    rows, _ = history_rows(transit)
    values = [p['at'] for p in rows if p.get('seen', math.inf) <= min(ready, asof)
              and p.get('at', math.inf) <= min(ready, asof)
              and ((p.get('r') == rid and p.get('s') == seq) if eligible is None else
                   p.get('r') in eligible and p.get('stop_id') == '120000029')
              and datetime.fromtimestamp(p['at'], KST).date() == datetime.fromtimestamp(ready, KST).date()]
    return max(values) if values else None


class ContinuityAdapter:
    def __init__(self, baseline, profile, enabled):
        self.baseline, self.profile, self.enabled = baseline, profile, frozenset(enabled)

    def __getattr__(self, name):
        return getattr(self.baseline, name)

    def info(self):
        return {**self.baseline.info(), 'transport_candidate': self.profile.meta(),
                'candidate_components': sorted(self.enabled)}

    def headway(self, rid, seq, at, asof, nominal, shared=None):
        if 'headway' in self.enabled:
            p = self.profile.headway_wait(rid, int(seq), at, asof)
            if p:
                return p['headway']['median_seconds'], p['source'], self.profile.data['dates']
        return self.baseline.headway(rid, seq, at, asof, nominal, shared)

    def service(self, transit, route, index, ready, observed=(), live=True, history=None):
        value = self.baseline.service(transit, route, index, ready, observed, live, history)
        if value is None or route.get('kind') == 'shuttle' or 'headway' not in self.enabled:
            return value
        now = transit.now()
        # The surrounding planner owns fresh live ETAs and capacity filtering.
        # Never replace a current catchable identified bus with a historical clock.
        if any(a.get('vehicle_id') and a.get('provided_at') is not None and
               0 <= now-a['provided_at'] <= 150 and a.get('departure_at', 0) >= ready and not a.get('full')
               for a in observed):
            return value
        recent, _ = history_rows(transit, live)
        p = self.profile.headway_wait(route['id'], route['stops'][index]['seq'], ready, now,
                                     recent_passages=recent,
                                     last_passage=last_passage(transit, route['id'], route['stops'][index]['seq'], ready, now) if live else None)
        if p is None:
            return value
        leave = ready+round(p['seconds'])
        # A known missed/full vehicle conditions the surrounding fallback. Do not
        # reinterpret it as an empty bus or move departure before that constraint.
        blocked = [a['departure_at'] for a in observed if a.get('full') or a['departure_at'] < ready]
        if blocked and leave <= max(blocked):
            return value
        if not transit.in_service(route, leave):
            return value
        forecast = {**value.get('arrival_forecast', {}), 'source': p['source'],
                    'model_id': p['model_id'], 'base_departure_at': leave,
                    'headway_seconds': p['headway']['mean_seconds'],
                    'range_seconds': p['range_seconds'], 'headway_distribution': p,
                    'future_departures_at': [], 'vehicle_confirmed': False, 'rolling': True,
                    'label': '과거 정류장 도착간격·변동 기반 추정',
                    'conditional_after_known_services': p['conditioned_elapsed_seconds'] is not None}
        for stale in ('operations', 'phase_conditioned'):
            forecast.pop(stale, None)
        return {**value, 'departure_at': leave, 'earliest_departure_at': leave,
                'vehicle_id': None, 'provided_at': None, 'arrival_source': 'service_history_estimate',
                'arrival_forecast': forecast, 'prediction_note': '같은 방향 정류장 관측 간격·변동을 반영한 운행기회 추정'}

    def predict_crowd(self, route, index, at, asof, evidence=None, last_section=None, live=True, shared=None):
        baseline = self.baseline.predict_crowd(route, index, at, asof, evidence, last_section, live, shared)
        if route.get('kind') == 'shuttle' or 'crowd' not in self.enabled or baseline.get('crowd_source') == 'observed':
            return baseline
        evidence = evidence or {}
        grade = evidence.get('crowd_cost')
        if grade is None and str(evidence.get('crowd_code')) in ('3', '4', '5', '6'):
            grade = int(evidence['crowd_code'])-3
        try:
            source_seq = int(last_section) if last_section is not None else None
        except (TypeError, ValueError):
            source_seq = None
        p = self.profile.crowd(route['id'], int(route['stops'][index]['seq']), at, asof,
                               grade=grade if live else None,
                               source_seq=source_seq,
                               observed_at=evidence.get('provided_at') if live else None)
        if p is None:
            return baseline
        labels = {0: '여유', 1: '보통', 2: '혼잡', 3: '매우혼잡'}
        age = asof-p['observed_at'] if p['observed_at'] is not None else None
        return {**baseline, 'crowd_cost': None, 'crowd_estimate': round(p['estimate'], 3),
                'crowd_risk': p['comparison_risk'], 'crowd_source': p['source'],
                'crowd_uncertainty': p['comparison_risk']-p['estimate'],
                'crowd_label': labels[round(p['estimate'])]+' 추정', 'observed_at': p['observed_at'],
                'age_seconds': round(age) if age is not None else None,
                'model_version': p['model_id'], 'empirical_transport': p, 'calibrated': False}


class TravelAdapter:
    def __init__(self, baseline, profile, transit, enabled):
        self.baseline, self.profile, self.transit, self.enabled = baseline, profile, transit, frozenset(enabled)

    def __getattr__(self, name):
        return getattr(self.baseline, name)

    def estimate(self, route, i, j, when, snapshot=None, live=False):
        base = self.baseline.estimate(route, i, j, when, snapshot, live)
        if ('ride' not in self.enabled or route.get('kind') == 'shuttle' or
                not base.get('available') or base.get('current_segments', 0) > 0):
            return base
        _, recent = history_rows(self.transit, live)
        p = self.profile.ride_time(route['id'], route['stops'][i]['seq'], route['stops'][j]['seq'], when, self.transit.now(), recent_travel=recent)
        if p is None:
            return base
        return {**p, 'seconds': max(1, round(p['seconds'])), 'label': '같은 방향·구간의 과거 통과시간',
                'history_dates': p['training_dates'], 'observed_at': None,
                'empirical_transport': p, 'fallback_source': base.get('source'),
                'note': '정차·신호를 포함한 관측 통과시간이며 정차시간을 중복 가산하지 않습니다.'}


def common_gate_adapter(baseline_function, profile, enabled):
    def add_common_gate(candidates, planner, departure, live):
        baseline = baseline_function(candidates, planner, departure, live)
        if 'gate' not in enabled:
            return baseline
        from strategies import GATE_ROUTES, GATE_STOP, STATION_STOP
        from routing import finish_candidate
        direct = []
        for c in candidates:
            buses = [l for l in c['legs'] if l['type'] == 'bus']
            if len(buses) == 1 and buses[0]['route_id'] in GATE_ROUTES and buses[0]['station_id'] == GATE_STOP:
                b = buses[0]
                route = planner.by_id[b['route_id']]
                if any(s['id'] == STATION_STOP and s['seq'] == b['to_seq'] for s in route['stops']):
                    direct.append((c, b))
        if not direct:
            return baseline
        if any(b.get('vehicle_id') and (b.get('provided_at') or b.get('eta_observed_at')) is not None and
               0 <= planner.transit.now()-(b.get('provided_at') or b.get('eta_observed_at')) <= 150 and b.get('arrival_source') == 'live'
               for c, b in direct):
            return baseline
        original, first = min(direct, key=lambda x: x[0]['walk_seconds'])
        direct = [(c, b) for c, b in direct if c['walk_seconds'] == original['walk_seconds'] and
                  c['boarding_seconds'] == original['boarding_seconds'] and b['ready_at'] == first['ready_at']]
        # Route variants are one eligible service, not duplicate alternatives.
        members = {b['route_id']: (c, b) for c, b in direct}
        ready = first['ready_at']
        anchor = last_passage(planner.transit, None, None, ready, planner.transit.now(), members) if live else None
        recent, _ = history_rows(planner.transit, live)
        p = profile.gate_wait(members, ready, planner.transit.now(), last_passage=anchor, recent_passages=recent)
        if p is None or not set(p['route_probabilities']).issubset(members):
            return baseline
        weights = p['route_probabilities']
        leave = ready+round(p['seconds'])
        pool = None
        if hasattr(planner.transit, 'city_boarding'):
            route = planner.by_id[first['route_id']]
            i = next(i for i, s in enumerate(route['stops']) if s['seq'] == first['from_seq'])
            pool = planner.transit.city_boarding(route, i, ready,
                {'departure_at': leave, 'earliest_departure_at': leave, 'vehicle_id': None, 'provided_at': None,
                 'full': False, 'arrival_source': 'empirical_joint_gate_estimate',
                 'arrival_forecast': {'headway_seconds': p['headway']['mean_seconds']}}, live,
                key='pool:'+GATE_STOP, headway=p['headway']['mean_seconds'],
                pool_members=[{'route_id': r, 'seq': b['from_seq'], 'probability': weights.get(r, 0)}
                              for r, (c, b) in members.items()])
            if pool is None:
                return baseline
            pool = prevent_duplicate_full_risk(pool, leave, p)
            leave = ready+round(pool['departure_at']-ready)
        # Weight each possible actual route's ride at this common departure time.
        # Keep direct alternatives too: first vehicle need not be fastest overall.
        route_seconds = {}
        for r, (c, b) in members.items():
            route = planner.by_id[r]
            i = next(k for k, s in enumerate(route['stops']) if s['seq'] == b['from_seq'])
            j = next(k for k, s in enumerate(route['stops']) if s['seq'] == b['to_seq'])
            snapshot = getattr(planner.transit, 'plan_snapshot', {}) if live else getattr(planner.transit, 'history_snapshot', {})
            time_est = planner.travel.estimate(route, i, j, leave, snapshot, live) if hasattr(planner, 'travel') else None
            route_seconds[r] = time_est['seconds'] if time_est and time_est.get('available') else b['seconds']
        seconds = round(sum(weights.get(r, 0)*value for r, value in route_seconds.items()))
        if not all(planner.transit.in_service(planner.by_id[r], leave) for r in weights):
            return baseline
        legs = deepcopy(original['legs'])
        for l in legs:
            if l['type'] == 'wait':
                l.update(seconds=round(leave-ready), source='empirical_joint_gate_estimate')
        ride = next(l for l in legs if l['type'] == 'bus')
        ride.update(seconds=seconds, departure_at=leave, arrival_at=leave+seconds,
                    route_name='정문 공동노선 먼저 오는 차', arrival_source='empirical_joint_gate_estimate',
                    vehicle_id=None, provided_at=None, arrival_options=[],
                    ride_model={'seconds': seconds, 'source': 'joint_gate_first_route_weighted_travel',
                                'empirical_transport': p},
                    crowd_cost=None, crowd_source='empirical_common_line_estimate',
                    crowd_estimate=sum(weights.get(r, 0)*(b.get('crowd_estimate') if b.get('crowd_estimate') is not None else 1.5)
                                       for r, (c, b) in members.items()),
                    crowd_risk=sum(weights.get(r, 0)*b.get('crowd_risk', 3) for r, (c, b) in members.items()),
                    crowd_label='공동노선 혼잡위험 추정', observed_at=None, age_seconds=None)
        if pool and pool.get('city_wait'):
            ride['city_wait'] = pool['city_wait']
        ride['arrival_forecast'] = {**(pool or {}).get('arrival_forecast', {}),
                                   'source': p['source'], 'headway_distribution': p,
                                   'base_departure_at': leave, 'vehicle_confirmed': False,
                                   'model_id': p['model_id']}
        out = finish_candidate('gate-first', legs, departure, [])
        out['strategy'] = 'walk_to_gate'
        out['common_gate_service'] = {**p, 'kind': 'joint_observed_opportunity_estimate',
                                      'expected_wait_seconds': round(leave-ready),
                                      'eligible_route_ids': sorted(members)}
        return [c for c in baseline if c.get('id') != 'gate-first']+[out]
    return add_common_gate


def install_candidate(planner, profile, enabled, network_sha256, patch_gate=True):
    """Use only in a sandbox or an explicitly approved release. Returns undo()."""
    if network_sha256 != profile.data['network_sha256']:
        raise ValueError('Directed network version differs from the fitted data')
    unknown = set(enabled)-{'headway', 'ride', 'crowd', 'gate'}
    if unknown:
        raise ValueError('Unknown transport component')
    old_continuity, old_travel = planner.transit.continuity, planner.travel
    old_memory = getattr(planner.transit, '_transport_history', None)
    routes = getattr(planner, 'routes', list(getattr(planner, 'by_id', {}).values()))
    planner.transit._transport_history = TransportHistory(routes)
    planner.transit.continuity = ContinuityAdapter(old_continuity, profile, enabled)
    planner.travel = TravelAdapter(old_travel, profile, planner.transit, enabled)
    import gate_service
    old_gate = gate_service.add_common_gate
    if patch_gate:
        gate_service.add_common_gate = common_gate_adapter(old_gate, profile, enabled)
    def undo():
        planner.transit.continuity, planner.travel = old_continuity, old_travel
        if old_memory is None:
            delattr(planner.transit, '_transport_history')
        else:
            planner.transit._transport_history = old_memory
        if patch_gate:
            gate_service.add_common_gate = old_gate
    return undo
