"""R261116164131: integer-second API fix; frozen fitted model stays untouched."""
import candidate_runtime as frozen

ADAPTER_REVISION = 'R261116164131'


class TravelAdapter(frozen.TravelAdapter):
    def estimate(self, route, i, j, when, snapshot=None, live=False):
        value = super().estimate(route, i, j, when, snapshot, live)
        if value.get('source') != 'observed_directed_stop_passage_time':
            return value
        # A median of two integer observed durations can end in .5s. Planner
        # headers round totals, so make the leg obey its existing integer API.
        return {**value, 'seconds': max(1, round(value['seconds'])),
                'runtime_adapter_revision': ADAPTER_REVISION}


def install_candidate(planner, profile, enabled, network_sha256, patch_gate=True):
    undo = frozen.install_candidate(planner, profile, enabled, network_sha256, patch_gate)
    previous = planner.travel
    planner.travel = TravelAdapter(previous.baseline, profile, planner.transit, enabled)
    return undo
