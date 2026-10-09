# Isolated computer experiment

**Standalone update:** use [README.md](README.md) for portable setup and export. Bundled sources are checked without parent sources or Git. Only the original checkout uses a local path-bound parent guard. `.env.template` is the public blank-key configuration; the user's `.env.example` remains private. Historical generation files were archived in the completed deep run's `frozen_sources/` before portability changes; original outputs and hash records are unchanged.

Portability validation: a clean renamed export completed setup in a fresh venv, passed 43 checks and three real-browser smoke cases. [Validation record](reports/STANDALONE_VALIDATION.md). No new live inference or clinical-quality comparison was run during this packaging update.

Implemented and validated on 9 October 2026. **Computer infrastructure works; AI output improvement has not yet been established.** The voluntary-adoption results are in [reports/RESULTS.md](reports/RESULTS.md). The separate comparison requiring actual browser use is described in [REQUIRED_COMPARISON.md](REQUIRED_COMPARISON.md) and reported in [reports/REQUIRED_RESULTS.md](reports/REQUIRED_RESULTS.md).

## What exists

The selected component is CopilotKit/OpenBot's MIT-licensed `agent-computer`, pinned to commit `4773ef6866544a497c2a33ed2475bb4aa1de0475`. Its browser/files/shell HTTP service runs independently of the full OpenBot application. This lab adds a synthetic portal and a bounded calculator; it does not use CopilotKit Intelligence or change KareOS providers.

`lab.py` extends a byte-identical snapshot of KareOS's free-form specialist runtime. The snapshot hashes are recorded in `source_snapshot/manifest.json`. Production package initializers are bypassed; retrieval is replaced by `FixtureGateway`, persistence by `NullRunStore`, and model access by an explicit research adapter. The existing validated specialist output and evidence-ID validation are reused.

| Arm | Available tools |
|---|---|
| A | Existing search/fetch over fixed synthetic documents; no computer |
| B | A plus structured document listing/reading, arithmetic and scratch notes |
| C | A plus a real Chromium browser, accessibility snapshots, link clicks, page reading, container arithmetic and scratch files |

This is a single-specialist pilot, rather than the complete clinical board. Delegation is disabled equally in all arms. Production clinical score calculators are replaced equally with an explicit unavailable/missing-data response; they cannot reach the admission database. The common system prompt and runtime are reused, with arm-specific tool schemas/instructions. The default specialty is differential diagnosis.

The optional `--protocol required` selects `protocol.required.json`. In this protocol all arms must read both documents before finalizing. A uses search/fetch, B must use structured retrieval, and C must use its browser; B/C cannot bypass their interface with search/fetch. This ensures actual computer use. The original offered-tools protocol remains available and its results are kept separate. Expected browser input errors are returned to the agent for correction; other browser failures remain fatal.

The model remains free to choose whether to use its extra tools. C's `lab_tool_trace` records actual adoption; assigning a computer does not prove it was used. Screenshots are saved for inspection, but this version sends text observations to the model. It does not test visual reasoning, a general desktop, unrestricted shell access, or public internet research.

## Closed-space boundaries

- All source copies, dependencies, fixtures, settings and reports live in `computer_research`. No parent package, route, production agent or environment file was edited.
- Each computer run gets a fresh non-root container and browser profile. Containers have `--network none`, no published ports, no host mounts, all capabilities dropped, resource limits and `no-new-privileges`.
- The only portal is `127.0.0.1:8765` inside that container. The host controller uses `docker exec` to access the authenticated OpenBot service on container loopback. Container networking cannot reach KareOS, AWS or the public internet.
- The host model adapter can reach the explicitly configured inference provider. Research model credentials stay on the host and are never passed into the computer. The ephemeral computer-service token is not written into reports.
- Model commands are limited to allowed portal paths, simple `.txt` note names, and a fixed arithmetic command evaluated without Python `eval`. No arbitrary model-provided shell command is exposed.
- No patient data is loaded. All 12 cases and their documents are invented exercises. The fixture interpretation notes are not published guidelines or clinical validation.
- Containers are removed in `finally` paths and cleanup verifies their ownership label. A killed host process can interrupt cleanup; inspect only containers with label `kareos.computer-research=pilot-v1` before manually removing a leftover.
- Docker Desktop was started for the experiment and two local research images were built. No research containers remain after validation. Docker images/cache remain available for future runs.
- A nested, uncommitted Git repository was initialized solely for isolated GitNexus indexing. Parent HEAD, merge state and staged index were preserved. Do not stage this folder as a submodule by accident.

