"""Conservative joins of existing walking paths at real boarding platforms.

This catalogue never creates geometry, edits a path, or predicts free seats.
Missing directed prefix/suffix paths are a coverage limitation, not permission
to draw a straight connector. Thresholds are scenario settings, not observations.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import copy
import math


def point_key(point):
    """Use the stored coordinates exactly; rounding must not invent a join."""
    if len(point) != 2 or not all(math.isfinite(float(x)) for x in point):
        return None
    return tuple(float(x) for x in point)


def project(point, path):
    """Return lateral metres and directed arclength on a local campus polyline."""
    scale = math.pi / 180 * 6371000
    longitude_scale = scale * math.cos(math.radians(path[0][0]))
    origin = path[0]
    xy = lambda p: ((p[1] - origin[1]) * longitude_scale,
                    (p[0] - origin[0]) * scale)
    px, py = xy(point)
    best = (math.inf, 0.)
    cursor = 0.
    for a, b in zip(path, path[1:]):
        ax, ay = xy(a); bx, by = xy(b)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        fraction = max(0., min(1., ((px-ax)*dx + (py-ay)*dy) / length**2)) if length else 0.
        candidate = (math.hypot(px-ax-fraction*dx, py-ay-fraction*dy),
                     cursor + fraction*length)
        if candidate < best:
            best = candidate
        cursor += length
    return best


def follows(path, original, lateral_limit):
    """Reject off-corridor vertices and reversed progression, conservatively."""
    previous = -math.inf
    for point in path:
        lateral, progress = project(point, original)
        if lateral > lateral_limit + 1e-7 or progress < previous - 1e-6:
            return False
        previous = max(previous, progress)
    return True


def unscaled_stages(stages, factor):
    """Plans are already person-scaled; the catalogue stores nominal clocks."""
    rows = []
    for source in stages:
        entry = {**source, 'next_walk': [source['next_walk'][0], source['next_walk'][1]/factor]}
        if 'pool' in source:
            entry['pool'] = unscaled_stages(source['pool'], factor)
        if 'continuation_stages' in source:
            entry['continuation_stages'] = unscaled_stages(source['continuation_stages'], factor)
        rows.append(entry)
    return rows


@dataclass(frozen=True)
class WalkingOpportunity:
    original_path: int
    prefix_path: int
    suffix_path: int
    node: int
    prefix_seconds: float
    suffix_seconds: float
    extra_meters: float
    lateral_meters: float
    stages: tuple


class WalkingOpportunities:
    """Geometry-only cache; eligibility and actual FIFO remain in the engine."""
    def __init__(self, bundle, node_for, config):
        self.paths = bundle['prepared']['common']['paths']
        self.physical = bundle['physical_paths']
        self.node_for = node_for
        self.extra_limit = float(config.get('enroute_max_extra_meters', 80.))
        self.lateral_limit = float(config.get('enroute_max_lateral_meters', 30.))
        if not all(math.isfinite(x) and x >= 0 for x in (self.extra_limit, self.lateral_limit)):
            raise ValueError('Enroute path limits must be finite nonnegative metres')
        self.walk_ids = set()
        self.entries = defaultdict(dict)
        self.cache = {}
        self.counts = Counter()

        def remember_stages(stages):
            for stage in stages:
                self.walk_ids.add(stage['next_walk'][0])
                remember_stages(stage.get('pool', []))
                remember_stages(stage.get('continuation_stages', []))

        def remember_option(option):
            self.walk_ids.add(option['walk'][0])
            remember_stages(option['stages'])
            self.add_chain(option['stages'], option.get('_destination'))

        for key, entries in bundle.get('compatible_route_policies', {}).items():
            _, destination = key.split('|', 1)
            for entry in entries:
                remember_stages([entry]); self.add_chain([entry], destination)
        for key, entries in bundle.get('compatible_single_stage_pools', {}).items():
            _, destination = key.split('|', 1)
            for entry in entries:
                remember_stages([entry]); self.add_chain([entry], destination)
        for key, options in bundle.get('alternatives', {}).items():
            _, destination = key.split('|', 1)
            for option in options:
                remember_option({**option, '_destination': destination})
        for catalogue in ('origin_catalog', 'student_origin_catalog'):
            for options in bundle.get(catalogue, {}).values():
                for option in options:
                    # Origin catalogue keys are repr tuples. Never eval them.
                    self.walk_ids.add(option['walk'][0]); remember_stages(option['stages'])
        for plans in bundle['prepared']['plans'].values():
            for plan in plans:
                self.walk_ids.add(plan[5][0]); remember_stages(plan[6])
                destination = bundle.get('destination_keys', {}).get(str(plan[0]))
                factor = bundle.get('walk_scales', {}).get(str(plan[0]), 1.)
                self.add_chain(plan[6], destination, factor)

        self.platforms_at = defaultdict(list)
        for (anchor, node, destination), entries in self.entries.items():
            self.platforms_at[anchor, destination].append((node, entries))

        self.by_start = defaultdict(list)
        self.by_pair = defaultdict(list)
        for index in sorted(self.walk_ids):
            if not self.valid_path(index):
                continue
            path = self.paths[index]
            start, end = point_key(path[0]), point_key(path[-1])
            self.by_start[start].append(index)
            self.by_pair[start, end].append(index)

    def add_chain(self, stages, destination, factor=1.):
        if not stages or destination is None:
            return
        for source in stages[0].get('pool', [stages[0]]):
            try:
                node = self.node_for(source)
                wait_path = self.paths[source['wait_path']]
                anchor = point_key(wait_path[0])
            except (KeyError, IndexError, TypeError):
                self.counts['unsupported_platform_metadata'] += 1
                continue
            if anchor is None or node is None:
                continue
            services = self.entries[anchor, node, destination]
            service = source['rid'], source['board']
            if service in services:
                continue
            # A service owns its exact continuation, not a borrowed route tail.
            entry = copy.deepcopy(source)
            entry.pop('pool', None)
            entry.setdefault('continuation_stages', copy.deepcopy(stages[1:]))
            if factor != 1.:
                entry = unscaled_stages([entry], factor)[0]
            entry['choice_pool_locked'] = True
            services[service] = entry

    def valid_path(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.paths) or index >= len(self.physical):
            return False
        path = self.paths[index]; profile = self.physical[index]
        seconds, meters = profile.get('seconds'), profile.get('meters')
        return (len(path) >= 2 and all(point_key(p) is not None for p in path)
                and isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds > 0
                and isinstance(meters, (int, float)) and math.isfinite(meters) and meters > 0)

    def get(self, original_path, destination):
        self.counts['queries'] += 1
        key = original_path, destination
        if key in self.cache:
            self.counts['cache_hits'] += 1
            return self.cache[key]
        result = []
        if self.valid_path(original_path):
            original = self.paths[original_path]
            start, end = point_key(original[0]), point_key(original[-1])
            for prefix in self.by_start.get(start, ()):
                anchor = point_key(self.paths[prefix][-1])
                if anchor in (start, end):
                    continue
                for suffix in self.by_pair.get((anchor, end), ()):
                    extra = self.physical[prefix]['meters'] + self.physical[suffix]['meters'] - self.physical[original_path]['meters']
                    lateral, progress = project(anchor, original)
                    if (extra > self.extra_limit + 1e-7 or lateral > self.lateral_limit + 1e-7
                            or progress <= 1e-7 or not follows(self.paths[prefix], original, self.lateral_limit)
                            or not follows(self.paths[suffix], original, self.lateral_limit)):
                        continue
                    for node, services in self.platforms_at.get((anchor, destination), ()):
                        entries = list(services.values())
                        stage = {**entries[0], 'pool': entries, 'choice_pool_locked': True,
                                 'expanded_compatible_pool': True}
                        result.append(WalkingOpportunity(original_path, prefix, suffix, node,
                                      self.physical[prefix]['seconds'], self.physical[suffix]['seconds'],
                                      extra, lateral, (stage,)))
        result.sort(key=lambda op: (op.prefix_seconds, op.extra_meters, op.node, op.prefix_path, op.suffix_path))
        self.cache[key] = tuple(result)
        self.counts['distinct_queries'] += 1
        self.counts['distinct_queries_with_geometry'] += bool(result)
        self.counts['geometric_opportunities'] += len(result)
        return self.cache[key]

    def report(self):
        return {'counts': dict(self.counts), 'known_walking_path_count': len(self.walk_ids),
                'indexed_walking_path_count': sum(len(v) for v in self.by_start.values()),
                'platform_destination_count': len(self.entries),
                'max_extra_meters': self.extra_limit, 'max_lateral_meters': self.lateral_limit,
                'coverage_scope': 'Existing exact directed walking prefix/suffix and platform anchors only; missing joins leave the original walk unchanged.',
                'coordinates_created': False, 'new_paths_created': False,
                'thresholds_are_observed': False}
