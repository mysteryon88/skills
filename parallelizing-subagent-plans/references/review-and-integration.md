# Review and Integration Contract

The parallel executor must preserve the source plan's testing, review, and verification gates. Parallel scheduling changes elapsed time, not the definition of done.

## Per-Task and per-lane gates

Each source Task remains a review boundary even when several Tasks share one lane.

1. The implementer uses TDD for behavior changes, runs focused checks, commits the Task, and records evidence.
2. One reviewer independent of the implementer checks specification, then code quality in the same dispatch and returns both verdicts. Preserve distinct reviewers when the source plan or project policy requires them. Specification failure blocks quality approval and completion.
3. Critical or Important findings enter a scoped fix loop. Minor findings are written to the run ledger for final triage.
4. Fix rounds 1-3 resume the original implementer. Rounds 4-5 prefer a fresh independent implementer with the required capability; when capacity is unavailable, use a fresh isolated context with the complete finding packet.
5. Every fix round ends with focused tests and a scoped re-review of the fix diff.
6. After five rounds, adjudicate each residual finding. A real load-bearing finding blocks the lane; it is never silently parked.

A lane becomes merge-eligible only after every Task in it passes its gate, the lane diff respects ownership, focused tests are fresh, all work is committed, and the worktree is clean.

Resume the same lane implementer after each Task gate, while unrelated lanes continue. For a singleton lane, its accepted Task review can also satisfy lane review only when the unchanged complete lane diff, ownership and integration readiness were explicitly reviewed and recorded. Keep a separate lane review for multiple Tasks, changed/missing scope, or a binding distinct-review requirement. The final integrated review remains mandatory.

## Worktree integration

Merge approved lane branches one at a time into the integration branch in dependency order. After each merge:

- run that lane's checks;
- run contract or interaction checks with already merged lanes;
- inspect the merge diff for lost or duplicated behavior;
- record the merge commit and evidence.

A textual conflict is resolved by one dedicated integrator with both lane briefs, both reports, frozen contracts, current integration constraints, and the conflict set. The integrator preserves both approved behaviors and adds a regression test when the conflict exposed an untested interaction.

A clean Git merge is not semantic proof. API producer/consumer pairs, UI/backend boundaries, generated artifacts, migrations, and shared state require explicit integrated checks.

## Whole-branch review

After all lanes and epilogue Tasks are integrated:

1. run the complete proportionate suite, type checks, lint, build, packaging, migration, security, and runtime checks named by the plan;
2. create a whole-diff package from frozen base to integration head;
3. dispatch an independent reviewer whose capabilities match the repository and risk surface, with the source spec, source plan, overlay, ledger, lane reports, contracts, and verification evidence;
4. send the complete final finding set to one integration fixer in one coherent wave;
5. run focused tests, the integrated suite, and one scoped re-review of the final fix diff.

There is one final fix wave. Residual contestable or non-load-bearing findings receive explicit rulings in the ledger. Residual load-bearing defects block completion and preserve all recovery resources.

## Delivery and cleanup

Reconcile a moved base, rerun affected checks, and verify the final tree directly. Never trust worker summaries as completion evidence.

Cleanup starts only after the final target branch contains every approved commit and passes fresh verification. Remove only worktrees, branches, manifests, briefs, reports, and review packages recorded as owned by this run. Dirty, unmerged, locked, foreign, or failed resources are preserved and reported. Never force-delete a branch or manually erase a worktree directory as routine cleanup.
