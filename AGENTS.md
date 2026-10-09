# Development instructions

## Scope and priorities
This repository contains a Python Discord bot, optional Hindsight memory, a subscription answer extension, and privacy-preserving observability.
Read README.md and the files involved in the requested change before editing. Preserve existing provider behavior and optional configuration defaults.
Prefer the smallest change that solves the observed problem. Do not install entire agent catalogs, new orchestration frameworks, or model dependencies solely to obtain development guidance.

## Diagnose before changing
1. Identify the failing boundary: Discord delivery, memory service, answer provider, search response contract, or observability.
2. Record the observed symptom and a reproducible case. Distinguish missing evidence from an empty result.
3. Trace the actual request path and inspect the relevant existing tests.
4. Fix the demonstrated cause; use a regression test for behavior changes.
5. Reproduce the original case and run the relevant checks before reporting success.
For deployment incidents, code, CI, deployment status, service health, and end-to-end behavior are separate evidence. A successful CI run does not prove production recovery.

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
Never broaden telemetry to include question or answer text without explicit authorization.

## Delivery
Use a branch and PR for changes. Preserve existing CI and protection rules; do not bypass required checks.
Report the change, evidence actually observed, and remaining unverified behavior.
When execution is unavailable, continue safe source review and prepare a reviewable change, but state that local execution was not performed.
