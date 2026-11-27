"""Choice-cost perception only; never replace a physical forecast with this view.

Apply to an original Prediction, retaining that original for actual ETA, capacity,
boarding and audit calculations.  The first timeline row is the CURRENT queue,
even if the traveller has already transferred earlier in the journey.  Later
waiting and preparation are omitted only from this perceived outlook.

Unchanged metadata, including the original physical boarding timeline, is carried
through without mutation.  That timeline is an audit trail, not a perceived clock
trajectory.  Consequently this view must not be fed back as a physical forecast.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
import math
from numbers import Real

from preferences import Prediction


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _duration(value, name):
    result = _finite(value, name)
    if result < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _sum(values, name):
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} is not a finite sum") from exc
    return _finite(result, name)


def _roundoff(*values):
    """An f64 ULP budget, not a behavioural or fixed-seconds tolerance."""
    return _finite(16.0 * _sum((math.ulp(v) for v in values), "ULP budget"),
                   "ULP tolerance")


def _close(actual, expected, name, extra=0.0):
    tolerance = _sum((_roundoff(actual, expected), extra), f"{name} tolerance")
    if abs(actual - expected) > tolerance:
        raise ValueError(f"{name} is inconsistent with the boarding timeline")


def _computed_nonnegative(value, name, tolerance):
    value = _finite(value, name)
    if value < -tolerance:
        raise ValueError(f"{name} is negative beyond f64 roundoff")
    return max(0.0, value)


def perceived_without_transfer_wait(pred: Prediction) -> Prediction:
    """Remove only later rows' wait/preparation from a choice-cost outlook.

    Time components must be finite and nonnegative. Absolute timestamps need only
    be finite because their clock origin is arbitrary. Inconsistent aggregates,
    backwards clocks or preparation exceeding a queue interval are rejected;
    only arithmetic roundoff measured in f64 ULPs is tolerated.

    A valid zero/one-row forecast is returned by identity. With later rows, eta
    loses their full intervals, wait loses their waiting portion, and prep loses
    their preparation. The current first_wait is retained, as are walk, ride and
    every other field. Squared/cubed waiting burdens retain only first_wait.
    """
    if not isinstance(pred, Prediction):
        raise TypeError("pred must be a Prediction")

    eta = _finite(pred.eta, "eta")
    durations = {
        name: _duration(getattr(pred, name), name)
        for name in ("walk", "wait", "ride", "prep", "first_wait",
                     "wait_squared", "wait_cubed")
    }
    timeline = pred.boarding_timeline
    if not isinstance(timeline, Sequence) or isinstance(timeline, (str, bytes)):
        raise ValueError("boarding_timeline must be a sequence of rows")
    if not timeline:
        return pred

    arrivals, boardings, intervals, preparations, waiting, clock_errors = [], [], [], [], [], []
    for index, row in enumerate(timeline):
        if not isinstance(row, Mapping):
            raise ValueError(f"boarding_timeline[{index}] must be a mapping")
        prefix = f"boarding_timeline[{index}]"
        try:
            arrival = _finite(row["arrival"], f"{prefix}.arrival")
            boarding = _finite(row["time"], f"{prefix}.time")
            preparation = _duration(row["preparation_seconds"],
                                    f"{prefix}.preparation_seconds")
        except KeyError as exc:
            raise ValueError(f"{prefix} is missing {exc.args[0]}") from exc
        error = _roundoff(arrival, boarding)
        interval = _computed_nonnegative(boarding - arrival, f"{prefix} interval", error)
        if boardings:
            _computed_nonnegative(arrival - boardings[-1], f"{prefix} travel clock",
                                 _roundoff(arrival, boardings[-1]))
        queue_wait = _computed_nonnegative(interval - preparation,
                                          f"{prefix} waiting",
                                          error + _roundoff(interval, preparation))
        arrivals.append(arrival)
        boardings.append(boarding)
        intervals.append(interval)
        preparations.append(preparation)
        waiting.append(queue_wait)
        clock_errors.append(error)

    clock_error = _sum(clock_errors, "timeline clock roundoff")
    total_wait = _sum(waiting, "timeline waiting")
    total_prep = _sum(preparations, "timeline preparation")
    _close(durations["wait"], total_wait, "wait", clock_error + _roundoff(*waiting))
    _close(durations["prep"], total_prep, "prep", _roundoff(*preparations))
    _close(durations["first_wait"], intervals[0], "first_wait", clock_errors[0])

    squares = [interval * interval for interval in intervals]
    cubes = [square * interval for square, interval in zip(squares, intervals)]
    square_error = _sum((2.0 * interval * error + error * error
                         for interval, error in zip(intervals, clock_errors)),
                        "squared waiting roundoff")
    cube_error = _sum((3.0 * interval * interval * error
                       + 3.0 * interval * error * error + error * error * error
                       for interval, error in zip(intervals, clock_errors)),
                      "cubed waiting roundoff")
    _close(durations["wait_squared"], _sum(squares, "timeline wait_squared"),
           "wait_squared", square_error + _roundoff(*squares))
    _close(durations["wait_cubed"], _sum(cubes, "timeline wait_cubed"),
           "wait_cubed", cube_error + _roundoff(*cubes))

    total = _sum((durations[name] for name in ("walk", "wait", "ride", "prep")),
                 "forecast elapsed time")
    origin = _finite(eta - total, "implied forecast origin")
    before_first = _finite(arrivals[0] - origin, "first access time")
    geometry_error = clock_error + _roundoff(eta, total, origin, arrivals[0],
                                            durations["walk"])
    if before_first < -geometry_error or before_first > durations["walk"] + geometry_error:
        raise ValueError("eta/components imply impossible first access walking")
    _computed_nonnegative(eta - boardings[-1], "last ride/egress time",
                         _roundoff(eta, boardings[-1]))

    if len(timeline) <= 1:
        return pred

    removed = _sum(intervals[1:], "removed transfer intervals")
    removed_prep = _sum(preparations[1:], "removed transfer preparation")
    removed_wait = _computed_nonnegative(removed - removed_prep,
                                        "removed transfer waiting",
                                        clock_error + _roundoff(removed, removed_prep))
    remaining_wait = _computed_nonnegative(durations["wait"] - removed_wait,
                                          "remaining current waiting",
                                          clock_error + _roundoff(durations["wait"], removed_wait))
    remaining_prep = _computed_nonnegative(durations["prep"] - removed_prep,
                                          "remaining current preparation",
                                          _roundoff(durations["prep"], removed_prep))

    # Snap only verified subtraction roundoff to the unchanged CURRENT row. This
    # avoids inventing tiny waits or losing a tiny current wait by cancellation.
    current_wait = _computed_nonnegative(durations["first_wait"] - preparations[0],
                                        "current first waiting",
                                        clock_errors[0] + _roundoff(durations["first_wait"], preparations[0]))
    _close(remaining_wait, current_wait, "remaining current waiting", clock_error)
    _close(remaining_prep, preparations[0], "remaining current preparation",
           _roundoff(*preparations, durations["prep"]))
    new_eta = _finite(eta - removed, "perceived eta")
    new_total = _sum((durations["walk"], durations["ride"], current_wait, preparations[0]),
                     "perceived elapsed time")
    _close(new_eta - new_total, origin, "eta/components origin",
           clock_error + _roundoff(eta, total, new_eta, new_total))
    first_square = _finite(durations["first_wait"] * durations["first_wait"], "first_wait squared")
    first_cube = _finite(first_square * durations["first_wait"], "first_wait cubed")
    return replace(pred, eta=new_eta, wait=current_wait, prep=preparations[0],
                   wait_squared=first_square, wait_cubed=first_cube)
