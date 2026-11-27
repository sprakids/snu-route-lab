"""Adjacent detected-stop elapsed-time calibration; never infer riders or dwell."""
from collections import defaultdict
import bisect, math, statistics

TRAIN_DATES = ('2026-11-10',)
CHECK_DATES = ('2026-11-11',)
MIN_TRAIN_INTERVALS = 5

def collect_training(rows, dates=TRAIN_DATES):
    buckets = defaultdict(list)
    for row in rows:
        if row['day'] not in dates or int(row['to_seq']) != int(row['from_seq']) + 1:
            continue
        key = (row['route'], int(row['from_seq']), int(row['to_seq']), int(row['hour']))
        for seconds in row['seconds']:
            assert isinstance(seconds, (int, float)) and math.isfinite(seconds) and 0 < seconds <= 1800
            buckets[key].append(float(seconds))
    return dict(buckets)

def estimate(values, prior, minimum, minimum_n=MIN_TRAIN_INTERVALS):
    assert math.isfinite(prior) and math.isfinite(minimum) and prior > 0 and minimum > 0
    assert prior >= minimum - 1e-5
    if len(values) < minimum_n:
        return float(prior), 'preserved_insufficient_training_intervals'
    return max(float(minimum), float(statistics.median(values))), 'training_adjacent_detected_stop_median'

def profile_at(route, seconds, weekday='2'):
    profiles = route['segment_profiles'][str(weekday)]
    index = bisect.bisect_right([p[0] for p in profiles], seconds) - 1
    return profiles[max(0, min(len(profiles) - 1, index))][2]

def error_summary(samples):
    """Each observation is a detected interval, not an independent person/day."""
    if not samples:
        return {'n': 0, 'mae_seconds': None, 'mean_error_seconds': None, 'rmse_seconds': None}
    return {'n': len(samples), 'mae_seconds': statistics.mean(abs(x) for x in samples),
            'mean_error_seconds': statistics.mean(samples),
            'rmse_seconds': math.sqrt(statistics.mean(x*x for x in samples))}
