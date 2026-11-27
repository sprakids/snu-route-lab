"""Small, enrollment-weighted changes to the probability of leaving after class."""
from bisect import bisect_right
from collections import Counter
import math

# Shape is interpolated at actual class termination, before egress or transit.
KNOTS = [(9*60,0), (11*60,.1), (13*60,.4), (14*60,.65), (15*60,1),
         (16*60,1), (17*60,.8), (18*60,.55), (20*60,.3), (23*60,.2)]
MINUTES = [m for m,_ in KNOTS]
BASE_PROBABILITY = .5
MAX_CHANGE = .05

def shape(t):
    i = bisect_right(MINUTES, t)
    if not i:
        return KNOTS[0][1]
    if i == len(KNOTS):
        return KNOTS[-1][1]
    a, av = KNOTS[i-1]
    b, bv = KNOTS[i]
    return av + (bv-av)*(t-a)/(b-a)

def probabilities(enrollment):
    total = sum(enrollment.values())
    center = math.fsum(n*shape(m) for m,n in enrollment.items())/total
    scale = MAX_CHANGE/max(center,1-center)
    def at(t):
        return BASE_PROBABILITY + scale*(shape(t)-center)
    return at

def class_events(source):
    return [e for e in source if e['included_main'] and e['weekday'] in '월화수목금' and e['end_minute'] <= 1390]

def apply_departures(bundle, events, day, converted):
    plans = bundle['prepared']['plans'][day]
    group_mass = Counter()
    enrollment = Counter()
    for e in events:
        if e['weekday']==day:
            enrollment[e['end_minute']] += e['enrollment']
    prob = probabilities(enrollment)
    before = math.fsum(p[3] for p in plans)
    for i,p in enumerate(plans):
        idx = (p[0]-1)//48  # V11 makes 4 destination samples of 12 particles per class event.
        event = events[idx]
        if event['weekday'] != day or str(event['building']) != p[1] or p[4]+1e-6 < 60*event['end_minute']:
            raise ValueError(f'Class identity or departure time mismatch: {p[0]}')
        group_mass[idx] += p[3]
        w = p[3]*prob(event['end_minute'])/BASE_PROBABILITY
        plans[i] = [*p[:3],w,*p[4:]]
        if p[0] in converted:
            _,pid,seconds = converted[p[0]]
            converted[p[0]] = (w,pid,seconds)
    for idx,e in enumerate(events):
        if e['weekday']==day:
            assert math.isclose(group_mass[idx], BASE_PROBABILITY*e['enrollment'],abs_tol=1e-7)
    total = math.fsum(p[3] for p in plans)
    assert math.isclose(total,before,abs_tol=1e-6) and math.isclose(total,.5*sum(enrollment.values()),abs_tol=1e-6)
    by_end = [dict(end_minute=m,enrollment=n,probability=prob(m), immediate_trip_mass=n*prob(m),
                   flat_trip_mass=.5*n, other_activity_mass=n*(1-prob(m))) for m,n in sorted(enrollment.items())]
    return dict(weekday=day, enrollments=sum(enrollment.values()), total_trip_mass=total,
                previous_trip_mass=before, rate_by_class_end=by_end, hourly_clock_rates={str(h):prob(60*h) for h in range(24)})
