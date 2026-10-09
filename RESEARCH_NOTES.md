# KareOS: computer access for specialist AI agents

Prepared: 9 October 2026 (Asia/Calcutta)  
Branch when prepared: `KareOs-V1/INT_Revanth`  
Status: isolated implementation built; real browser smoke checks and 39 automated checks passed. The expanded 108-trial comparison is complete: [deep-test results](reports/DEEP_RESULTS.md). It found a small gain on one case, five computer failures and roughly doubled latency, without establishing a reliable overall accuracy improvement. Earlier pilots remain in [reports/RESULTS.md](reports/RESULTS.md) and [reports/REQUIRED_RESULTS.md](reports/REQUIRED_RESULTS.md). See [IMPLEMENTATION.md](IMPLEMENTATION.md) for commands and boundaries.

## 1. Purpose and the observation behind this experiment

The team gave the same prompt to Grok and Grok Bot and observed a substantially better answer from Grok Bot. We want to investigate whether giving KareOS specialist agents computer access produces a similar improvement.

That comparison motivates the experiment, but does not establish its cause. The two products may differ in model version, instructions, reasoning budget, retrieval, memory, tools, and verification steps. A longer or better-presented answer may also contain unsupported claims. Our experiment should measure useful, correct findings and evidence quality independently of presentation.

Working hypothesis: an agent can produce better results when it can investigate a question, access relevant evidence, perform calculations, inspect outcomes, and revise its answer. A computer provides one way to support those activities. The size and reliability of any improvement remain unknown.

## 2. What computer access means

An agent does not need a dedicated physical machine. For this experiment, its computer is an isolated Linux environment with a real browser, a temporary filesystem, and bounded command execution. Each run receives its own environment and browser state.

The intended interaction loop is:

1. Receive the synthetic clinical case and task.
2. Observe the browser or workspace.
3. Select an allowed action: navigate, inspect, click, read a file, or calculate.
4. Execute the action through an authenticated service.
5. Return the actual result, including text and a screenshot where supported.
6. Decide whether to investigate further, request missing information, or finish.
7. Return findings with traceable evidence and appropriate uncertainty.

