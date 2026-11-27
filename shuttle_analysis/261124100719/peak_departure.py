"""Increase the earlier R curve's deviation from its daily mean before routing."""
import math
from collections import Counter

from departure import BASE_PROBABILITY, MAX_CHANGE as PREVIOUS_MAX_CHANGE
from departure import apply_departures as previous_departures

CONTRAST = 3
MAX_CHANGE = PREVIOUS_MAX_CHANGE * CONTRAST


def amplify(probability):
    revised = BASE_PROBABILITY + CONTRAST * (probability - BASE_PROBABILITY)
    if not 0 <= revised <= 1:
        raise ValueError(f'Invalid departure probability {revised}')
    return revised


def apply_departures(bundle, events, day, converted):
    # The previous model identifies the course of every plan and checks its enrollment.
    profile = previous_departures(bundle, events, day, converted)
    ratios = {}
    for row in profile['rate_by_class_end']:
        old = row['probability']
        new = amplify(old)
        row['probability'] = new
        row['immediate_trip_mass'] = row['enrollment'] * new
        row['other_activity_mass'] = row['enrollment'] - row['immediate_trip_mass']
        ratios[row['end_minute']] = new / old

    plans = bundle['prepared']['plans'][day]
    by_minute = Counter()
    for i, plan in enumerate(plans):
        uid = plan[0]
        minute = events[(uid - 1) // 48]['end_minute']
        weight = plan[3] * ratios[minute]
        plans[i] = [*plan[:3], weight, *plan[4:]]
        by_minute[minute] += weight
        if uid in converted:
            _, path, duration = converted[uid]
            converted[uid] = (weight, path, duration)

    for row in profile['rate_by_class_end']:
        assert math.isclose(by_minute[row['end_minute']], row['immediate_trip_mass'], abs_tol=1e-7)
    total = math.fsum(p[3] for p in plans)
    assert math.isclose(total, profile['previous_trip_mass'], abs_tol=1e-6)
    profile['total_trip_mass'] = total
    profile['hourly_clock_rates'] = {h: amplify(p) for h, p in profile['hourly_clock_rates'].items()}
    return profile
