"""Same-stop, one-bus OD cross-check for both rail gateway directions."""
from bisect import bisect_left
from collections import Counter

from score import HERE, PARENT, V12, PRIMARY, SERVICES, TARGET, NEAR, ENDS, folder, read, records, write_rows


def gateway(stop):
    if stop in ENDS:
        return '낙성대역·낙성대입구'
    if stop == '120000150':
        return '서울대입구역2번출구'


def count_rides(model, service, common):
    key = f'{service}-thu'
    audit = read(folder(model, key) / f'audit-{key}.json.gz')
    routes = common['city_route_stops']
    events = {(e[2], e[1], e[0]): (e[11], e[12]) for e in audit['events'] if e[11] in routes}
    counts = Counter()
    for trip in audit['legs']:
        for leg in trip['legs']:
            if leg[0] != 3 or not 17 * 3600 <= leg[1] < 21 * 3600:
                continue
            _, start, end, _, node, _, vehicle, *_ = leg
            event = events.get((vehicle, node, start))
            if not event:
                continue
            route, i = event
            board = routes[route][i]['id']
            if board not in (TARGET, NEAR):
                continue
            offsets = common['route_info'][route]['offsets']
            j = bisect_left(offsets, offsets[i] + end - start - 1e-5)
            assert abs(offsets[j] - offsets[i] - (end - start)) < 1e-5
            direction = gateway(routes[route][j]['id'])
            if direction:
                counts[board, int(start // 3600), direction] += trip['weight']
    return counts


if __name__ == '__main__':
    import sys
    measured = Counter()
    for r in records(PARENT / '11월5일_두정류장_하차지.csv'):
        stop, hour, direction = r['board_id'], int(r['hour']), gateway(r['alight_id'])
        if direction and 17 <= hour < 21:
            measured[stop, hour, direction] += int(r['measured'])
    common = read(V12 / 'viewer-data/common.json.gz')
    rows = []
    for model in PRIMARY:
        for service in SERVICES:
            estimated = count_rides(model, service, common)
            for k in sorted(measured.keys() | estimated.keys()):
                rows.append(dict(model=model, service=service, board=k[0], hour=k[1],
                                 gateway=k[2], measured=measured[k], modeled=estimated[k]))
    write_rows(HERE / '두역방면_동일승하차.csv', rows)
