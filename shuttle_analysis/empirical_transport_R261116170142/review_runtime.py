"""Review-only composition: passing child components, preserved parent ride.

This adapter does not fit parameters. It supplies the same directed, unflagged
gate evidence contract used by the frozen evaluation and applies its fixed gate.
"""
from functools import lru_cache
from pathlib import Path
import json

from empirical_transport import EmpiricalTransport
from parent_transport import EmpiricalTransport as ParentTransport
from candidate_runtime import install_candidate as install_raw_candidate

ROOT = Path(__file__).resolve().parent
GATE = '120000029'


class ReviewModel:
    def __init__(self, candidate, parent, policy):
        self.candidate, self.parent, self.policy = candidate, parent, policy
        self.data, self.model_id = candidate.data, candidate.model_id
        self.accepted = frozenset(policy['shadow_enabled_components'])
        self.gate_sequences = {x['r']: x['s'] for x in candidate.data['gate_events']}

    def meta(self):
        return {**self.candidate.meta(), 'runtime_composition': {
            k: self.model_id if k in self.accepted else self.parent.model_id if k != 'crowd' else 'legacy_continuity'
            for k in ['headway', 'ride', 'crowd', 'gate']}, 'operating_adoption': False}

    @staticmethod
    def annotate(value, selected_by, fallback):
        return {**value, 'selected_by_candidate': selected_by, 'retained_parent_component': fallback} if value else None

    def headway_wait(self, rid, seq, at, asof, **kwargs):
        p = self.candidate.headway_wait(rid, seq, at, asof, **kwargs) if 'headway' in self.accepted else None
        if p:
            return self.annotate(p, self.model_id, False)
        p = self.parent.headway_wait(rid, seq, at, asof, last_passage=kwargs.get('last_passage'))
        return self.annotate(p, self.model_id, True)

    def ride_time(self, rid, a, b, at, asof, **kwargs):
        p = self.candidate.ride_time(rid, a, b, at, asof, **kwargs) if 'ride' in self.accepted else None
        if p:
            return self.annotate(p, self.model_id, False)
        return self.annotate(self.parent.ride_time(rid, a, b, at, asof), self.model_id, True)

    def crowd(self, *args, **kwargs):
        if 'crowd' not in self.accepted:
            return None
        return self.candidate.crowd(*args, **kwargs)

    def gate_wait(self, eligible, at, asof, **kwargs):
        eligible = tuple(eligible)
        if kwargs.get('recent_passages') is not None:
            # A route's passage at ANY campus stop is not a gate passage. Filter
            # known-full vehicles before collapsing simultaneous opportunities.
            rows = [x for x in kwargs['recent_passages'] if x.get('r') in eligible and x.get('full') is not True
                    and (x.get('stop_id') == GATE or x.get('stop_id') is None and x.get('s') == self.gate_sequences.get(x.get('r')))]
            rows = self.candidate.causal_passages(rows, at, asof, eligible)
            kwargs['recent_passages'] = rows
            kwargs['last_passage'] = max((x['at'] for x in rows), default=None)
        p = self.candidate.gate_wait(eligible, at, asof, **kwargs) if 'gate' in self.accepted else None
        if p:
            return self.annotate(p, self.model_id, False)
        p = self.parent.gate_wait(eligible, at, asof, last_passage=kwargs.get('last_passage'))
        return self.annotate(p, self.model_id, True)


@lru_cache(maxsize=1)
def load_review_model():
    # One immutable model object per worker, rather than rereading it per search.
    data = json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))
    previous = json.loads((ROOT.parent/'empirical_transport_261116162001/artifacts/profile.json').read_text(encoding='utf-8'))
    policy = json.loads((ROOT/'artifacts/final_component_policy.json').read_text(encoding='utf-8'))
    return ReviewModel(EmpiricalTransport(data), ParentTransport(previous), policy)


def install_review_candidate(planner, network_sha256):
    model = load_review_model()
    enabled = {'headway', 'ride', 'gate'} | ({'crowd'} if 'crowd' in model.accepted else set())
    return install_raw_candidate(planner, model, enabled, network_sha256)