## Run it

From PowerShell:

```powershell
Set-Location 'D:\Kraionyx AI\KareOS-V1\computer_research'
# Already completed on this machine; use to reproduce dependencies/images:
.\setup.ps1

.venv\Scripts\python.exe lab.py check
.venv\Scripts\python.exe -m pytest -q --basetemp .cache/pytest-temp
.venv\Scripts\python.exe lab.py smoke
```

For live inference, configure `.env` **inside this directory** with an explicit provider/model. Bedrock supports a locally configured AWS research profile or `RESEARCH_BEDROCK_API_KEY` bearer authentication. The research-specific key takes precedence over `BEDROCK_API_KEY` and `AWS_BEARER_TOKEN_BEDROCK`. An HTTPS OpenAI-compatible endpoint and local key remain an alternative. The user's supplied `.env.example` now contains credentials and is Git-ignored; do not share or commit it or `.env`. No parent `.env` is read or written. This test will not silently substitute a mock model if configuration is missing.

```powershell
# After configuring the research .env:
.venv\Scripts\python.exe lab.py run --cases 3 --repeats 1
# Expanded comparison with mandatory evidence retrieval through each arm's route:
.venv\Scripts\python.exe lab.py run --protocol required --cases 12 --repeats 3
# Actual browser versus retrieval control, three cases repeated twice:
.venv\Scripts\python.exe lab.py run --protocol required --cases 3 --repeats 2
```

The small run is 9 investigations; the full run is 108. Each investigation has at most 16 logical model calls, 14 tool calls and a 300-second inference deadline. The API-key transport retries only HTTP 429, at most four HTTP attempts with 10/20/40-second waits, inside the existing call deadline. Permanent authentication errors are not retried. Provider status/retry events are recorded without headers or credentials. All arms share the same model, temperature, output contract and budgets. Computer startup latency is separately recorded alongside total latency. Run order is randomized with a fixed seed. Cases are truncated only by the explicit `--cases` option.

## Results and review

The completed 108-trial comparison is summarized in [DEEP_RESULTS.md](reports/DEEP_RESULTS.md). It preserves every failure and original output. Primary quality counts use exact, source-checked Codex adjudication, with one borderline answer left uncertain. All potential passes were fully read; verified failure witnesses suffice for negative primary decisions. A separate Sonnet 4.5 judge reviewed every completed answer with arm/tool traces hidden. Neither is a qualified clinician.

The original Haiku judge produced invalid references and semantic contradictions; its partial records are retained. The replacement review is a documented post-generation evaluation amendment. The case rubric and all generator settings stayed fixed. `deep_review_v2.py` checks exact string quotes or scalar values, records raw requests/responses and permits one uniform format-validation repair. It invokes the global Sonnet inference profile only for synthetic review; it does not change the generator's `.env` model setting.

To replay the retained audit/report without regenerating agent answers:

```powershell
.venv\Scripts\python.exe deep_review_v2.py required-20261009-200529
.venv\Scripts\python.exe build_deep_report.py required-20261009-200529
```

Existing audits are reused only when original result hashes match. The comparison builder also verifies frozen generator/reviewer files, all original output hashes, exact adjudication witnesses and parent integrity. A new run requires its own source-checked adjudication; do not copy scores between runs.

Live reports contain settings, actual provider-reported tokens, model prompts/responses, tool results, evidence references, completion/failure status, latency and optional estimated cost. Cost stays unknown unless explicit per-million-token rates are supplied. Provider requests that fail before returning usage may incur unreported charges; successful-response token totals are not a complete billing ledger. Keep the chosen model and pricing fixed during a comparison.

The `blinded-review` directory contains case facts, outputs and review forms without arm names or tool traces. Keep `summary.json` (which contains the arm mapping) away from blinded reviewers. Clinicians should score supported additional findings, unsupported claims, citation support and usefulness. Keyword coverage is only a debugging proxy: mentioning a word, including in a negation, can receive credit. Citation registration confirms a source was retrieved, not that it supports a claim. Neither metric proves medical accuracy.