OpenAI documents browser/desktop control using model actions or code execution in an application-provided environment. It emphasizes preserving environment state between calls and verifying outcomes. This is a general integration reference, not a requirement to switch KareOS to an OpenAI model. [Computer-use documentation](https://developers.openai.com/api/docs/guides/tools-computer-use)

## 3. Existing KareOS foundations

The repository combines a Next.js frontend, a unified FastAPI backend, LangGraph clinical reasoning, and the separate Svaani documentation API. RDS is the source of truth for application and clinical metadata; private S3 stores files and artifacts.

The native registry in `agents/registry.py` currently declares 19 agents across five tiers. The CDSS graph supports 15 board specialist identities. The YAML configuration lists 20 agents but differs from the native registry; it should not be used as the implemented-agent count.

Relevant implementation areas:

| Existing area | How it helps the experiment |
| --- | --- |
| `agents/cdss/runtime.py` | Boundary that invokes specialist reasoning; supports native and free-form modes. |
| `agents/freeform/runtime.py` | Existing investigation loop, validated actions, scope, budgets, and model boundary. |
| `agents/freeform/contracts.py` | Typed actions and tenant/user/encounter/document scope. |
| `agents/freeform/profiles.py` | Code-owned capability grants for specialist roles. |
| `agents/freeform/gateway.py` | Scoped patient and knowledge retrieval with registered evidence. |
| `agents/freeform/model.py` | Current text-based model interface through KareOS's model router. |
| `agents/conference/` | Logical agent sandboxes, bounded collaboration, and recorded discussion. These are not operating-system computers. |
| `eval/core/` | Patient-fact, citation, safety, defensibility, uncertainty, and useful-insight checks. |
| `eval/runners/run_live.py` | Existing live record/replay evaluation pattern. |

The baseline already has tools. We must describe it as the current agent without computer access, rather than presenting it as an entirely tool-free chatbot.

## 4. Open-source projects assessed

These assessments were based on the projects' documentation, manifests, and selected runtime code. The selected OpenBot computer component has now been built and exercised at commit `4773ef6866544a497c2a33ed2475bb4aa1de0475`. The other projects have not been executed, and none has received a comprehensive audit here.

| Project | Relevant capabilities | Fit and limitations |
| --- | --- | --- |
| [CopilotKit OpenBot](https://github.com/CopilotKit/OpenBot) | Computer containers, browser/files/shell, action policy and audit infrastructure, external agents through AG-UI. Root project is MIT-licensed. | First candidate for a standalone computer-service integration. Alpha; the complete product requires CopilotKit Intelligence and its project/license setup. It is a template, not a published drop-in package. |
| [Rakazo](https://github.com/elie222/rakazo), linked from [rakazo.com](https://rakazo.com/) | Browser, terminal, graphical desktop, Docker and remote sandbox adapters. Apache-2.0 root license. | Alternative for full desktop experiments. Agent and computer runtimes are separate. It defaults to a shared Team Computer; select a Private Computer for isolated workloads. [Runtime and isolation details](https://github.com/elie222/rakazo/blob/main/docs/computer-runtime.md) |
| [OpenMausBot](https://github.com/milind-soni/OpenMausBot) | Per-bot computers, cloud desktops/local VMs, permissions and connected apps. Bots run through Claude/Codex/Grok CLIs. | Useful demonstration/reference. Using the complete app would introduce a different agent harness, making the causal comparison harder. Core is Apache-2.0, while `enterprise/` has separate production licensing. [Licensing details](https://github.com/milind-soni/OpenMausBot/blob/main/LICENSING.md) |
| [Cloudflare Computer](https://github.com/cloudflare/computer) | Durable Object-backed filesystem and container, shell, and JavaScript execution backends. MIT. | Infrastructure reference or later synthetic-data prototype. It does not by itself supply our complete graphical desktop-control loop. Explicitly preview-only and currently unsuitable for production. Its persistence topology differs from KareOS's RDS/S3 boundaries. |
| [OpenHuman](https://github.com/tinyhumansai/openhuman) | Rust agent harness, browser/desktop control, memory, orchestration, and run journals. | Useful reference for efficient tool loops. Larger integration change for our Python/TypeScript stack. Its workspace declares GPL-3.0-only; copying or embedding code requires license compatibility assessment. [Workspace manifest](https://github.com/tinyhumansai/openhuman/blob/main/Cargo.toml) |

No project's feature list or general coding benchmark demonstrates improved clinical accuracy for KareOS. That is the question our evaluation must answer.

## 5. Repository choice

### Primary candidate: OpenBot's computer service

First investigate running OpenBot's `agent-computer` component and container lifecycle separately from its complete application. Keep KareOS's specialist model, instructions, clinical scope, and evaluator in charge.

Its computer service is an authenticated HTTP process with browser and workspace operations. Browser interaction primarily uses accessibility snapshots and element references, so the first browser experiment need not depend on screenshot interpretation. The service's own comments state that policy and audit live in the upstream gateway, not in the computer process. Our adapter must therefore enforce those boundaries. [Computer-service source](https://github.com/CopilotKit/OpenBot/blob/main/agent-computer/src/index.ts)

Feasibility questions to resolve before adoption:

- Can we build and run the computer component without the complete OpenBot UI, agent harness, and Intelligence service?
- Which shared modules, runtime dependencies, and license notices are required?
- Can its browser, file, and shell operations be exposed cleanly to KareOS's action loop?
- Does it provide the action/observation features needed by the benchmark, and which require additional work?
- Can we reliably reset and destroy the environment after success, cancellation, or failure?

The full OpenBot stack documents separate computer and supervisor services, plus gateway-controlled policy and audit. Its shipped policy defaults and proxy-only egress controls must be reviewed rather than assumed sufficient for our experiment. [Architecture](https://github.com/CopilotKit/OpenBot/blob/main/docs/architecture.md)

### Alternative: Rakazo's Docker computer runtime

If the OpenBot extraction requires too much platform coupling, or we need richer graphical desktop operation, evaluate Rakazo's Docker runtime/provider boundary. Its documented contract covers provisioning, observation/actions, commands, files, and teardown; graphical operation requires a model that can consume image results. Private computers provide the isolation we need. [Computer runtime](https://github.com/elie222/rakazo/blob/main/docs/computer-runtime.md)

Rakazo's local Docker path requires Docker Engine, its computer image, and an authenticated supervisor, without requiring a remote sandbox account. [Provider requirements](https://github.com/elie222/rakazo/blob/main/docs/self-host-sandbox-providers.md)

This is a conditional choice, not a claim that either component already works independently with KareOS.

## 6. Proposed integration

```text
Synthetic case + fixed experiment configuration
                    |
         Existing KareOS specialist runtime
                    |
         Experiment-selected capability set
             /                       \
   Existing/structured tools       Computer adapter
                                      |
                         Scope + action authorization
                         Budgets + evidence registration
                         Action/result recording
                                      |
                         Authenticated computer service
                                      |
                         Fresh browser + shell + files
```

Proposed new modules, subject to impact analysis and feasibility findings:

- `agents/computer/adapter.py`: provision/reset/observe/act/execute/read/close boundary.
- `agents/computer/contracts.py`: validated actions and bounded result schemas.
- `agents/computer/policy.py`: experiment-owned action and network permissions.
- `eval/runners/computer_compare.py`: paired runs, configuration capture, recording, and replay.
- `eval/computer_cases/`: synthetic case inputs; reviewer expectations stored separately from agent-visible inputs.

Add computer operations as optional capabilities in the existing free-form runtime. The experiment owns the switch; an agent cannot grant itself access. Preserve existing action validation, scope checks, output schemas, and clinical safety stages.

Any Python execution remains inside the computer environment. Use validated clinical calculator services for established clinical scores; exploratory Python calculations must show their inputs and results and must not silently become authoritative clinical facts.

A browser observation or agent-written note is not automatically verified evidence. Register source identity, document/page details where available, relevant excerpts, and retrieval time before the final answer cites it.

## 7. First specialist and model setup

Start with **nephrology**, which is supported by the current CDSS specialist runtime and aligns with existing kidney-injury evaluation material. This avoids first adding another specialty or replacing the whole board.

Hold constant the provider, exact model identifier/version, clinical instructions, synthetic case, and answer schema. Record reasoning settings, sampling settings, and limits. Disable silent provider fallback for scored runs or mark those runs incomparable.

The current free-form `ModelPort.complete` is text-based. Browser accessibility/text observations can fit that interface. Screenshot reasoning requires an explicit image-capable adapter and a compatible model. If a different model is necessary, use it across every experimental arm and report the production-model comparison separately.

Browser-controlled and screenshot-controlled modes should be reported separately. A successful DOM/browser test does not establish that the agent can operate arbitrary desktop applications.

## 8. Experimental arms

| Arm | Configuration | Question answered |
| --- | --- | --- |
| A: current baseline | Same KareOS agent and existing permitted tools; no computer. | What does the current workflow achieve? |
| B: structured-tool control | Same agent, plus access to the additional evidence/files/calculations through structured tools. No browser/desktop control. | How much improvement comes from added information and tool capabilities? |
| C: computer-enabled | Same agent, with a fresh computer exposing equivalent additional resources through browser/workspace operations. | Does computer operation add value beyond the structured-tool control? |

A versus C tests the proposed enhancement. B versus C helps distinguish the computer interface's contribution from the contribution of newly available evidence and calculations. The resources available to B and C must be documented and equivalent; differences invalidate that narrower causal claim.

Do not transplant another project's model, memory, system prompt, or agent loop into C while leaving A unchanged. That would test a bundle of changes instead of computer access.

## 9. Cases and experimental controls

Begin with a smoke test on three synthetic cases. Then run **12 cases x 3 arms x 3 repetitions = 108 scored runs**, separate from setup/smoke runs.

Case categories should include:

- Kidney injury with competing explanations.
- Medication-related hazards hidden in a synthetic medication list.
- Electrolyte abnormalities requiring recognition and clarification.
- Conflicting laboratory reports and inconsistent units.
- Missing baseline measurements where uncertainty must be preserved.
- Reports that require comparing trends across documents.
- Questions that require finding and supporting a relevant evidence claim.
- Straightforward cases where additional speculation adds no useful finding.

Use existing `eval/cases/worsening_renal_function.json` and `eval/value_add_cases/hidden_hyperkalemia.json` as starting material after checking suitability for an individual-specialist evaluation. Existing board scorecards may require an adapter; do not score a single specialist as though it were a complete multidisciplinary board.

Before model runs, define expected findings, acceptable alternatives, missing-data expectations, evidence support, and serious failures. Keep grading instructions/reference answers outside all agent-visible files and computers.

Controls:

- Start with a fixed evidence collection exposed through a local test portal and equivalent structured tools. This makes results repeatable without live-web changes.
- Randomize/interleave arm order within each case/repetition.
- Reset agent memory, browser profiles, files, and environment between scored runs.
- Use the same total reasoning/time/token ceilings and final-answer length limit; capture actual consumption rather than assuming equal usage.
- Predefine a computer-action limit and cancellation deadline during the smoke test, then freeze them for the scored pilot.
- Keep failed and timed-out runs in the report. Distinguish infrastructure failures from clinical reasoning failures.
- Test live public browsing afterward as a separately labeled exploratory phase, retaining source snapshots/hashes where possible.

Repeated runs measure variability. Twelve distinct cases remain a small pilot; 108 runs are not 108 independent clinical cases.

## 10. Evaluation and review

The primary quality measure is coverage of correct, clinically relevant expected findings per case. Specify its rubric and denominator before running. Track incorrect additional findings separately so verbosity cannot increase the score by itself.

| Measure | Assessment |
| --- | --- |
| Correct key findings | Case-specific reviewer rubric, including acceptable alternative reasoning. |
| Important omissions | Expected findings or clarifications that were missed. |
| Fabricated patient facts | Compare factual claims against the supplied synthetic record. |
| Citation validity and support | Check source existence, actual retrieval provenance, and whether the source supports the claim. |
| Useful additional insights | Extend existing value-add checks, with reviewer confirmation of correctness. |
| Appropriate uncertainty | Check handling of missing, conflicting, stale, or insufficient data. |
| Serious safety failures | Predefined failure categories; report each failure individually. |
| Completion reliability | Success, timeout, cancellation, invalid action/output, and environment/provider failure. |
| Cost and speed | Actual model usage/cost, computer cost where available, elapsed time, and action counts. |

Reuse the existing evaluator where it applies. Keyword/embedding checks and automated judges provide signals; they do not independently establish clinical correctness.

Provide reviewers with final answers under randomized labels so they do not know the arm. Seek clinician review, preferably two reviewers with adjudication of disagreements. Keep readability/presentation scores separate from clinical quality. If clinician review is unavailable, label the results preliminary and avoid claims of improved clinical accuracy.

## 11. Pilot decision rule

Before the scored pilot, confirm or revise this proposed target:

- At least a **10-percentage-point improvement** in average correct-finding coverage for C over A.
- No observed increase in fabricated facts or unsupported claims.
- No severe safety failures in the pilot.
- Operational cost, latency, and completion reliability within a pre-agreed budget.

The 10-point target is a proposed engineering decision threshold, not a clinical standard or established statistical effect size. Report paired case-level differences and uncertainty, accounting for repeated runs within a case. Zero observed severe failures does not prove safety.

Use C versus B to decide whether computer interaction earns its additional complexity. If B performs similarly or better, structured tools may deliver the useful improvement more efficiently. If results are mixed, investigate the cases and actions rather than relying only on an aggregate average.

A positive pilot supports a larger benchmark and specialist-specific testing. It does not authorize production deployment or rollout to all 19 agents.

## 12. Isolation, persistence, and data boundaries

- Use synthetic patient information and public/synthetic reference documents only.
- Run computer services on a private, authenticated interface, with a fresh environment for each run.
- Do not expose RDS credentials, application secrets, host home directories, or the KareOS source workspace to agent computers.
- Keep model credentials in the trusted runner, outside the agent-controlled shell.
- Keep any Docker socket exclusively in the trusted lifecycle supervisor; never mount it into the agent computer.
- Restrict browser and shell egress at the infrastructure boundary, including raw socket paths. Proxy settings alone do not establish full network isolation.
- Block metadata endpoints, unapproved internal services, arbitrary downloads, and unauthorized transmissions.
- No real hospital logins, patient-record mutations, order placement, or EHR export in the experiment.
- Keep step/time/resource limits, cancellation, and teardown available.
- Treat page/document text as untrusted input, not as instructions that can change permissions.
- Local research artifacts may contain synthetic test data only. Any later production artifact design must keep metadata/audit records in RDS and objects in private S3 with tenant-scoped access and presigned URLs.
- Do not introduce Supabase, Wasabi, UploadThing, or local-PHI persistence into KareOS.

## 13. Recorded artifacts and deliverables

For each run, capture case/repetition/arm IDs, code and dependency revisions, model configuration, prompt/evidence fingerprints, allowed capabilities, final output, tool actions/results, screenshots where applicable, source provenance, usage/cost, elapsed time, failure classification, and evaluator results.

Keep the agent-visible task package separate from reviewer expectations. Store only synthetic research artifacts locally and avoid recording credentials or secret-bearing URLs.

Expected deliverables:

1. A pinned candidate runtime with repeatable startup/reset/teardown instructions.
2. An optional KareOS computer adapter with the feature disabled by default.
3. Synthetic tasks, fixed evidence resources, and an independent review rubric.
4. A paired comparison runner and replayable recordings.
5. A Markdown comparison report with per-case outputs, quality measures, cost/latency, failures, and limitations.
6. A recommendation to expand, retain structured tools, change the design, or stop the experiment.

## 14. Plan of action

| Phase | Work | Completion evidence |
| --- | --- | --- |
| 0: preflight | Preserve the current working tree; recover/rebuild the missing GitNexus index and run required impact analysis before changing existing code. Check Docker/Linux container support and available model interfaces without exposing credentials. | Resolved impact results and documented environment readiness. |
| 1: feasibility | Pin OpenBot; inspect its computer dependencies; attempt standalone service startup. Evaluate Rakazo if the primary path is unsuitable. | A real browser can navigate, inspect, read/write a synthetic file, execute a bounded calculation, and be destroyed/reset. |
| 2: adapter | Implement validated computer actions, scope/policy checks, budgets, evidence registration, and action recording behind an experiment flag. | Meaningful isolation, invalid-action, cancellation, and teardown checks pass. |
| 3: smoke test | Run three synthetic cases; verify all arms use the same model and their intended capabilities. Freeze benchmark configuration and budget estimates. | Actual model-driven computer actions, valid final outputs, and complete recordings. |
| 4: scored pilot | Run the fixed 12-case, three-arm, three-repetition benchmark. | 108 accounted-for runs, including failures; replayable scores and reviewer packets. |
| 5: review | Obtain blinded review, compare paired results, explain failures and cost differences. | A documented decision supported by results and stated uncertainty. |
| 6: expansion | Only if supported by the pilot, add selected specialists and a broader benchmark before considering deployment. | Evidence that improvements transfer beyond the initial specialist/cases. |

Setup may require Docker support, image downloads, provider credentials in the trusted runner, and paid model calls. Determine actual requirements and estimate the cost before starting live evaluation. Mock action tests verify plumbing; they must never be reported as evidence of better agent reasoning.

## 15. Expectations and limitations

Potential benefits: better document investigation, grounded citations, useful calculations, more complete findings, and clearer evidence trails.

Potential costs: extra model turns and latency, computer resource usage, failed navigation, distracting evidence, incorrect tool choices, and additional isolation/maintenance work.

No improvement magnitude is promised. Computer access can help particular tasks, produce no measurable change, or reduce performance. Specialist-specific tools and verified information may explain most of the benefit. Full-board outcomes may also differ from the individual-agent result.

The immediate goal is to learn which configuration delivers the best defensible output for KareOS under measured constraints.

## 16. Current repository state and change policy

Lalith's changes were merged into the working tree of `KareOs-V1/INT_Revanth` using a merge that stopped before committing. The existing merge remains uncommitted.

The isolated research folder now contains the pinned Docker/OpenBot browser, frozen agent source copies, synthetic fixtures, live comparison runs and retained AI-review artifacts. The expanded comparison accounted for all 108 trial slots. Research tools use synthetic data and separate settings; application behavior and the pending parent merge remain unchanged. AI audit results are provisional; qualified-clinician validation remains outstanding.

Do not commit, push, or complete the pending merge as part of this research work. Keep new experiment changes distinguishable from the existing staged merge. Future code changes must follow `AGENTS.md`, including impact analysis before editing functions and graph change analysis before any separately authorized commit.

The documentation-only pre-edit GitNexus impact attempt could not resolve callers, processes, or risk because this checkout has no indexed repository. That result is unresolved, not a low-risk graph verdict. No executable symbol was changed for this document.
