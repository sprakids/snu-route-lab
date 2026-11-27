"""API integration smoke on real frozen roads, with endpoint-only walking fixture."""
from datetime import datetime
import json
import sys
import time

from extract_observations import ROOT, KST, load_network, write_json, digest
sys.path.insert(0, str(ROOT/'baseline_app'))
from routing import Planner, PRESETS, distance
from continuity import Continuity
from candidate_runtime import install_candidate
ADAPTER_REVISION = 'R261116170142'
from empirical_transport import EmpiricalTransport


class EndpointWalker:
    # A tiny test graph: only identical endpoints connect. It deliberately does
    # not invent straight walk paths or claim campus pedestrian coverage.
    def walk(self, a, b):
        if distance(a, b) > .5:
            return None
        return {'seconds': 0, 'meters': 0, 'geometry': [list(a)], 'steps_m': 0, 'source': 'integration_fixture'}


class Transit:
    def __init__(self, at):
        self.at, self.cache = at, {}
        self.snapshot = self.history_snapshot = self.plan_snapshot = {}
        self.continuity = Continuity()

    def now(self):
        return self.at

    def in_service(self, route, at):
        return True

    def interval(self, route, at):
        return route['interval_minutes']

    def arrivals(self, route, index):
        return []

    def forecast_service(self, route, index, ready, observed, live):
        return self.continuity.service(self, route, index, ready, observed, live)

    def crowd_for(self, route, index, selected, at, live):
        return self.continuity.predict_crowd(route, index, at, self.now(), None, None, live)

    def notes(self):
        return ['Offline integration fixture; no provider calls or live queue accuracy claimed.']


def main():
    model = EmpiricalTransport(str(ROOT/'artifacts/profile.json'))
    network = load_network()
    transit = Transit(datetime(2026, 11, 16, 17, tzinfo=KST).timestamp())
    planner = Planner(network, EndpointWalker(), transit)
    route = next(r for r in network['routes'] if r['id'] == '100100250')
    destination = next(s for s in route['stops'] if s['id'] == '120000150')
    reports = []
    for seq in [16, 18, 21]:
        origin = next(s for s in route['stops'] if s['seq'] == seq)
        args = ((origin['lat'], origin['lon']), (destination['lat'], destination['lon']),
                transit.now(), 'history', PRESETS['fast'])
        baseline = planner.plan(*args, include_shuttle=False)
        undo = install_candidate(planner, model, {'headway', 'ride', 'crowd', 'gate'}, digest(ROOT/'baseline_app/data/network.json'))
        try:
            start = time.perf_counter()
            candidate = planner.plan(*args, include_shuttle=False)
            elapsed = time.perf_counter()-start
        finally:
            undo()
        assert candidate['candidates'], 'No candidate from exact route endpoints'
        for c in candidate['candidates']:
            assert all(l['seconds'] >= 0 for l in c['legs'])
            assert abs(c['total_seconds']-sum(l['seconds'] for l in c['legs'])) <= 1
            assert c['arrival_at'] == c['departure_at']+c['total_seconds']
            for leg in c['legs']:
                if leg['type'] == 'bus':
                    assert leg.get('geometry') and leg['vehicle_id'] is None
                    assert abs(leg['arrival_at']-leg['departure_at']-leg['seconds']) < 1
        reports.append({'origin_route_seq': seq, 'baseline_candidates': len(baseline['candidates']),
                        'candidate_candidates': len(candidate['candidates']), 'candidate_elapsed_seconds': elapsed,
                        'has_common_gate': any(c.get('common_gate_service') for c in candidate['candidates'])})
    write_json(ROOT/'artifacts/offline_planner_smoke.json', {'passed': True, 'cases': reports,
               'network': 'actual frozen eight city routes and directed road geometries',
               'walking_fixture': 'identical endpoints only; not pedestrian coverage test',
               'full_deployed_or_browser_flow_tested': False, 'shuttle_queues_tested': False,
               'runtime_adapter_revision': ADAPTER_REVISION,
               'runtime_adapter_sha256': digest(ROOT/'candidate_runtime.py'),
               'new_provider_polls': 0, 'script_sha256': digest(__file__)})
    print(json.dumps({'passed': True, 'cases': reports}))


if __name__ == '__main__':
    main()
