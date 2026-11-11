"""Offline, conditional capacity projection over caller-supplied prefix totals.

This module is an executable design artifact, not a storage adapter or an
operational gate. It does no I/O and cannot establish object existence,
cleanup eligibility, inventory disjointness/completeness, or historical usage.
"""

from collections.abc import Mapping, Sequence

_DEFAULT_THRESHOLDS = {
    "warning_7gb": 7_000_000_000,
    "freeze_8_5gb": 8_500_000_000,
    "stop_9gb": 9_000_000_000,
}


def _name(value, path):
    if not isinstance(value, str):
        raise TypeError(f"{path} must be a string")
    if not value or value != value.strip() or not value.isprintable():
        raise ValueError(f"{path} must be nonempty, trimmed, and printable")
    return value


def _bytes(value, path, *, positive=False):
    # bool is an int subclass; strict integers avoid that silent coercion.
    if type(value) is not int:
        raise TypeError(f"{path} must be an integer, not bool or float")
    if value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{path} must be {qualifier}")
    return value


def _mapping(value, path):
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")
    return value


def _sequence(value, path):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{path} must be a non-string sequence")
    return value


def _fields(value, expected, path):
    _mapping(value, path)
    if set(value) != set(expected):
        raise ValueError(f"{path} fields must be exactly {', '.join(expected)}")


def _byte_mapping(value, path, *, positive=False):
    _mapping(value, path)
    return {
        _name(key, f"{path} key"): _bytes(amount, f"{path}[{key!r}]", positive=positive)
        for key, amount in value.items()
    }


