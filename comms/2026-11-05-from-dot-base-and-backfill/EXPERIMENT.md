# Backfill source-health alert reproduction

Pinned commit: bdf76e79d7bd4faf8eb9b83712fa53a801580762

Run against a checkout (no repository writes):

    python3 reproduce_backfill_alert_gap.py --repo /path/to/datumoj

The CLI verifies exact Git blob SHA-1 identities for cloud.py, source_issues.py, and pipeline.py before extracting functions. It requires only Python standard library. It never imports datumoj, runs gh, contacts services, crawls data, changes a ledger, or writes to the supplied repository. stdout is four JSON Lines; stderr reports blob verification and assertions. results.jsonl is the captured rerun. Verification exited 0; the three exact source blobs matched the pinned commit.

## Results

1. non_due_threshold_crossing: a synthetic vector failure crosses 2 -> 3. failed_sources records embedding_failed, source_health is empty, and sync_issues makes no GitHub calls.
2. health_only_overlay_streak_overwritten: a health-only overlay records failed/embedding_failed. The real _source_health recalculates its count from the successful synthetic ledger as 0, even overwriting a sentinel count of 99. Default threshold 2 filters it out.
3. same_round_existing_ok_conditional: when given an existing healthy row and a later backfill threshold crossing, the healthy row survives and real sync_issues calls the fake issue comment and close. Full real-world same-round reachability was NOT established.
4. next_due_still_terminal_failure: with pending vector failure count already 3, real _backfill skips retry and emits no new failed_sources. A supplied healthy source row makes sync_issues close the fake issue. Current pipeline.py independently skips terminal retry entries (lines 284-305), and cloud.py _embedding_counts only records newly crossed limits (lines 310-321). The experiment does NOT execute the full next-due crawl/parse path; the healthy row is synthetic.

## Boundaries

- This is a focused function-level reproduction, not an application integration test or production observation.
- Source files are pinned and AST-extracted; all vector storage, registry, source snapshots, time budget plumbing, and GitHub behavior are synthetic.
- _source_health is invoked without generation, so the cloud_run_missing branch is not exercised.
- The health-only overlay is an in-memory diagnostic, not a repository patch. The sentinel 99 demonstrates the final count is overwritten from the ledger.
- _source and _round are not executed. Their ledger behavior was inspected separately in current cloud.py (source final record lines 213-224; due loop lines 539-599).
- The fourth scenario requires no genuine vector recovery/reset and a subsequent healthy source result. New versions or explicit failure resets could change that premise.
- The fixed fake issue and timestamps are test data. No actual issue was read or changed by this script.
- No production fix is included.

Sources:
https://github.com/gorou5/datumoj/pull/88#discussion_r4476320145
https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/src/datumoj/rikolto/cloud.py#L243-L378
https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/scripts/source_issues.py#L68-L98
https://github.com/gorou5/datumoj/blob/bdf76e79d7bd4faf8eb9b83712fa53a801580762/src/datumoj/rikolto/pipeline.py#L284-L305

Script SHA-256: 516275644267c6a5eee664431a7de278490002a73803604853fade1d9ec590d1
