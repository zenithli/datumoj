"""Execute four behavior mutants in isolated in-memory modules, never on disk.

A mutation is killed only by its matching test's tagged AssertionError. Missing
mutation targets, syntax/import/runtime errors, other assertions, and survivors
all make the check fail. All model tests run before and after the mutants.
"""

import io
import sys
import unittest
from pathlib import Path
from types import ModuleType

# Each substitution is unique, executable, and tied to a hand-derived fixture.
MUTATIONS = (
    {
        "name": "decide_from_cleanup_instead_of_peak",
        "old": "        decision_bytes = write_peak\n",
        "new": "        decision_bytes = after_cleanup\n",
        "test": "ProjectCapacityTests.test_peak_cannot_borrow_cleanup",
        "assertion": "PEAK_DECISION_MUST_USE_WRITE_PEAK",
    },
    {
        "name": "subtract_every_generation_reference",
        "old": "            if object_id not in seen_objects:\n",
        "new": "            if True:\n",
        "test": "ProjectCapacityTests.test_shared_raw_cleanup_once_across_rounds",
        "assertion": "SHARED_PHYSICAL_CLEANUP_ONCE",
    },
    {
        "name": "zero_balances_when_no_writes",
        "old": "        before_by_prefix = dict(current)\n",
        "new": "        before_by_prefix = dict(current) if writes else dict.fromkeys(current, 0)\n",
        "test": "ProjectCapacityTests.test_empty_cleanup_zero_writes_preserve_totals",
        "assertion": "EMPTY_WRITES_KEEP_BALANCE",
    },
    {
        "name": "equality_not_reached",
        "old": '                "reached": decision_bytes >= limit,\n',
        "new": '                "reached": decision_bytes > limit,\n',
        "test": "ProjectCapacityTests.test_equality_reached_not_exceeded",
        "assertion": "EQUALITY_IS_REACHED",
    },
)


class _RecordingResult(unittest.TextTestResult):
    """Keep exception objects so a mere nonzero exit cannot count as a kill."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure_records = []

    def addFailure(self, test, err):
        self.failure_records.append((test, err))
        super().addFailure(test, err)


def _run_suite(model_source, test_source, test_name=None):
    """Import tests against one ephemeral model and always restore imports."""
    model = ModuleType("budget_model")
    tests = ModuleType("_isolated_capacity_budget_tests")
    previous = sys.modules.get("budget_model")
    had_previous = "budget_model" in sys.modules
    try:
        # Trusted local artifact sources plus fixed mutations only.
        # Namespace isolation is not a sandbox for untrusted Python.
        exec(  # noqa: S102
            compile(model_source, "<isolated-budget-model>", "exec"), model.__dict__
        )
        sys.modules["budget_model"] = model
        exec(  # noqa: S102 - same trusted local source boundary as above
            compile(test_source, "<isolated-budget-tests>", "exec"), tests.__dict__
        )
        loader = unittest.TestLoader()
        suite = (loader.loadTestsFromName(test_name, tests) if test_name
                 else loader.loadTestsFromModule(tests))
        stream = io.StringIO()
        result = unittest.TextTestRunner(
            stream=stream, verbosity=2, resultclass=_RecordingResult
        ).run(suite)
        return result, stream.getvalue()
    finally:
        if had_previous:
            sys.modules["budget_model"] = previous
        else:
            sys.modules.pop("budget_model", None)


def _require_green(result, transcript, label):
    if result.testsRun == 0 or not result.wasSuccessful():
        raise RuntimeError(f"{label} is not green:\n{transcript}")
    return f"{label}: {result.testsRun} tests passed"


def check_mutations(model_source, test_source):
    """Return verification lines or raise RuntimeError for an invalid check."""
    result, transcript = _run_suite(model_source, test_source)
    lines = [_require_green(result, transcript, "BASELINE")]
    for mutation in MUTATIONS:
        count = model_source.count(mutation["old"])
        if count != 1:
            raise RuntimeError(
                f"INVALID {mutation['name']}: mutation target occurs {count} times, expected 1"
            )
        mutant = model_source.replace(mutation["old"], mutation["new"], 1)
        try:
            result, transcript = _run_suite(mutant, test_source, mutation["test"])
        except Exception as exc:
            raise RuntimeError(
                f"INVALID {mutation['name']}: execution error, not an assertion kill: {exc}"
            ) from exc
        if result.wasSuccessful():
            raise RuntimeError(f"SURVIVED {mutation['name']}: intended test passed")
        if result.testsRun != 1 or result.errors or len(result.failure_records) != 1:
            raise RuntimeError(f"INVALID {mutation['name']}: not one assertion failure:\n{transcript}")
        test, (error_type, error, tb) = result.failure_records[0]
        intended_method = mutation["test"].split(".")[-1]
        in_intended_test = False
        while tb is not None:
            if (tb.tb_frame.f_code.co_filename == "<isolated-budget-tests>"
                    and tb.tb_frame.f_code.co_name == intended_method):
                in_intended_test = True
            tb = tb.tb_next
        if (not issubclass(error_type, AssertionError)
                or mutation["assertion"] not in str(error)
                or not test.id().endswith(mutation["test"])
                or not in_intended_test):
            raise RuntimeError(f"INVALID {mutation['name']}: wrong assertion:\n{transcript}")
        lines.append(f"KILLED {mutation['name']}: AssertionError: {error}")
    result, transcript = _run_suite(model_source, test_source)
    lines.append(_require_green(result, transcript, "RESTORED BASELINE"))
    lines.append("4/4 behavior mutants killed by their intended assertion failures")
    return lines


def main():
    root = Path(__file__).resolve().parent
    model_path = root / "budget_model.py"
    original = model_path.read_bytes()
    test_source = (root / "test_budget_model.py").read_text(encoding="utf-8")
    try:
        lines = check_mutations(original.decode("utf-8"), test_source)
    # Any harness exception must fail the check, never count as a kill.
    except Exception as exc:  # noqa: BLE001
        print(f"MUTATION CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if model_path.read_bytes() != original:
            raise RuntimeError("real model changed during mutation checking")
    for line in lines:
        print(line)
    print("Real model source unchanged (byte-for-byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
