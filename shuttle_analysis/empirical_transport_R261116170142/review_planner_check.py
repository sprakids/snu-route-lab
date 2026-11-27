"""Check the policy-selected runtime; frozen forecast model is not modified."""
from datetime import datetime
import json
import time
from extract_observations import ROOT, KST, load_network, write_json, digest
from offline_planner_smoke import Planner, Transit, EndpointWalker, PRESETS
from review_runtime import install_review_candidate, load_review_model


def main():
    network = load_network()
    transit = Transit(datetime(2026, 11, 16, 17, tzinfo=KST).timestamp())
    planner = Planner(network, EndpointWalker(), transit)
    model = load_review_model()
    route = next(r for r in network['routes'] if r['id'] == '100100250')
    target = next(s for s in route['stops'] if s['id'] == '120000150')
    output = []
    for seq in [16, 18, 21]:
        origin = next(s for s in route['stops'] if s['seq'] == seq)
        undo = install_review_candidate(planner, digest(ROOT/'baseline_app/data/network.json'))
        try:
            start = time.perf_counter()
            result = planner.plan((origin['lat'], origin['lon']), (target['lat'], target['lon']),
                                  transit.now(), 'history', PRESETS['fast'], include_shuttle=False)
            elapsed = time.perf_counter()-start
        finally:
            undo()
        assert result['candidates']
        empirical = []
        for c in result['candidates']:
            assert c['arrival_at'] == c['departure_at']+c['total_seconds']
            assert abs(sum(l['seconds'] for l in c['legs'])-c['total_seconds']) <= 1
            for l in c['legs']:
                if l['type'] == 'bus' and l.get('ride_model', {}).get('source') == 'observed_directed_stop_passage_time':
                    empirical.append(l['ride_model'])
        assert empirical and all(x.get('model_id') == 'R261116162001' for x in empirical)
        output.append({'origin_seq': seq, 'candidates': len(result['candidates']),
                       'empirical_parent_rides': len(empirical), 'elapsed_seconds': elapsed})
    value = {'passed': True, 'model_id': model.model_id, 'cases': output, 'component_model_versions': model.meta()['runtime_composition'],
             'snapshot_contract': 'same directed gate, known-full removed before simultaneous opportunity collapse',
             'runtime_selector_added_after_score': True, 'frozen_forecast_rules_or_parameters_modified': False,
             'independent_accuracy_of_selected_composite_not_claimed': True,
             'test_scope': 'real frozen city roads; same-endpoint walking fixture; no browser/shuttle queue accuracy claim',
             'new_provider_polls': 0,
             'runtime_adapter_sha256': digest(ROOT/'review_runtime.py')}
    write_json(ROOT/'artifacts/review_runtime_check.json', value)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
