"""Hand-derived executable examples for the offline capacity design only."""

import copy
import json
import unittest

from budget_model import project_capacity


class ProjectCapacityTests(unittest.TestCase):
    """The four named core tests are also executed against behavior mutants."""

    def test_peak_cannot_borrow_cleanup(self):
        # A decision based on after-cleanup 80 instead of peak 120 must fail.
        result = project_capacity(
            {"raw": 90},
            [{"writes_by_prefix": {"raw": 30}, "cleanup": [
                {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 40}
            ]}],
            {"cap": 100},
        )
        row = result["rounds"][0]
        self.assertEqual(row["write_peak_bytes"], 120)
        self.assertEqual(row["before_write_by_prefix"], {"raw": 90})
        self.assertEqual(row["before_write_bytes"], 90)
        self.assertEqual(row["expected_writes_by_prefix"], {"raw": 30})
        self.assertEqual(row["expected_write_bytes"], 30)
        self.assertEqual(row["after_write_by_prefix"], {"raw": 120})
        self.assertEqual(row["unique_cleanup_by_prefix"], {"raw": 40})
        self.assertEqual(row["unique_cleanup_bytes"], 40)
        self.assertEqual(row["after_cleanup_by_prefix"], {"raw": 80})
        self.assertEqual(row["after_cleanup_bytes"], 80)
        self.assertTrue(row["thresholds"]["cap"]["reached"],
                        "PEAK_DECISION_MUST_USE_WRITE_PEAK")
        self.assertEqual(row["thresholds"]["cap"], {
            "threshold_bytes": 100,
            "before_headroom_bytes": 10,
            "peak_headroom_bytes": -20,
            "after_cleanup_headroom_bytes": 20,
            "reached": True,
            "exceeded": True,
        })

    def test_shared_raw_cleanup_once_across_rounds(self):
        # Counting both generation references frees 60, not the physical 30.
        shared = {"object_id": "scope:raw:shared:v1", "prefix": "raw", "size_bytes": 30}
        result = project_capacity(
            {"raw": 100},
            [
                {"writes_by_prefix": {}, "cleanup": [shared, dict(shared)]},
                {"writes_by_prefix": {}, "cleanup": [dict(shared)]},
            ],
            {"cap": 200},
        )
        first, second = result["rounds"]
        self.assertEqual(first["unique_cleanup_bytes"], 30, "SHARED_PHYSICAL_CLEANUP_ONCE")
        self.assertEqual(first["after_cleanup_bytes"], 70)
        self.assertEqual(second["before_write_bytes"], 70)
        self.assertEqual(second["unique_cleanup_bytes"], 0)
        self.assertEqual(second["after_cleanup_bytes"], 70)
        self.assertEqual(result["final_by_prefix"], {"raw": 70})

    def test_empty_cleanup_zero_writes_preserve_totals(self):
        # Replacing balances with zero when writes are empty loses 30 bytes.
        result = project_capacity(
            {"raw": 10, "copies": 20},
            [{"writes_by_prefix": {}, "cleanup": []}],
            {"cap": 100},
        )
        row = result["rounds"][0]
        self.assertEqual(row["before_write_bytes"], 30, "EMPTY_WRITES_KEEP_BALANCE")
        self.assertEqual(row["write_peak_bytes"], 30)
        self.assertEqual(row["after_cleanup_bytes"], 30)
        self.assertEqual(row["before_write_by_prefix"], {"raw": 10, "copies": 20})
        self.assertEqual(row["after_write_by_prefix"], {"raw": 10, "copies": 20})
        self.assertEqual(row["after_cleanup_by_prefix"], {"raw": 10, "copies": 20})
        self.assertEqual(row["unique_cleanup_by_prefix"], {"raw": 0, "copies": 0})
        self.assertEqual(row["expected_write_bytes"], 0)
        self.assertEqual(row["unique_cleanup_bytes"], 0)
        self.assertEqual(row["thresholds"]["cap"], {
            "threshold_bytes": 100,
            "before_headroom_bytes": 70,
            "peak_headroom_bytes": 70,
            "after_cleanup_headroom_bytes": 70,
            "reached": False,
            "exceeded": False,
        })

    def test_equality_reached_not_exceeded(self):
        # A strict > reached comparison incorrectly rejects exact equality.
        result = project_capacity(
            {"raw": 90},
            [{"writes_by_prefix": {"raw": 10}, "cleanup": [
                {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 20}
            ]}],
            {"cap": 100},
        )
        row = result["rounds"][0]
        self.assertTrue(row["thresholds"]["cap"]["reached"], "EQUALITY_IS_REACHED")
        self.assertFalse(row["thresholds"]["cap"]["exceeded"])
        self.assertEqual(row["write_peak_bytes"], 100)
        self.assertEqual(row["thresholds"]["cap"]["peak_headroom_bytes"], 0)
        self.assertEqual(row["after_cleanup_bytes"], 80)

    def test_chronology_and_projected_high_water_persist(self):
        result = project_capacity(
            {"raw": 90, "copies": 10},
            [
                {"writes_by_prefix": {"raw": 30}, "cleanup": [
                    {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 80}
                ]},
                {"writes_by_prefix": {"copies": 20}, "cleanup": [
                    {"object_id": "scope:copies:b:v1", "prefix": "copies", "size_bytes": 25}
                ]},
            ],
            {"cap": 100},
        )
        first, second = result["rounds"]
        self.assertEqual(first["after_cleanup_by_prefix"], {"raw": 40, "copies": 10})
        self.assertEqual(second["before_write_by_prefix"], {"raw": 40, "copies": 10})
        self.assertEqual(second["before_write_bytes"], 50)
        self.assertEqual(second["write_peak_bytes"], 70)
        self.assertEqual(second["after_cleanup_bytes"], 45)
        self.assertEqual(second["thresholds"]["cap"]["before_headroom_bytes"], 50)
        self.assertEqual(second["thresholds"]["cap"]["peak_headroom_bytes"], 30)
        self.assertEqual(result["projected_high_water_bytes"], 130)
        self.assertEqual(result["final_by_prefix"], {"raw": 40, "copies": 5})
        self.assertEqual(result["final_bytes"], 45)

    def test_no_rounds_preserves_initial_high_water_and_headroom(self):
        result = project_capacity({"raw": 120}, [], {"cap": 100})
        self.assertEqual(result["initial"], {
            "by_prefix": {"raw": 120}, "total_bytes": 120, "headroom_bytes": {"cap": -20}
        })
        self.assertEqual(result["rounds"], [])
        self.assertEqual(result["projected_high_water_bytes"], 120)
        self.assertEqual(result["final_bytes"], 120)

    def test_empty_inventory_and_no_rounds(self):
        result = project_capacity({}, [], {"cap": 100})
        self.assertEqual(result["initial"], {
            "by_prefix": {}, "total_bytes": 0, "headroom_bytes": {"cap": 100}
        })
        self.assertEqual(result["projected_high_water_bytes"], 0)
        self.assertEqual(result["final_by_prefix"], {})
        self.assertEqual(result["final_bytes"], 0)

    def test_explicit_zero_values_and_empty_thresholds(self):
        result = project_capacity(
            {"raw": 0},
            [{"writes_by_prefix": {"raw": 0}, "cleanup": [
                {"object_id": "scope:raw:zero:v1", "prefix": "raw", "size_bytes": 0}
            ]}],
            {},
        )
        self.assertEqual(result["rounds"][0]["after_cleanup_bytes"], 0)
        self.assertEqual(result["rounds"][0]["thresholds"], {})
        self.assertEqual(result["initial"]["headroom_bytes"], {})
        self.assertEqual(result["thresholds"], {})

    def test_default_thresholds_use_decimal_bytes(self):
        result = project_capacity(
            {"raw": 6_999_999_999},
            [{"writes_by_prefix": {"raw": 1}, "cleanup": []}],
        )
        self.assertEqual(result["thresholds"], {
            "warning_7gb": 7_000_000_000,
            "freeze_8_5gb": 8_500_000_000,
            "stop_9gb": 9_000_000_000,
        })
        reports = result["rounds"][0]["thresholds"]
        self.assertEqual(reports["warning_7gb"]["peak_headroom_bytes"], 0)
        self.assertTrue(reports["warning_7gb"]["reached"])
        self.assertFalse(reports["warning_7gb"]["exceeded"])
        self.assertEqual(reports["freeze_8_5gb"]["peak_headroom_bytes"], 1_500_000_000)
        self.assertFalse(reports["freeze_8_5gb"]["reached"])
        self.assertEqual(reports["stop_9gb"]["peak_headroom_bytes"], 2_000_000_000)

    def test_custom_confirmation_line_is_reporting_not_permission(self):
        result = project_capacity(
            {"raw": 7_999_999_999},
            [{"writes_by_prefix": {"raw": 2}, "cleanup": []}],
            {"confirmation_8gb": 8_000_000_000},
        )
        report = result["rounds"][0]["thresholds"]["confirmation_8gb"]
        self.assertEqual(result["thresholds"], {"confirmation_8gb": 8_000_000_000})
        self.assertEqual(report["peak_headroom_bytes"], -1)
        self.assertTrue(report["reached"])
        self.assertTrue(report["exceeded"])
        self.assertFalse(result["thresholds_are_operational_permission"])

    def test_integer_precision_beyond_float_exact_range(self):
        result = project_capacity(
            {"raw": 9_007_199_254_740_993},
            [{"writes_by_prefix": {"raw": 2}, "cleanup": [
                {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 1}
            ]}],
            {"cap": 9_007_199_254_740_994},
        )
        row = result["rounds"][0]
        self.assertEqual(row["write_peak_bytes"], 9_007_199_254_740_995)
        self.assertEqual(row["after_cleanup_bytes"], 9_007_199_254_740_994)
        self.assertEqual(row["thresholds"]["cap"]["peak_headroom_bytes"], -1)
        self.assertEqual(row["thresholds"]["cap"]["after_cleanup_headroom_bytes"], 0)

    def test_distinct_physical_ids_count_even_if_content_is_identical(self):
        result = project_capacity(
            {"raw": 100},
            [{"writes_by_prefix": {}, "cleanup": [
                {"object_id": "scope:raw:hash-copy1:v1", "prefix": "raw", "size_bytes": 30},
                {"object_id": "scope:raw:hash-copy2:v1", "prefix": "raw", "size_bytes": 30},
            ]}],
        )
        self.assertEqual(result["rounds"][0]["unique_cleanup_bytes"], 60)
        self.assertEqual(result["final_bytes"], 40)

    def test_same_id_is_not_recreated_by_aggregated_writes(self):
        shared = {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 30}
        result = project_capacity(
            {"raw": 30},
            [
                {"writes_by_prefix": {}, "cleanup": [shared]},
                {"writes_by_prefix": {"raw": 30}, "cleanup": [shared]},
                {"writes_by_prefix": {}, "cleanup": [
                    {"object_id": "scope:raw:a:v2", "prefix": "raw", "size_bytes": 30}
                ]},
            ],
        )
        self.assertEqual(result["rounds"][1]["unique_cleanup_bytes"], 0)
        self.assertEqual(result["rounds"][1]["after_cleanup_bytes"], 30)
        self.assertEqual(result["rounds"][2]["unique_cleanup_bytes"], 30)
        self.assertEqual(result["final_bytes"], 0)

    def test_inputs_and_output_snapshots_are_independent(self):
        current = {"raw": 90}
        rounds = [{"writes_by_prefix": {"raw": 30}, "cleanup": [
            {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 40}
        ]}]
        thresholds = {"cap": 100}
        original = copy.deepcopy((current, rounds, thresholds))
        result = project_capacity(current, rounds, thresholds)
        self.assertEqual((current, rounds, thresholds), original)
        result["initial"]["by_prefix"]["raw"] = 999
        result["rounds"][0]["before_write_by_prefix"]["raw"] = 888
        result["rounds"][0]["expected_writes_by_prefix"]["raw"] = 777
        result["thresholds"]["cap"] = 666
        self.assertEqual((current, rounds, thresholds), original)
        self.assertEqual(result["rounds"][0]["after_write_by_prefix"], {"raw": 120})
        self.assertEqual(result["rounds"][0]["after_cleanup_by_prefix"], {"raw": 80})
        self.assertEqual(result["final_by_prefix"], {"raw": 80})

    def test_json_output_and_explicit_conditional_supplied_scope(self):
        result = project_capacity({"raw": 1}, [])
        decoded = json.loads(json.dumps(result, allow_nan=False))
        self.assertEqual(decoded, result)
        scope = result["scope"]
        self.assertEqual(scope["kind"], "supplied_prefixes_only")
        self.assertEqual(scope["prefixes"], ["raw"])
        self.assertFalse(scope["account_wide_completeness_verified"])
        self.assertFalse(scope["physical_object_existence_verified"])
        self.assertFalse(scope["cleanup_eligibility_verified"])
        self.assertFalse(scope["historical_observed_high_water_verified"])
        self.assertEqual(result["cleanup_assumption"],
                         "caller_supplied_hypothetical_eligible_physical_objects")

    def test_same_id_conflicting_metadata_within_and_across_rounds(self):
        original = {"object_id": "scope:shared:v1", "prefix": "raw", "size_bytes": 30}
        for conflict in (
            {"object_id": "scope:shared:v1", "prefix": "raw", "size_bytes": 31},
            {"object_id": "scope:shared:v1", "prefix": "copies", "size_bytes": 30},
        ):
            for rounds in (
                [{"writes_by_prefix": {}, "cleanup": [original, conflict]}],
                [{"writes_by_prefix": {}, "cleanup": [original]},
                 {"writes_by_prefix": {}, "cleanup": [conflict]}],
            ):
                with (
                    self.subTest(conflict=conflict, rounds=rounds),
                    self.assertRaisesRegex(ValueError, "conflicting metadata"),
                ):
                    project_capacity({"raw": 100, "copies": 100}, rounds)

    def test_cleanup_underflow_is_prefix_specific_after_writes(self):
        # Aggregate 101 cannot cover removing 2 from the one-byte raw category.
        with self.assertRaisesRegex(ValueError, "cleanup exceeds.*raw"):
            project_capacity(
                {"raw": 1, "copies": 100},
                [{"writes_by_prefix": {}, "cleanup": [
                    {"object_id": "scope:raw:a:v1", "prefix": "raw", "size_bytes": 2}
                ]}],
            )

    def test_distinct_cleanup_objects_are_summed_before_overdraft_check(self):
        with self.assertRaisesRegex(ValueError, "cleanup exceeds"):
            project_capacity({"raw": 5}, [{"writes_by_prefix": {}, "cleanup": [
                {"object_id": "scope:a:v1", "prefix": "raw", "size_bytes": 3},
                {"object_id": "scope:b:v1", "prefix": "raw", "size_bytes": 3},
            ]}])

    def test_caller_hypothesis_may_use_bytes_available_after_writes(self):
        result = project_capacity({"raw": 0}, [{
            "writes_by_prefix": {"raw": 10},
            "cleanup": [{"object_id": "scope:hypothetical:v1", "prefix": "raw", "size_bytes": 10}],
        }])
        self.assertEqual(result["rounds"][0]["write_peak_bytes"], 10)
        self.assertEqual(result["final_bytes"], 0)
        self.assertFalse(result["scope"]["physical_object_existence_verified"])

    def test_rejects_bool_float_negative_and_noninteger_byte_values(self):
        for bad in (True, False, 1.0, -1, "1", None):
            for place in ("current", "write", "cleanup"):
                with self.subTest(value=bad, place=place):
                    current = {"raw": bad if place == "current" else 10}
                    writes = {"raw": bad} if place == "write" else {}
                    cleanup = ([{"object_id": "scope:a:v1", "prefix": "raw", "size_bytes": bad}]
                               if place == "cleanup" else [])
                    error = ValueError if type(bad) is int else TypeError
                    with self.assertRaises(error):
                        project_capacity(current, [{"writes_by_prefix": writes, "cleanup": cleanup}])

    def test_thresholds_require_positive_integer_values(self):
        for bad in (True, False, 1.0, -1, 0, "1", None):
            with self.subTest(value=bad):
                error = ValueError if type(bad) is int else TypeError
                with self.assertRaises(error):
                    project_capacity({}, [], {"cap": bad})

    def test_invalid_identity_prefix_and_threshold_names(self):
        for bad in ("", " ", " raw", "raw ", "raw\nchild", "raw\x00child", 1, None):
            for place in ("current", "write", "cleanup_prefix", "object_id", "threshold"):
                with self.subTest(value=bad, place=place):
                    current = {bad: 10} if place == "current" else {"raw": 10}
                    writes = {bad: 0} if place == "write" else {}
                    cleanup = []
                    if place in ("cleanup_prefix", "object_id"):
                        cleanup = [{"object_id": bad if place == "object_id" else "scope:a:v1",
                                    "prefix": bad if place == "cleanup_prefix" else "raw",
                                    "size_bytes": 0}]
                    thresholds = {bad: 100} if place == "threshold" else None
                    error = ValueError if isinstance(bad, str) else TypeError
                    with self.assertRaises(error):
                        project_capacity(current, [{"writes_by_prefix": writes, "cleanup": cleanup}],
                                         thresholds)

    def test_undeclared_prefixes_are_rejected_even_with_zero_bytes(self):
        for round_plan in (
            {"writes_by_prefix": {"other": 0}, "cleanup": []},
            {"writes_by_prefix": {}, "cleanup": [
                {"object_id": "scope:a:v1", "prefix": "other", "size_bytes": 0}
            ]},
        ):
            with (
                self.subTest(round_plan=round_plan),
                self.assertRaisesRegex(ValueError, "undeclared prefix"),
            ):
                project_capacity({"raw": 10}, [round_plan])

    def test_unknown_or_missing_round_fields_are_rejected(self):
        for round_plan in (
            {}, {"writes_by_prefix": {}}, {"cleanup": []},
            {"writes_by_prefix": {}, "cleanup": [], "net_growth": 0},
        ):
            with (
                self.subTest(round_plan=round_plan),
                self.assertRaisesRegex(ValueError, "fields"),
            ):
                project_capacity({}, [round_plan])

    def test_unknown_or_missing_cleanup_fields_are_rejected(self):
        for cleanup in (
            {}, {"object_id": "scope:a:v1", "prefix": "raw"},
            {"object_id": "scope:a:v1", "size_bytes": 0},
            {"prefix": "raw", "size_bytes": 0},
            {"object_id": "scope:a:v1", "prefix": "raw", "size_bytes": 0, "generation": "a"},
        ):
            with (
                self.subTest(cleanup=cleanup),
                self.assertRaisesRegex(ValueError, "fields"),
            ):
                project_capacity({"raw": 10}, [{"writes_by_prefix": {}, "cleanup": [cleanup]}])

    def test_rejects_wrong_container_types(self):
        calls = (
            ([], [], None), (None, [], None),
            ({}, {}, None), ({}, "", None), ({}, iter([]), None),
            ({}, [None], None), ({}, [{"writes_by_prefix": [], "cleanup": []}], None),
            ({}, [{"writes_by_prefix": {}, "cleanup": {}}], None),
            ({}, [{"writes_by_prefix": {}, "cleanup": ""}], None),
            ({}, [{"writes_by_prefix": {}, "cleanup": [None]}], None),
            ({}, [], []),
        )
        for current, rounds, thresholds in calls:
            with (
                self.subTest(current=current, rounds=rounds, thresholds=thresholds),
                self.assertRaises(TypeError),
            ):
                project_capacity(current, rounds, thresholds)

    def test_ordinary_tuple_sequences_are_accepted(self):
        result = project_capacity({"raw": 10}, ({"writes_by_prefix": {}, "cleanup": ()},))
        self.assertEqual(result["final_bytes"], 10)


if __name__ == "__main__":
    unittest.main()