Do not conclude that computer access improves clinical performance from the infrastructure checks, scripted tests or a small unreviewed pilot. A positive result would require clinician-reviewed paired case/repeat comparisons, improvement over both A and B, acceptable unsupported claims and workable latency/cost. These 12 deliberately simple synthetic exercises are a first feasibility benchmark; expand and externally review them before assessing clinical usefulness or generalization.

## Validation completed

- **39 automated checks passed** in 9.73 seconds. Coverage includes the real specialist output contract in A/B/C (C uses a real container), source registration, unread-citation rejection, denial of another arm's tools, shared tool budgets, calculator restrictions, path restrictions, missing tool arguments and preventing production calculator imports. Additional checks cover Bedrock bearer-key transport, research-key precedence, parity with the production JSON parser, throttling/authentication retry behavior, required source retrieval, disabled shortcuts, stale-snapshot recovery and fatal browser failures. Scripted model responses in these checks validate plumbing only. Saved test results: [validation.xml](reports/validation.xml).
- **Three real computer smoke runs passed**: navigation, accessibility snapshots, link clicks, document text, shell arithmetic, note round trips, screenshots, denied external URLs/path escapes/code expressions, direct socket egress blocked and teardown.
- Latest smoke report: [SUMMARY.md](reports/smoke-20261009-183027/SUMMARY.md); machine-readable checks and image identities: [summary.json](reports/smoke-20261009-183027/summary.json).
- A live three-case pilot was attempted using the configured Claude Haiku 4.5 model. The primary provided Bedrock key failed authentication; the second supplied key succeeded and was configured only as `RESEARCH_BEDROCK_API_KEY` in the research `.env`. See [current results](reports/RESULTS.md) for completion, failures, actual tool adoption and the limits of the comparison. Earlier failed attempts are retained. No clinical accuracy claim is made.
- Parent integrity passed: branch `KareOs-V1/INT_Revanth`, HEAD `87f90342c56e094e959aeabf1dd05b360273b27d`, pending Lalith merge `f405f618ae2da531aaa416f9469d176aed6c9541`, staged index unchanged, no tracked working-tree changes, and copied/original source hashes match. Nothing was committed or pushed.
- GitNexus impact on the copied specialist initially reported one importer and no affected execution flows (LOW). New lab-symbol checks were confirmed with local text searches when the graph returned UNKNOWN. The isolated graph later indexed successfully, but full-text search was unavailable and process enumeration was truncated. This is not claimed as a complete graph regression check; no commit was made.

## Files

| File | Purpose |
|---|---|
| `README.md` | Standalone setup, tests and per-agent computer roadmap |
| `RESEARCH_NOTES.md` | Preserved original rationale and repository comparisons |
| `lab.py` | Runtime adapters, live inference, evaluation schedule and reports |
| `computer.py` | Container lifecycle, authenticated transport and tool policy |
| `portal.py`, `calculator.py` | Container-local evidence and arithmetic |
| `cases.json`, `protocol.json` | Frozen synthetic fixtures and shared limits |
| `smoke.py`, `test_lab.py` | Infrastructure and runtime verification |
| `DEEP_TEST_PLAN.md` | Expanded comparison design registered before generation |
| `deep_review.py`, `deep_review_v2.py` | Retained initial judge and replacement masked audit |
| `build_deep_report.py` | Hash-checked adjudication, metrics and paired case analysis |
| `Dockerfile`, `start.sh` | Research overlay atop the pinned OpenBot component |
| `setup.ps1`, `requirements.lock.txt` | Reproducible local setup |
| `.env.example` | Local supplied settings and credentials; Git-ignored |
| `.env.template`, `export.ps1` | Public configuration and clean project export |
| `source_snapshot/` | Frozen copies; never modify them to match a changed parent |

Upstream source: [OpenBot repository](https://github.com/CopilotKit/OpenBot). The MIT notice remains in the vendored checkout. This lab has not comprehensively audited the upstream service. Its browser sandbox is off under the upstream default Docker configuration; synthetic pages, the container boundary and disabled networking are the present experiment's containment measures.
