#!/usr/bin/env python3
"""Pinned-source, standard-library-only function-level backfill alert reproduction.

Only selected cloud.py and source_issues.py functions execute. Repository imports,
vector operations and GitHub operations never execute. See README.md for limits.
"""
import argparse
import ast
import hashlib
import json
import re
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

PINS = {
    "bdf76e7": {
        "commit": "bdf76e79d7bd4faf8eb9b83712fa53a801580762",
        "blobs": {
            "src/datumoj/rikolto/cloud.py": "ca67c7a45832e4674b2a5dbbe47de2b5c51da2d8",
            "scripts/source_issues.py": "9b1da5aaeb4126c331dfce9bf400751a0cd85ec8",
            "src/datumoj/rikolto/pipeline.py": "196d8aaecbb9cac11df82fd5dae43ab1b987b036",
        },
    },
    "2f03e89": {
        "commit": "2f03e8949f219bcbc9bb637793d68fee04872f78",
        "blobs": {
            "src/datumoj/rikolto/cloud.py": "94464407b24c75dacefc54bcf13c4137ba62b104",
            "scripts/source_issues.py": "9b1da5aaeb4126c331dfce9bf400751a0cd85ec8",
            "src/datumoj/rikolto/pipeline.py": "65bcef3ac26a5854457c6dbb88a2dcbe10ec5423",
        },
    },
}


def read_pinned_sources(repo, baseline):
    sources = {}
    for relative, expected in PINS[baseline]["blobs"].items():
        data = (repo / relative).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise ValueError(f"Source blob mismatch: {relative}: expected {expected}, got {actual}")
        sources[relative] = data.decode("utf-8")
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--baseline", choices=PINS, default="2f03e89")
    args = parser.parse_args()
    try:
        source = read_pinned_sources(args.repo, args.baseline)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Verified 3 Git source blobs from {PINS[args.baseline]['commit']}.", file=sys.stderr)

    pipeline_ast = ast.parse(source["src/datumoj/rikolto/pipeline.py"])
    limits = [
        ast.literal_eval(node.value) for node in pipeline_ast.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VECTOR_FAILURE_LIMIT"
                for target in node.targets)
    ]
    assert limits == [3], limits
    ns = dict(
        datetime=datetime, re=re, json=json, time=time,
        replace=lambda p, **kw: p, local_write=lambda _: nullcontext(),
        ParseSummary=lambda: None, _progress=lambda *a: None,
        VECTOR_FAILURE_LIMIT=limits[0], _BACKFILL_BATCH=100, _PIPELINE_GRACE_SECONDS=30,
    )

    def take(text, names):
        body = [node for node in ast.parse(text).body
                if isinstance(node, ast.FunctionDef) and node.name in names]
        assert {node.name for node in body} == names
        exec(compile(ast.Module(body=body, type_ignores=[]),
                     "<selected-original-functions>", "exec"), ns)

    take(source["src/datumoj/rikolto/cloud.py"], {
        "_backfill", "_source_health", "_final_runs", "_failure_streak",
        "_failure_counts", "_embedding_counts", "_health_failure",
    })
    take(source["scripts/source_issues.py"], {"issue_text", "sync_issues"})
    ns["LABEL"] = "source-broken"
    calls = []

    class FakeGitHub:
        def __init__(self):
            self.failures = 0

        def call(self, *args, read_json=False):
            calls.append(args)
            if args[:2] == ("issue", "list"):
                return [{"number": 99, "title": "[source-broken] jp-test"}]
            if args[:2] == ("label", "list"):
                return [{"name": "source-broken"}]
            return True

    ns["GitHub"] = FakeGitHub
    success = {
        "source_id": "jp-test", "run_id": "ok1", "state": "final",
        "started_at": "2026-11-05T00:00:00+00:00",
        "ended_at": "2026-11-05T00:01:00+00:00",
        "status": "completed", "exit_status": 0, "failures": {},
    }
    scheduler = NS(_read_history=lambda: ([success], None))
    state = {"missing": {
        "jp-test:doc": {"snapshot_id": "snap", "chunks": 1, "failures": 2},
    }}
    pipeline = NS(vectors=object(), manifest=NS(get_snapshot=lambda _: NS(source_id="jp-test")))
    deps = NS(pipeline_deps=pipeline, data_dir="unused",
              registry=NS(all=lambda: [NS(id="jp-test")]))
    ns["_load_vector_state"] = lambda _: state
    ns["_start_vectors"] = lambda p: setattr(p, "_vector_remaining", p.vector_limit)

    def retry(p, *a, **kw):
        state["missing"]["jp-test:doc"]["failures"] += 1
        p._vector_remaining -= 1
        return 0

    ns["_retry_vectors"] = retry

    def healthy():
        return {
            "source_id": "jp-test", "status": "ok", "phase": None, "categories": {},
            "consecutive_failures": 0, "first_failure_at": None,
        }

    outputs = []

    def run(label, current, initial=2, health_overlay=False):
        calls.clear()
        state["missing"]["jp-test:doc"]["failures"] = initial
        result = {
            "generation": 2, "source_health": current, "failed_sources": [],
            "embedding_deferred": 0, "backfill_embedded": 0,
        }
        before = ns["_failure_counts"](pipeline)
        ns["_backfill"](deps, 10, time.monotonic(), 10, lambda: None, result, before)
        if health_overlay:
            h = healthy()
            ns["_health_failure"](h, "embedding", "embedding_failed", 1)
            h["consecutive_failures"] = 99
            result["source_health"].append(h)
        result["source_health"] = ns["_source_health"](scheduler, result["source_health"])
        ns["sync_issues"](result)
        output = {
            "scenario": label, "failed_sources": result["failed_sources"],
            "source_health": result["source_health"], "gh_calls": list(calls),
            "ledger_rows": len(scheduler._read_history()[0]),
        }
        outputs.append(output)
        print(json.dumps(output))

    run("non_due_threshold_crossing", [])
    run("health_only_overlay_streak_overwritten", [], health_overlay=True)
    run("same_round_existing_ok_conditional", [healthy()])
    run("next_due_still_terminal_failure", [healthy()], initial=3)

    assert outputs[0]["failed_sources"] and outputs[0]["source_health"] == []
    assert outputs[0]["gh_calls"] == []
    assert outputs[1]["source_health"][0]["status"] == "failed"
    assert outputs[1]["source_health"][0]["consecutive_failures"] == 0
    assert outputs[1]["gh_calls"] == []
    assert outputs[2]["failed_sources"]
    assert outputs[2]["gh_calls"][-1] == ("issue", "close", "99")
    assert outputs[3]["failed_sources"] == []
    assert outputs[3]["gh_calls"][-1] == ("issue", "close", "99")
    assert all(row["ledger_rows"] == 1 for row in outputs)
    print("PASS: four original function-level scenarios reproduced.", file=sys.stderr)


if __name__ == "__main__":
    main()