def project_capacity(current_prefix_bytes, rounds, thresholds=None):
    """Return a JSON-serializable, integer-only conditional capacity projection.

    ``current_prefix_bytes`` maps declared, mutually exclusive prefix/category
    labels to non-negative integer bytes. The caller must provide a complete,
    disjoint inventory for its claimed scope. Every prefix used in a round must
    be declared here, including initially empty categories with zero bytes.

    ``rounds`` is an ordered sequence of mappings with exactly two fields:
    ``writes_by_prefix`` maps declared prefixes to expected NEW physical-object
    bytes before cleanup (not logical size or net growth); ``cleanup`` is a
    sequence of mappings with exactly ``object_id``, ``prefix``, ``size_bytes``.
    Cleanup objects are caller-supplied hypothetical eligible objects. Aggregate
    totals cannot verify either existence or eligibility. After-write prefix
    bytes are the available balance for this hypothetical cleanup step.

    IDs are opaque, caller-supplied, scope-qualified immutable physical-object
    identities, not generation references or content hashes. A repeated ID with
    identical prefix/size frees bytes only once across all rounds. Conflicting
    metadata fails. Recreation requires a new incarnation ID; aggregated writes
    never reset an already-cleaned identity.

    ``thresholds=None`` selects decimal-byte 7GB/8.5GB/9GB reporting lines. An
    explicit mapping replaces them; an empty mapping disables threshold reports.
    Thresholds are positive integers and never operational permission. Each
    round's reached/exceeded reports use only its after-write peak, before any
    cleanup. The projected high-water includes the initial total and every peak,
    and is not an observed historical high-water mark.

    Names are nonempty, trimmed, printable strings. Values must be builtin int
    (never bool/float); bytes are non-negative and thresholds are positive.
    Type errors raise TypeError; invalid values/fields, undeclared prefixes,
    identity conflicts, and per-prefix cleanup overdrafts raise ValueError.
    No input is mutated and no output balance aliases an input or other step.
    """
    current = _byte_mapping(current_prefix_bytes, "current_prefix_bytes")
    _sequence(rounds, "rounds")
    limits = _byte_mapping(
        _DEFAULT_THRESHOLDS if thresholds is None else thresholds,
        "thresholds",
        positive=True,
    )
    initial_total = sum(current.values())
    high_water = initial_total
    seen_objects = {}
    projected_rounds = []

    for index, round_plan in enumerate(rounds, start=1):
        path = f"rounds[{index - 1}]"
        _fields(round_plan, ("writes_by_prefix", "cleanup"), path)
        writes = _byte_mapping(round_plan["writes_by_prefix"], f"{path}.writes_by_prefix")
        for prefix in writes:
            if prefix not in current:
                raise ValueError(f"{path}.writes_by_prefix: undeclared prefix {prefix!r}")
        cleanup = _sequence(round_plan["cleanup"], f"{path}.cleanup")

        before_by_prefix = dict(current)
        before_total = sum(before_by_prefix.values())
        expected_write_bytes = sum(writes.values())
        after_write_by_prefix = {
            prefix: amount + writes.get(prefix, 0)
            for prefix, amount in before_by_prefix.items()
        }
        write_peak = sum(after_write_by_prefix.values())
        cleanup_by_prefix = dict.fromkeys(current, 0)

        for cleanup_index, item in enumerate(cleanup):
            item_path = f"{path}.cleanup[{cleanup_index}]"
            _fields(item, ("object_id", "prefix", "size_bytes"), item_path)
            object_id = _name(item["object_id"], f"{item_path}.object_id")
            prefix = _name(item["prefix"], f"{item_path}.prefix")
            size = _bytes(item["size_bytes"], f"{item_path}.size_bytes")
            if prefix not in current:
                raise ValueError(f"{item_path}: undeclared prefix {prefix!r}")
            metadata = (prefix, size)
            if object_id in seen_objects and seen_objects[object_id] != metadata:
                raise ValueError(f"{item_path}: conflicting metadata for {object_id!r}")
            if object_id not in seen_objects:
                cleanup_by_prefix[prefix] += size
                seen_objects[object_id] = metadata

        for prefix, cleanup_bytes in cleanup_by_prefix.items():
            if cleanup_bytes > after_write_by_prefix[prefix]:
                raise ValueError(f"{path}: cleanup exceeds available bytes in prefix {prefix!r}")
        unique_cleanup_bytes = sum(cleanup_by_prefix.values())
        after_cleanup_by_prefix = {
            prefix: amount - cleanup_by_prefix[prefix]
            for prefix, amount in after_write_by_prefix.items()
        }
        after_cleanup = sum(after_cleanup_by_prefix.values())
        decision_bytes = write_peak
        reports = {
            name: {
                "threshold_bytes": limit,
                "before_headroom_bytes": limit - before_total,
                "peak_headroom_bytes": limit - write_peak,
                "after_cleanup_headroom_bytes": limit - after_cleanup,
                "reached": decision_bytes >= limit,
                "exceeded": decision_bytes > limit,
            }
            for name, limit in limits.items()
        }
        projected_rounds.append({
            "round_index": index,
            "before_write_by_prefix": before_by_prefix,
            "before_write_bytes": before_total,
            "expected_writes_by_prefix": dict(writes),
            "expected_write_bytes": expected_write_bytes,
            "after_write_by_prefix": after_write_by_prefix,
            "write_peak_bytes": write_peak,
            "unique_cleanup_by_prefix": cleanup_by_prefix,
            "unique_cleanup_bytes": unique_cleanup_bytes,
            "after_cleanup_by_prefix": after_cleanup_by_prefix,
            "after_cleanup_bytes": after_cleanup,
            "thresholds": reports,
        })
        high_water = max(high_water, write_peak)
        current = dict(after_cleanup_by_prefix)

    return {
        "scope": {
            "kind": "supplied_prefixes_only",
            "prefixes": list(current),
            "inventory_assumption": "complete_disjoint_inventory_for_supplied_scope",
            "account_wide_completeness_verified": False,
            "physical_object_existence_verified": False,
            "cleanup_eligibility_verified": False,
            "historical_observed_high_water_verified": False,
        },
        "cleanup_assumption": "caller_supplied_hypothetical_eligible_physical_objects",
        "identity_assumption": "caller_supplied_scope_qualified_immutable_physical_object_ids",
        "thresholds_are_operational_permission": False,
        "thresholds": dict(limits),
        "initial": {
            "by_prefix": dict(current_prefix_bytes),
            "total_bytes": initial_total,
            "headroom_bytes": {name: limit - initial_total for name, limit in limits.items()},
        },
        "rounds": projected_rounds,
        "projected_high_water_bytes": high_water,
        "final_by_prefix": dict(current),
        "final_bytes": sum(current.values()),
    }
