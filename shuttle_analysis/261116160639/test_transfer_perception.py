"""Source-only handoff tests; integration owner runs them after wiring policy."""

import copy
from dataclasses import fields, replace
import math
import unittest

from perception import perceived_without_transfer_wait
from preferences import Prediction


def three_boardings():
    # Start1000, walk60, first prep20/wait100, ride180/walk40,
    # second prep20/wait180, ride120/walk30, third prep10/wait90,
    # then ride150/walk10. All expected values below follow this itinerary.
    return Prediction(
        eta=2010.0, walk=140.0, wait=370.0, ride=450.0, prep=50.0,
        transfers=2, fare=1500.0, crowd_exposure=275.0, fatigue=12.0,
        first_wait=120.0, wait_squared=64400.0, wait_cubed=10728000.0,
        empirical_context=({"source": "retained observation", "grade": 3},),
        boarding_load_projections=({"vehicle": 7, "capacity": 44.0},),
        boarding_timeline=(
            {"arrival": 1060.0, "time": 1180.0, "preparation_seconds": 20.0, "node": 0},
            {"arrival": 1400.0, "time": 1600.0, "preparation_seconds": 20.0, "node": 1},
            {"arrival": 1750.0, "time": 1850.0, "preparation_seconds": 10.0, "node": 2},
        ),
    )


def immediate_current_boarding():
    # Same rides/walks and later intervals as above; current wait/prep are zero.
    return Prediction(
        eta=1890.0, walk=140.0, ride=450.0, wait=270.0, prep=30.0,
        first_wait=0.0, wait_squared=50000.0, wait_cubed=9000000.0,
        boarding_timeline=(
            {"arrival": 1060.0, "time": 1060.0, "preparation_seconds": 0.0},
            {"arrival": 1280.0, "time": 1480.0, "preparation_seconds": 20.0},
            {"arrival": 1630.0, "time": 1730.0, "preparation_seconds": 10.0},
        ),
    )


