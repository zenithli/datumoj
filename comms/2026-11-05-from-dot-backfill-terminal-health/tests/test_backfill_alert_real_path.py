"""Real-path backfill health regression contracts, with only external services simulated."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from datumoj.rikolto import cloud
from datumoj.rikolto.core.schedule import Scheduler, write_control
from datumoj.rikolto.testing.fakes import FakeChunkStore, FakeManifest, FakeRegistry
from datumoj.rikolto.testing.samples import make_chunk, make_document, make_snapshot, make_spec
from tests import test_cloud_run as cloud_tests
from tests import test_source_issues as issue_tests

world = cloud_tests.world
fake_gh = issue_tests.fake_gh


@pytest.fixture
def terminal_backfill_journey(world, fake_gh, tmp_path, httpserver):
    """Run five real cloud rounds and the real issue-sync script after each round."""
    world.clock[0] -= timedelta(days=2)
    world.overrides.pop("vectors")
    embedder = cloud_tests.FlakyEmbedder(100)
    world.overrides["embedder"] = embedder
    # Produce a real crawl issue while real parsed chunks accumulate embedding
    # failures. No source_health row, vector counter or ledger row is fabricated.
    httpserver.expect_request("/failure.txt").respond_with_data(b"synthetic error", status=503)
    failure_url = httpserver.url_for("/failure.txt")
    world.specs[0].scope["urls"].append(failure_url)
    evidence = []

    def step(name):
        result, root = cloud_tests.invoke(world, name)
        assert result["generation"] is not None, result
        sync = issue_tests.run_script(tmp_path, result["source_health"], result["generation"])
        assert sync.returncode == 0, sync.stdout + sync.stderr
        pending = json.loads((root / "vectors-state.json").read_text())["missing"]
        ledger = cloud_tests.rows(root)
        gh = json.loads(fake_gh.read_text())
        evidence.append({
            "round": name, "result": result, "pending": pending, "ledger": ledger,
            "gh": gh, "embedder_attempted": embedder.attempted,
        })
        (tmp_path / "backfill-real-path-evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        return result, pending, ledger, gh

    first, _, first_ledger, gh = step("first_due")
    assert first["due"] == 3
    first_health = next(row for row in first["source_health"] if row["source_id"] == "jp-cloud0")
    assert first_health["status"] == "failed" and first_health["consecutive_failures"] == 1
    assert gh["issues"] == []

    world.clock[0] += timedelta(hours=1)
    second, _, second_ledger, gh = step("second_due")
    second_health = next(row for row in second["source_health"] if row["source_id"] == "jp-cloud0")
    assert second_health["status"] == "failed" and second_health["consecutive_failures"] == 2
    assert len(gh["issues"]) == 1
    assert gh["issues"][0]["title"] == "[source-broken] jp-cloud0"
    assert not gh["issues"][0].get("closed")

    third, terminal, third_ledger, _ = step("non_due_terminal")
    assert third["due"] == 0 and third["sources"] == []
    assert third["exit_status"] == 1
    assert {item["failures"] for item in terminal.values()} == {3}
    assert third["vector_pending"] == 6
    assert {row["source_id"] for row in third["failed_sources"]} == {
        "jp-cloud0", "jp-cloud1", "jp-cloud2",
    }
    assert third_ledger == second_ledger
    attempts_at_terminal = embedder.attempted

    # Repair only crawl. _source/parse_pending must calculate the next health
    # naturally; the embedder still fails and terminal records are not reset.
    world.specs[0].scope["urls"].remove(failure_url)
    world.clock[0] += timedelta(hours=1)
    fourth, pending, fourth_ledger, _ = step("next_due_crawl_recovers")
    assert fourth["due"] == 2
    assert fourth["vector_pending"] == 6 and pending == terminal
    assert embedder.attempted == attempts_at_terminal
    final = [row for row in fourth_ledger if row["source_id"] == "jp-cloud0" and row["state"] == "final"]
    assert final[-1]["status"] == "completed" and final[-1]["failures"] == {}
    assert len(fourth_ledger) > len(second_ledger) > len(first_ledger)
    # Eliminate the actual fault through successful embedding of new document
    # versions. Do not edit vectors-state.json, clear ledger rows, or fake health.
    embedder.failures = 0
    httpserver.clear()
    for index in range(3):
        httpserver.expect_request(f"/source{index}.txt").respond_with_data(
            b"Recovered synthetic document version\n\nSuccessfully embedded paragraph", content_type="text/plain",
        )
    world.clock[0] += timedelta(days=1)
    fifth, recovered, _, _ = step("real_vectors_recover")
    assert fifth["due"] == 3 and fifth["vector_pending"] == 0 and recovered == {}
    assert embedder.attempted > attempts_at_terminal
    return evidence


def test_contract_non_due_terminal_failure_is_visible(terminal_backfill_journey):
    """Terminal failures must remain visible without inventing crawl runs."""
    _, second, third, _, _ = terminal_backfill_journey
    health = {row["source_id"]: row for row in third["result"]["source_health"]}
    assert {"jp-cloud0", "jp-cloud1", "jp-cloud2"} <= health.keys()
    assert all(health[source]["status"] == "failed" for source in health)
    assert third["ledger"] == second["ledger"]
    assert health["jp-cloud1"]["consecutive_failures"] == 0
    assert health["jp-cloud2"]["consecutive_failures"] == 0
    assert len(third["gh"]["issues"]) == 1  # Existing crawl threshold is not relaxed.


def test_contract_terminal_vectors_do_not_count_as_recovered(terminal_backfill_journey):
    """Crawl recovery alone must not close an unresolved source issue."""
    fourth = terminal_backfill_journey[3]
    assert {row["failures"] for row in fourth["pending"].values()} == {3}
    assert not fourth["gh"]["issues"][0].get("closed", False)
    assert fourth["result"]["exit_status"] == 0 and fourth["result"]["failed_sources"] == []
    row = next(row for row in fourth["result"]["source_health"] if row["source_id"] == "jp-cloud0")
    assert row["status"] == "failed" and row["phase"] == "embedding"
    assert row["categories"] == {"embedding_failed": 1}
    assert row["consecutive_failures"] == 0 and row["first_failure_at"] is None


def test_contract_actual_vector_recovery_allows_issue_closure(terminal_backfill_journey):
    """The issue closes only after real vector writes remove terminal pending records."""
    fourth, fifth = terminal_backfill_journey[3:]
    assert not fourth["gh"]["issues"][0].get("closed", False)
    assert fifth["pending"] == {} and fifth["result"]["exit_status"] == 0
    assert all(row["status"] == "ok" for row in fifth["result"]["source_health"])
    issue = fifth["gh"]["issues"][0]
    assert issue["closed"] and issue["comments"][-1] == f"已恢复（第 {fifth['result']['generation']} 代）"


def health_pipeline(specs, missing, documents, snapshots=()):
    """Construct protocol fakes while keeping vector-state loading and attribution real."""
    manifest = FakeManifest()
    for snapshot in snapshots:
        manifest.record_snapshot(snapshot)
    chunks = FakeChunkStore()
    for key, sha in documents.items():
        chunks.put_document(make_document(key, sha), [make_chunk(key, sha, "section=1", "synthetic")])
    return SimpleNamespace(
        manifest=manifest, registry=FakeRegistry(specs), chunks=chunks,
        vector_state={"missing": missing, "last_error": None}, vector_state_path=None,
        vector_state_dirty=False, _vector_pruned_for=None,
    )


@pytest.mark.parametrize("status,phase,expected_status,expected_phase", [
    ("missing", "schedule", "missing", "schedule"),
    ("failed", "crawl", "failed", "crawl"),
    ("ok", None, "failed", "embedding"),
])
def test_terminal_overlay_preserves_missing_and_existing_failure_phase(
    tmp_path, status, phase, expected_status, expected_phase,
):
    """Terminal projection preserves missing eligibility and never doubles event counts."""
    spec = make_spec("jp-health")
    snapshot = make_snapshot(spec.id, snapshot_id="synthetic-known")
    missing = {
        "jp-health:known": {"snapshot_id": snapshot.snapshot_id, "failures": 3, "chunks": 1},
        "jp-health:fallback": {"snapshot_id": "missing-snapshot", "failures": 3, "chunks": 1},
        "jp-health:deferred": {"snapshot_id": snapshot.snapshot_id, "failures": 2, "chunks": 1},
    }
    pipeline = health_pipeline([spec], missing, dict.fromkeys(missing, snapshot.sha256), [snapshot])
    original = {"source_id": spec.id, "status": status, "phase": phase,
                "categories": {"embedding_failed": 1}, "consecutive_failures": 0, "first_failure_at": None}
    write_control(tmp_path, {"enabled": True, "sources": {spec.id: {"enabled": True}}})
    scheduler = Scheduler(tmp_path, [spec], lambda _: None)
    result = cloud._source_health(scheduler, [original], pipeline=pipeline)
    assert len(result) == 1
    assert result[0]["status"] == expected_status and result[0]["phase"] == expected_phase
    assert result[0]["categories"] == {"embedding_failed": 2}
    assert original["categories"] == {"embedding_failed": 1}
    assert result[0]["consecutive_failures"] == 0 and result[0]["first_failure_at"] is None
    assert not (tmp_path / "runs.jsonl").exists()


@pytest.mark.parametrize("global_enabled,source_enabled,embed", [
    (False, True, True), (True, False, True), (True, True, False),
])
def test_terminal_overlay_respects_runtime_and_embedding_switches(
    tmp_path, global_enabled, source_enabled, embed,
):
    """Global, per-source and embedding switches cannot create fresh terminal alerts."""
    spec = make_spec("jp-disabled", scope={"embed": embed})
    snapshot = make_snapshot(spec.id)
    key = "jp-disabled:doc"
    pipeline = health_pipeline([spec], {key: {"failures": 3, "chunks": 1}}, {key: snapshot.sha256})
    write_control(tmp_path, {"enabled": global_enabled, "sources": {spec.id: {"enabled": source_enabled}}})
    scheduler = Scheduler(tmp_path, [spec], lambda _: None)
    assert cloud._source_health(scheduler, [], pipeline=pipeline) == []


def test_terminal_overlay_ignores_stale_unknown_deleted_and_cross_source_documents(tmp_path):
    """Shared content hashes cannot transfer another source's terminal failure."""
    spec, other = make_spec("jp-health"), make_spec("jp-other")
    snapshot = make_snapshot(spec.id, snapshot_id="healthy-version")
    shared = make_snapshot(other.id, snapshot_id="other-source-same-content")
    assert shared.sha256 == snapshot.sha256
    missing = {
        "jp-health:deleted": {"snapshot_id": snapshot.snapshot_id, "failures": 3, "chunks": 1},
        "jp-health:stale": {"snapshot_id": snapshot.snapshot_id, "failures": 3, "chunks": 1},
        "jp-health:cross-source": {"snapshot_id": shared.snapshot_id, "failures": 3, "chunks": 1},
        "jp-unknown:doc": {"snapshot_id": "missing-snapshot", "failures": 3, "chunks": 1},
        "jp-other:valid": {"snapshot_id": shared.snapshot_id, "failures": 3, "chunks": 1},
    }
    documents = {"jp-health:stale": "ab" * 32, "jp-health:cross-source": snapshot.sha256,
                 "jp-unknown:doc": snapshot.sha256, "jp-other:valid": shared.sha256}
    pipeline = health_pipeline([spec, other], missing, documents, [snapshot, shared])
    write_control(tmp_path, {"enabled": True, "sources": {
        spec.id: {"enabled": True}, other.id: {"enabled": True},
    }})
    scheduler = Scheduler(tmp_path, [spec, other], lambda _: None)
    health = cloud._source_health(scheduler, [], pipeline=pipeline)
    assert len(health) == 1 and health[0]["source_id"] == other.id
    assert health[0]["categories"] == {"embedding_failed": 1}
