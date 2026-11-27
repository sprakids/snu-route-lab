def reference_run_rep(events, choices, routes, seed, walk_factor=1.0):
    rng = np.random.default_rng(seed)
    bins = defaultdict(float)
    modes = defaultdict(float)
    stopmeta = {}
    lags = []
    missing = Counter()
    for e in events:
        day = e['weekday']
        n = PARTICLES
        for group, dest in [('dorm', 'dorm_ug' if e['degree_level'] == '학사' else 'dorm_grad'), ('snu', 'snu'), ('nak', 'nak'), ('daehak', 'daehak')]:
            weight = e['enrollment'] / n
            speed = rng.triangular(0.9, 1.2, 1.5, n) * walk_factor
            scale = 1.2 / speed
            egress = rng.triangular(60, 180, 480, n)
            departure = e['end_minute'] * 60 + egress
            options = choices[e['building'], dest]
            costs = []
            arrivals = []
            phases = {rid: np.full(n, rng.random()) for rid in routes}
            for c in options:
                t = departure + c['first_walk']['seconds'] * scale
                stops = []
                for j, ride in enumerate(c['rides']):
                    if j:
                        t = t + c['transfer_walk']['seconds'] * scale
                    stops.append(t.copy())
                    t = t + 20
                    t = t + wait_seconds(routes[ride['route_id']], ride['board'], t, phases[ride['route_id']])
                    t = t + ride['ride_seconds']
                if c['rides']:
                    t = t + c['last_walk']['seconds'] * scale
                costs.append(t - departure + 120 * max(0, len(c['rides']) - 1))
                arrivals.append(stops)
            if not options:
                modes[day, group, 'unassigned'] += e['enrollment']
                missing[e['building']] += e['enrollment']
                continue
            cost = np.array(costs)
            choicecost = cost + rng.gumbel(0, 90, cost.shape)
            chosen = np.argmin(choicecost, axis=0)
            valid = np.isfinite(cost[chosen, np.arange(n)])
            _cohort_trace(e, group, chosen, valid, rng)
            modes[day, group, 'unassigned'] += float((~valid).sum()) * weight
            for ci, c in enumerate(options):
                selected = (chosen == ci) & valid
                count = int(selected.sum())
                if not count:
                    continue
                mode = 'walk' if not c['rides'] else 'shuttle_first' if c['rides'][0]['route_id'].startswith('shuttle-') else 'city_first'
                modes[day, group, mode] += count * weight
                for stage, ride in enumerate(c['rides']):
                    stopkey = (ride['stop_id'], ride['direction'], ride['route_id'])
                    stopmeta[stopkey] = ride
                    times = arrivals[ci][stage][selected] / 60
                    for minute in times:
                        b = int(minute // 5) * 5
                        bins[day, group, *stopkey, b, stage] += weight
                    if stage == 0:
                        for lag in (arrivals[ci][0][selected] - e['end_minute'] * 60) / 60:
                            lags.append((float(lag), weight, group))
    return (bins, modes, stopmeta, lags, missing)
