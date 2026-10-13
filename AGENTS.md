# Development instructions

## Scope and priorities
This repository contains a Python Discord bot, optional Hindsight memory, a subscription answer extension, and privacy-preserving observability.
Read README.md, CONSTRAINTS.md, and the files involved in the requested change before editing. Preserve existing provider behavior and optional configuration defaults.
Prefer the smallest change that solves the observed problem. Do not install entire agent catalogs, new orchestration frameworks, or model dependencies solely to obtain development guidance.

## Diagnose before changing
1. Identify the failing boundary: Discord delivery, memory service, answer provider, search response contract, or observability.
2. Record the observed symptom and a reproducible case. Distinguish missing evidence from an empty result.
3. Trace the actual request path and inspect the relevant existing tests.
4. Fix the demonstrated cause; use a regression test for behavior changes.
5. Reproduce the original case and run the relevant checks before reporting success.
For deployment incidents, code, CI, deployment status, service health, and end-to-end behavior are separate evidence. A successful CI run does not prove production recovery.

## Coordinated development
Assign one task owner to keep the scope, implementation, verification, and final report consistent.
Share findings with source paths, the inspected revision, and observed evidence before repeating research.
Parallelize only independent work with explicit ownership boundaries. Never edit the same file concurrently; hand off overlapping work serially.
The implementer runs the applicable checks and reports the exact revision or candidate, commands, results, and unverified items.
After implementation, perform a separate acceptance pass against each requested requirement and the final diff; passing tests alone does not establish task completion.
A separate acceptance pass is a distinct review step, not a requirement to call another model or launch another agent.
Request specialist review only for high-risk changes or unresolved uncertainty, using the relevant checklist below.
These are development instructions, not implemented runtime locking or an automatic reviewer. They do not add multi-model calls to ordinary Discord answers, pin models, or introduce configuration keys.

## Workflow proportional to the task
Use the task owner as the default researcher, planner, and implementer; these are responsibilities, not mandatory separate agents.
For a small documentation or local fix, use a short scope statement, the change, and a distinct final acceptance pass.
For runtime behavior changes, record the observed case, affected boundary, requirement-to-evidence mapping, relevant tests, and rollback approach before editing.
For access control, credentials, user data, provider routing, or deployment changes, add the relevant focused review and verify the affected boundary.
When scouting a backlog, propose at most three useful independent jobs, ordered by impact and urgency; do not invent jobs to fill a quota or expand beyond the authorized task.
Before editing, state the goal, affected paths, acceptance criteria, and known uncertainty. Findings must identify the inspected revision and file location.
Review findings should state the observed problem, impact, and evidence. Recheck affected requirements after fixes; two inconclusive acceptance passes trigger diagnosis or a scoped blocker report, not automatic acceptance.

## Failure handling and authorization
After the same failure repeats twice without new evidence, stop repeating the same command and classify the cause: code, test, environment, authentication, permissions, external service, or missing information.
Resolve an evidenced cause within scope. A permission or authentication failure is not a reason to switch models, bypass controls, or use a new paid service.
Seek deeper reasoning or specialist review for unresolved technical ambiguity or high-risk decisions, not merely because a retry counter reached three.
Keep existing worker limits intact; this guidance does not change the autopatcher's two-call limit or implement new retry controls.
Continue reversible work already authorized by the user without asking again at each role transition. Ask only when required authority or essential information is missing, and identify the exact blocked action and reason.
Before requesting approval for merge or deployment, prepare the reviewable diff, applicable checks, and remaining limitations. Existing explicit authorization remains valid within its scope; preserve repository checks and host approval policies.

## Focused review perspectives
Use these as review checklists, not instructions to launch additional agents.
- Python implementation: async cancellation, timeouts, concurrency, client lifecycle, response validation, and optional configuration compatibility.
- Privacy and security: no prompt, answer, memory, token, authentication file, raw exception, Discord identifier, or bank identifier in logs or public responses.
- Regression review: provider routing, user/server/channel bank separation, DM failure without public fallback, memory outage versus empty memory, and disabled-feature defaults.
- Operations review: no changes to production credentials, volumes, model settings, or user memory without task authorization.

## Verification
For runtime changes, run:
`python -m unittest discover -s tests -v`

For evaluation or observability changes, also run the checks defined in .github/workflows/tests.yml:
`python -m unittest discover -s evals -v`
`python -m unittest discover -s tests -p test_observability.py -v`
The evaluation environment uses PYTHONPATH=.:tests and DEEPEVAL_TELEMETRY_OPT_OUT=YES on Linux; adapt the path separator on Windows.
Use the existing dependency files and offline fixtures. Do not use real user prompts, memory, or paid model calls in CI.
The Hindsight smoke test creates synthetic data and can incur costs. Run it only when the task authorizes that service check; never target a user bank.
Documentation-only changes require content review, not invented runtime test results.

## Observability and cost evidence
Reuse the current bot_trace and optional Langfuse integration.
Keep completed, degraded, failed, and delivery_failed distinct. A completed flow does not establish answer correctness.
Treat unobserved search, token usage, or cost as unknown, not zero. Do not estimate subscription usage as billable API cost.
Before introducing cheaper-model routing or multiple workers, compare representative task quality, latency, retries, and total observed usage. Do not assume delegation lowers cost.
Do not label an execution path free based on an unverified promotion. Keep subscription allowance, API charges, and external-service costs separate; verify current terms before making a cost claim.
Use available usage records when relevant. Do not require a screenshot before and after every small job, or infer zero usage from an unchanged rounded display.
Never broaden telemetry to include question or answer text without explicit authorization.

## Delivery
Use a branch and PR for changes. Preserve existing CI and protection rules; do not bypass required checks.
Report the change, evidence actually observed, and remaining unverified behavior.
Track source change, checks, acceptance, PR creation, merge, deployment, and end-to-end validation as separate states. A PR or successful merge alone does not prove deployment or operational recovery.
When execution is unavailable, continue safe source review and prepare a reviewable change, but state that local execution was not performed.
