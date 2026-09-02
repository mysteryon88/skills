# Review and Critique Modes

## Quick prompt review

For `REVIEW_PROMPT`, default to a quick review: give the verdict first, then the smallest material findings that would change execution quality. Check goal preservation, instruction hierarchy, untrusted input, authority and side effects, target-runtime compatibility, observable acceptance and output shape, repetition, and false-completion paths. Do not rewrite the prompt unless separately requested. Use a deeper audit only when the user asks for it or the prompt controls high-risk production actions.

## Review integrity

For `REVIEW`, establish the intended contract, current behavior, tests, user-visible impact, and confidence. Map findings to evidence and consequence. File inventory, documentation restatement, style-only commentary, unit success presented as live proof, and silent narrowing to a diff or starting files do not count.

Preserve tracked project files, project data, dependencies, and external state. Inspect test configuration, fixtures, markers, and scripts before checks with network, service, credential, database, filesystem, or live effects. Redirect supported ephemeral output to a temporary directory or disable caches, compare `git status --short` before and after, preserve pre-existing changes, and report artifacts left behind. `FILES_ALLOWED` does not turn review into change.

## Critique integrity

For `CRITIQUE`, put the verdict first, challenge assumptions, and rank only material flaws. Each criticism needs evidence, impact, confidence, the assumption challenged, and a better alternative. Inspect hidden complexity, transition and ownership cost, compatibility, recovery, observability, and operational burden.

Preserve what survives scrutiny and give focused falsification checks. Omit unsupported flaws or label them unknown. Personal attacks, fabricated bugs, severity inflation, vague dislike, rewrite-everything demands, and clever phrasing without consequence do not count. `DIRECT` may be blunt; `ROAST` may be witty about the artifact. Humor never replaces evidence or targets people, motives, or competence.

## Skeptic stance for ideas and proposals

Use `CRITIQUE + SKEPTIC` to reduce commitment risk, not to perform reflexive rejection.

1. State the decision being tested and steelman the strongest credible version of the idea before criticizing it.
2. Extract the load-bearing assumptions that must be true for the idea to work. Treat supplied claims as hypotheses until evidence supports them.
3. Seek disconfirming evidence and strong counterexamples. Lack of evidence is an unknown, not proof that the idea fails.
4. Test only dimensions relevant to the decision: problem urgency, adoption and distribution, incentives, economics, technical feasibility and dependencies, operations, differentiation and defensibility, timing, and legal, safety, or regulatory constraints when applicable.
5. Classify each material issue as `FATAL`, `REPAIRABLE`, or `UNKNOWN`. Give evidence or source class, impact, confidence, and the assumption challenged.
6. Define observable kill criteria and the cheapest falsification test for each load-bearing assumption. Prefer tests that reduce the largest uncertainty before expensive implementation.
7. Preserve what survives scrutiny and propose the smallest stronger alternative, pivot, or narrower experiment.

Return one evidence-tied verdict:

Choose the first matching verdict in this order: `REJECT`, `WEAK`, `CONDITIONAL`, `PROMISING`.

- `REJECT`: a supported fatal flaw defeats the current form;
- `WEAK`: no fatal flaw is supported, but major repair is needed before testing or commitment;
- `CONDITIONAL`: no major repair is needed, but named load-bearing assumptions must pass before further commitment;
- `PROMISING`: no fatal flaw or major repair is supported, and no unresolved assumption blocks the next bounded investment.

Cynicism theater, generic risk lists, invented market facts, false precision, personal attacks, and treating uncertainty as failure do not count. A skeptic who only says no has not completed the task.

## Operational definitions and completion integrity

Define a load-bearing term only when interpretations change scope, behavior, severity, or acceptance. Derive it from current contracts, code, tests, and user decisions; report contradictions.

For a broad review, add an observable completion predicate, task-specific **Non-counting outcomes**, and adversarial failure modes. Discover the executable surface from entry points, dependency wiring, background tasks, migrations, and callers. Inspect blocking I/O, transactions and compensation, concurrency, adapters, error propagation, and duplicated active implementations only when connected to an in-scope behavior.

Use repository-defined severity. Otherwise:

- `P0`: credible compromise, data loss, destructive cross-tenant/fleet effect, or mass outage;
- `P1`: a primary declared user or operational scenario is broken or unsafe;
- `P2`: partial failure, state divergence, serious reliability/operability risk, or material missing verification;
- `P3`: non-blocking documentation, test-depth, or supportability improvement.

For readiness, require one evidence-tied verdict:

- `READY`: every required outcome is supported and no blocking gap remains;
- `PARTIALLY READY`: core behavior is supported but a material scenario or verification layer is incomplete;
- `NOT READY`: a primary scenario is broken/unsafe or required evidence contradicts readiness.
