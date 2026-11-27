"""Select the tested walk/PM setting against the observed full departure and queue."""
import json
import math
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL = HERE.parent / '261124100719'
FIELD = HERE.parent / 'field_observations_2026-11-23/full_departure_admin_daehak_1659.json'


def read(path):
    return json.loads(path.read_bytes())


def select():
    field = read(FIELD)
    assert field['vehicle_observation']['reported_full_at_departure'] is True
    observed = field['queue_observation']['reported_queue_people']
    options = []
    for rate in (60, 70, 80, 81, 82, 83, 85, 87, 90):
        folder = CONTROL if rate == 60 else HERE / 'rates' / str(rate)
        receipt, = (folder / 'runs/regular-mon').glob('attempt-*/result.json')
        result = read(receipt)
        assert result['status'] == 'verified' and result['core']['status'] == 'PASS'
        assert result['selection']['target'] == rate / 100
        event = result['candidate']
        options.append(dict(percent=rate, onboard=event['onboard'],
                            full=math.isclose(event['onboard'], event['capacity'], abs_tol=1e-6),
                            outside_queue=event['queue_after_1700'], ready_queue=event['ready_left'],
                            absolute_queue_error=abs(event['queue_after_1700'] - observed)))
    full = [r for r in options if r['full']]
    best_error = min(r['absolute_queue_error'] for r in full)
    # A single integer field count offers little precision for distinguishing sub-person differences.
    selected = min(r['percent'] for r in full if r['absolute_queue_error'] <= best_error + .5)
    record = dict(selected_percent=selected, observation_id=field['observation_id'],
                  observed_after_departure_queue=observed, observed_time='16:59', simulated_time='17:00',
                  eligible_pool='Daehak destination and original first service shuttle-daehak at its origin',
                  selection_rule='Require full onboard load, minimize whole outside queue error; prefer the smaller setting within 0.5 weighted person of the best.',
                  cases=options)
    path = HERE / 'selection.json'
    if path.exists() and read(path) != record:
        earlier = read(path)
        earlier_rates = [r['percent'] for r in earlier['cases']]
        assert earlier_rates in ([60, 70, 80, 90], [60, 70, 80, 83, 85, 87, 90])
        assert all(r in options for r in earlier['cases'])
        archive = HERE / ('selection_first_pass.json' if len(earlier_rates) == 4 else 'selection_second_pass.json')
        if not archive.exists():
            with archive.open('xb') as stream:
                stream.write(path.read_bytes())
        assert read(archive) == earlier
    temporary = HERE / 'selection.tmp'
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf8')
    os.replace(temporary, path)
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    select()
