# Long-Running Controls

Use these controls only when cost, duration, ambiguity, coordination, or failure impact justifies them.

Activate `GOAL_DRIVEN`, `EVAL_LOOP`, or both only for a durable goal or repeated scored improvement. Goal state, background execution, Pro mode, persisted reasoning, and runtime budgets are target-runtime capabilities or settings; prompt text must not claim to enable them.

## Durable goals

Use `GOAL_DRIVEN` for one objective that is larger than a normal turn but smaller than an open-ended backlog. Render the target runtime's native shape: for Codex Goal mode, start with `/goal <objective>`; for a goal tool, explicitly request goal creation. Do not merely say that the executor is already in goal mode.

For Codex Goal mode, the copy-ready artifact is invalid unless its first non-empty line is the literal `/goal <objective>` command. Mentioning `/goal` later, burying it in an explanation, or claiming that prompt text enables Goal mode does not satisfy this gate. If the target runtime cannot create a durable goal, return the capability gap instead of simulating persistence.

The goal must state the outcome, in-scope and excluded work, evidence that proves completion, checkpoint or progress-log expectations, and the exact success, decision, authority, and hard-blocker stopping conditions. Goal persistence never expands write authority.

## Eval-driven improvement

Use `EVAL_LOOP` only when progress can be compared repeatedly through a stable command, metric, rubric, or inspectable artifact. Establish the baseline before edits, identify the largest evidenced failure, make one focused change, rerun the same evaluation, compare with the best result, preserve or restore the best artifact, and record the result and next hypothesis.

Stop when all declared thresholds and artifact checks pass, or when further progress requires missing authority, unavailable evidence, or a product decision. A failed hypothesis is not completion; an unmeasurable request is not an eval loop. Combine `GOAL_DRIVEN + EVAL_LOOP` by using the goal's completion predicate as the loop's stopping rule rather than duplicating both contracts.

## Completion integrity

State one artifact-level completion predicate, task-specific near misses that do not count, concrete failure modes, required artifacts, and a return gate. Pair persistence with evidence-producing verification. An external budget may end work early only with the strongest verified partial artifact and exact remaining gap. Prompt wording never enforces a runtime budget, permission, or effort floor.

## Task sizing

Each unit needs one observable deliverable, explicit inputs/outputs, clear file or contract ownership, a focused verification path, and known dependencies.

Keep units dependency-aware and serialize migrations, shared schemas, lockfiles, generated output, common interfaces, and unresolved root-cause hypotheses. When the selected execution strategy is `PARALLEL_SUBAGENTS`, apply `parallel-subagent-mode.md`; worker claims never replace fresh integrated verification.

## Return integrity

Return only when the completion predicate is supported by required artifacts and adversarial checks. Otherwise return an explicitly incomplete verified partial result or exact `BLOCKED` condition; never substitute a status-only update.
