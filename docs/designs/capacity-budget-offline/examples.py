"""Print independently hand-checkable offline scenarios; no live inputs."""

import json

from budget_model import project_capacity


def scenarios():
    """Return inputs and projections, keeping reported baseline provenance clear."""
    small = {
        "current_prefix_bytes": {"raw": 90},
        "rounds": [{
            "writes_by_prefix": {"raw": 30},
            "cleanup": [{"object_id": "synthetic:retired-raw:v1", "prefix": "raw", "size_bytes": 40}],
        }],
        "thresholds": {"cap": 100},
    }
    bucket = {
        "current_prefix_bytes": {"reported_bucket": 8_800_774_448},
        "rounds": [
            {
                "writes_by_prefix": {"reported_bucket": 250_000_000},
                "cleanup": [{
                    "object_id": "synthetic:retired-object:v1",
                    "prefix": "reported_bucket", "size_bytes": 600_000_000,
                }],
            },
            {
                "writes_by_prefix": {"reported_bucket": 49_225_552},
                "cleanup": [
                    {"object_id": "synthetic:retired-object:v1",
                     "prefix": "reported_bucket", "size_bytes": 600_000_000},
                    {"object_id": "synthetic:retired-object:v1",
                     "prefix": "reported_bucket", "size_bytes": 600_000_000},
                ],
            },
        ],
    }
    return {
        "warning": "Offline scenarios only; no account-wide measurement or permission to write/delete.",
        "small_hand_calculation": {
            "input": small,
            "expected_totals": {"before": 90, "peak": 120, "after": 80},
            "projection": project_capacity(**small),
        },
        "reported_bucket_with_hypothetical_events": {
            "baseline_source": "https://github.com/zenithli/datumoj/issues/1#issuecomment-6782541584",
            "baseline_reported_at": "2026-11-11T08:30:00+09:00",
            "baseline_independently_remeasured": False,
            "events_are_hypothetical": True,
            "input": bucket,
            "expected_totals": {
                "round1_before": 8_800_774_448,
                "round1_peak": 9_050_774_448,
                "round1_after": 8_450_774_448,
                "round2_peak_and_after": 8_500_000_000,
                "scenario_high_water": 9_050_774_448,
            },
            "projection": project_capacity(**bucket),
        },
    }


if __name__ == "__main__":
    print(json.dumps(scenarios(), ensure_ascii=False, indent=2))