class TransferPerceptionTests(unittest.TestCase):
    def test_multiple_later_queues_removed_but_current_queue_kept(self):
        actual = three_boardings()
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual(perceived.eta, 1710.0)  # Remove later200+100, not first120.
        self.assertEqual(perceived.wait, 100.0)  # Remove180+90 waiting seconds.
        self.assertEqual(perceived.prep, 20.0)   # Remove later20+10 preparation.
        self.assertEqual(perceived.first_wait, 120.0)
        self.assertEqual(perceived.wait_squared, 14400.0)
        self.assertEqual(perceived.wait_cubed, 1728000.0)

    def test_keep_position_with_zero_first_preparation(self):
        actual = three_boardings()
        rows = copy.deepcopy(actual.boarding_timeline)
        rows[0]["preparation_seconds"] = 0.0
        actual = replace(actual, wait=390.0, prep=30.0, boarding_timeline=rows)
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual(perceived.wait, 120.0)
        self.assertEqual(perceived.prep, 0.0)
        self.assertEqual(perceived.first_wait, 120.0)
        self.assertEqual(perceived.eta, 1710.0)

    def test_later_preparation_removed_even_without_later_queue_wait(self):
        actual = Prediction(
            eta=1290.0, walk=30.0, ride=180.0, wait=60.0, prep=20.0,
            first_wait=60.0, wait_squared=4000.0, wait_cubed=224000.0,
            boarding_timeline=(
                {"arrival": 1020.0, "time": 1080.0, "preparation_seconds": 0.0},
                {"arrival": 1190.0, "time": 1210.0, "preparation_seconds": 20.0},
            ),
        )
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual((perceived.eta, perceived.wait, perceived.prep), (1270.0, 60.0, 0.0))
        self.assertEqual((perceived.wait_squared, perceived.wait_cubed), (3600.0, 216000.0))

    def test_past_transfer_count_does_not_erase_the_current_queue(self):
        actual = replace(three_boardings(), transfers=3)
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual(perceived.transfers, 3)
        self.assertEqual((perceived.wait, perceived.prep, perceived.first_wait), (100.0, 20.0, 120.0))

    def test_single_remaining_queue_is_returned_by_identity_after_past_transfer(self):
        actual = Prediction(
            eta=1200.0, walk=40.0, ride=100.0, wait=40.0, prep=20.0,
            transfers=1, first_wait=60.0, wait_squared=3600.0, wait_cubed=216000.0,
            boarding_timeline=({"arrival": 1040.0, "time": 1100.0,
                                "preparation_seconds": 20.0},),
        )
        self.assertIs(perceived_without_transfer_wait(actual), actual)

    def test_walk_only_forecast_is_returned_by_identity(self):
        actual = Prediction(eta=1120.0, walk=120.0)
        self.assertIs(perceived_without_transfer_wait(actual), actual)

    def test_original_and_all_other_fields_are_unchanged(self):
        actual = three_boardings()
        before = copy.deepcopy(actual)
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual(actual, before)
        self.assertIsNot(actual, perceived)
        changed = {"eta", "wait", "prep", "wait_squared", "wait_cubed"}
        for field in fields(actual):
            if field.name not in changed:
                with self.subTest(field=field.name):
                    self.assertEqual(getattr(perceived, field.name), getattr(before, field.name))
        self.assertIs(perceived.boarding_timeline, actual.boarding_timeline)
        self.assertIs(perceived.empirical_context, actual.empirical_context)
        self.assertIs(perceived.boarding_load_projections, actual.boarding_load_projections)

    def test_eta_and_components_keep_the_same_forecast_origin(self):
        actual = three_boardings()
        perceived = perceived_without_transfer_wait(actual)
        self.assertEqual(actual.eta - sum((actual.walk, actual.wait, actual.ride, actual.prep)), 1000.0)
        self.assertEqual(perceived.eta - sum((perceived.walk, perceived.wait, perceived.ride, perceived.prep)), 1000.0)
        self.assertEqual(actual.eta - perceived.eta,
                         (actual.wait - perceived.wait) + (actual.prep - perceived.prep))

    def test_no_ghost_wait_from_one_ulp_subtraction_error(self):
        actual = immediate_current_boarding()
        for direction in (0.0, math.inf):
            with self.subTest(direction=direction):
                rounded = replace(actual, wait=math.nextafter(actual.wait, direction))
                perceived = perceived_without_transfer_wait(rounded)
                self.assertEqual((perceived.wait, perceived.prep), (0.0, 0.0))
                self.assertEqual(perceived.eta, 1590.0)

    def test_absolute_clock_translation_does_not_change_removed_wait(self):
        actual = three_boardings()
        offset = 86400.0
        shifted = replace(actual, eta=actual.eta + offset,
                          boarding_timeline=tuple({**row, "time": row["time"] + offset,
                                                   "arrival": row["arrival"] + offset}
                                                  for row in actual.boarding_timeline))
        perceived = perceived_without_transfer_wait(shifted)
        self.assertEqual(perceived.eta, 1710.0 + offset)
        self.assertEqual((perceived.wait, perceived.prep), (100.0, 20.0))

    def test_negative_time_components_are_rejected(self):
        actual = three_boardings()
        for name in ("walk", "wait", "ride", "prep", "first_wait", "wait_squared", "wait_cubed"):
            with self.subTest(field=name):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, **{name: -1.0}))

    def test_nonfinite_time_inputs_are_rejected(self):
        actual = three_boardings()
        for name in ("eta", "wait", "prep", "first_wait"):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(field=name, value=value):
                    with self.assertRaises(ValueError):
                        perceived_without_transfer_wait(replace(actual, **{name: value}))

    def test_preparation_must_fit_its_queue_interval(self):
        actual = three_boardings()
        for preparation in (-1.0, 201.0):
            rows = copy.deepcopy(actual.boarding_timeline)
            rows[1]["preparation_seconds"] = preparation
            with self.subTest(preparation=preparation):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, boarding_timeline=rows))

    def test_backwards_boarding_or_transfer_clocks_are_rejected(self):
        actual = three_boardings()
        for update in ({"time": 1399.0}, {"arrival": 1179.0}):
            rows = copy.deepcopy(actual.boarding_timeline)
            rows[1].update(update)
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, boarding_timeline=rows))

    def test_timeline_and_aggregate_wait_preparation_must_agree(self):
        actual = three_boardings()
        for changes in ({"wait": 369.0}, {"prep": 49.0}, {"first_wait": 119.0}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, **changes))

    def test_inconsistent_waiting_moments_are_rejected(self):
        actual = three_boardings()
        for name in ("wait_squared", "wait_cubed"):
            with self.subTest(field=name):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, **{name: getattr(actual, name) + 1.0}))

    def test_impossible_eta_component_and_timeline_combinations_are_rejected(self):
        actual = three_boardings()
        for eta in (1849.0, 1900.0, 2200.0):
            with self.subTest(eta=eta):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, eta=eta))

    def test_missing_or_nonfinite_timeline_values_are_rejected(self):
        actual = three_boardings()
        for mutation in ("missing", "nan", "nonmapping"):
            rows = list(copy.deepcopy(actual.boarding_timeline))
            if mutation == "missing":
                del rows[1]["preparation_seconds"]
            elif mutation == "nan":
                rows[1]["time"] = math.nan
            else:
                rows[1] = 7
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    perceived_without_transfer_wait(replace(actual, boarding_timeline=rows))

    def test_timeline_must_be_a_sequence_of_rows(self):
        with self.assertRaises(ValueError):
            perceived_without_transfer_wait(replace(three_boardings(), boarding_timeline="invalid"))

    def test_material_error_is_not_hidden_by_roundoff_tolerance(self):
        actual = immediate_current_boarding()
        with self.assertRaises(ValueError):
            perceived_without_transfer_wait(replace(actual, wait=actual.wait - 0.0001))

    def test_non_prediction_input_is_rejected(self):
        with self.assertRaises(TypeError):
            perceived_without_transfer_wait({"eta": 1000.0})


if __name__ == "__main__":
    unittest.main()
