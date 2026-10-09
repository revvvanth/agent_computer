# Agent Computer Research

A standalone project for giving AI agents their own isolated computers and measuring whether that improves their output. Copy or export it to any folder, including a folder with a different name. KareOS services, its database, authentication and environment files are not needed.

**Goal:** computer access for KareOS agents, with a separate browser, workspace and computer session for each active agent. Develop and evaluate here first, then integrate the proven adapter into KareOS.

The controller runs on your machine. Each computer trial runs a fresh local Linux Docker container containing Chromium and CopilotKit/OpenBot's computer service. Model inference uses the provider configured in this project's `.env`, separately from computer hosting. The computer component works independently of the full OpenBot app.

## What works today

The project includes a frozen specialist runtime, three comparison arms, 12 synthetic cases, bounded tools, isolated containers, screenshots, traces, live inference and retained reviews. The runner currently tests **one specialist per trial**, sequentially. It does not yet orchestrate all KareOS agents or retain computers across tasks.

Standalone setup was verified from a clean renamed export with a newly created venv: **43 checks passed**, plus **three real-browser smoke cases**. Checks include two simultaneously alive computers with separate browser/file state, running without parent Git access, and rejecting modified baseline source. See [portability validation](reports/STANDALONE_VALIDATION.md); this verifies infrastructure, not AI accuracy.

| Required-route arm | Tools | Latest strict quality score | Completed |
| --- | --- | ---: | ---: |
| A: without computer | Search/fetch over the synthetic library | 8.3–11.1% | 36/36 |
| B: structured control | Document listing/reading, arithmetic, scratch notes | 8.3% | 36/36 |
| C: with computer | Real browser, DOM/accessibility observations, page reading, arithmetic, scratch files | 13.9% | 31/36 |

These are provisional AI-adjudicated benchmark pass rates, **not clinically validated accuracy**. The 108-trial test found extra passes on one fluid-balance case, five computer failures and approximately doubled mean time (32.8s A versus 65.9s C). It did not establish a reliable overall improvement. Screenshots are saved but are not sent to the model; this version tests browser text/DOM interaction, not visual desktop reasoning.

See [results](reports/DEEP_RESULTS.md), [implementation details](IMPLEMENTATION.md), [required-route comparison](REQUIRED_COMPARISON.md), and [the original rationale and repository comparisons](RESEARCH_NOTES.md). Historical KareOS references describe the original environment, not standalone dependencies. Some historical links need the optional raw reports export.

## Requirements

- Windows, PowerShell, Git and Python **3.11** available through `py -3.11`.
- Docker Desktop running the **Linux engine**. Each current container has limits of 2 CPUs and 2 GiB; allow additional capacity for Docker/browser startup.
- Internet for dependency downloads, the pinned OpenBot checkout/image build and live model inference. Agent computers have no external network access.
- For live inference: a configured Bedrock research key/AWS profile or an HTTPS OpenAI-compatible provider. Plumbing tests and browser smoke checks need no model credentials.

The setup script targets Windows. Other platforms can reproduce its Python venv, pinned checkout and Docker builds manually; that setup path has not been verified here.

## Export or move

From this project directory:

```powershell
# Destination must be a NEW folder; existing projects are never overwritten.
.\export.ps1 -Destination 'D:\AgentComputerLab'
# Optional: include original trial outputs, screenshots and reviews.
.\export.ps1 -Destination 'D:\AgentComputerLabWithReports' -IncludeReports
```

Export includes code, fixtures, bundled source, documentation and the results summary. It excludes `.env`, the private credential-filled `.env.example`, venvs, caches, vendor checkouts, nested Git/index data and the original-parent guard. `-IncludeReports` adds raw historical artifacts and their frozen generation sources. Export does not run tests or consume model credits.

You can also copy the folder manually. **Recreate `.venv`** at the new location; venvs are not portable. Use the public **`.env.template`** for a clean setup. The existing `.env` and `.env.example` are private local files; copy only the research credentials you need into the new `.env` to keep using your current provider.

## Setup

```powershell
Set-Location 'D:\AgentComputerLab'
.\setup.ps1
.venv\Scripts\python.exe lab.py check
```

Setup clones OpenBot at `4773ef6866544a497c2a33ed2475bb4aa1de0475`, installs `requirements.lock.txt`, builds both Docker images, creates a blank-key `.env` if missing and checks bundled source hashes. It preserves an existing `.env` and refuses a vendor checkout at a different revision. Setup does not call a model.

The image names retain `kareos-research-*` for compatibility; those names do not require KareOS. Two project copies can share images while creating different containers with independent state.

If PowerShell blocks scripts, a process-only invocation is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

## Configure inference

Edit this project's `.env`; keep credentials out of `.env.template`. Only the local `.env` and explicitly supported process environment variables are consulted. No parent environment file is loaded.

For the model used in the recorded generator experiment:

```dotenv
RESEARCH_PROVIDER=bedrock
RESEARCH_MODEL=in.anthropic.claude-haiku-4-5-20251001-v1:0
RESEARCH_AWS_REGION=ap-south-2
RESEARCH_BEDROCK_API_KEY=<your research key>
RESEARCH_TEMPERATURE=0.2
```

Alternatively leave the research key blank and set `RESEARCH_AWS_PROFILE` to an existing profile with access to your chosen model. Access/model availability are checked by actual provider requests. The research key takes precedence over supported legacy Bedrock bearer-key variables.

For an OpenAI-compatible provider, set `RESEARCH_PROVIDER=openai-compatible`, your explicit `RESEARCH_MODEL`, HTTPS `RESEARCH_BASE_URL` and `RESEARCH_API_KEY`. The adapter appends `/chat/completions`; include `/v1` in the base URL if required by your provider. The model must reliably emit the supplied JSON action contract.

Optional `RESEARCH_INPUT_PRICE` and `RESEARCH_OUTPUT_PRICE` are USD per million tokens. Blank values leave cost unknown. Missing configuration causes an error; there is no silent mock fallback.

## Run checks and tests

```powershell
# Includes real container/browser checks; no live model inference.
.venv\Scripts\python.exe -m pytest -q --basetemp .cache/pytest-temp
# Browser navigation, snapshots, clicks, arithmetic, files, isolation and teardown.
.venv\Scripts\python.exe lab.py smoke

# First paid comparison: 1 case x 1 repeat x 3 arms = 3 trials.
.venv\Scripts\python.exe lab.py run --protocol required --cases 1 --repeats 1
# Small comparison: 3 cases x 2 repeats x 3 arms = 18 trials.
.venv\Scripts\python.exe lab.py run --protocol required --cases 3 --repeats 2
# Expanded comparison: 12 cases x 3 repeats x 3 arms = 108 trials.
.venv\Scripts\python.exe lab.py run --protocol required --cases 12 --repeats 3
```

`required` forces A through search/fetch, B through structured retrieval and C through its browser to read both documents. B/C cannot bypass their interface. `--protocol offered` is a separate experiment with optional extra tools; inspect actual adoption before attributing effects to a computer. Keep the protocols separate.

Each run writes a new `reports/required-<timestamp>/` or `reports/live-<timestamp>/` directory: settings, all trial outputs/failures, prompts/responses, usage, tool traces, screenshots where available, `SUMMARY.md` and masked review forms. Arms share model, temperature, source content, output contract and budgets; interfaces differ. Run order is randomized. Default bounds are 16 model calls, 14 tool calls and a 300-second inference deadline; startup is separately recorded. Failures stay in the denominator.

Keyword coverage and registered citations are plumbing proxies. Review supported findings, material errors, missingness, usefulness and citation support against the source facts. Arrange qualified clinician review before calling a result clinical accuracy.

## Review and historical replay

```powershell
# RUN_NAME is a completed run folder name. Review can use model credits.
.venv\Scripts\python.exe deep_review_v2.py RUN_NAME
```

The replacement reviewer uses the explicit global Sonnet 4.5 profile coded in `deep_review_v2.py` and Bedrock transport. It does not automatically follow an OpenAI-compatible generator. Configure Bedrock access if using this reviewer. It hides arm/tool traces and verifies exact quoted/scalar evidence, but AI review can still miss errors. Each new run needs its own adjudication.

With raw reports exported, this rebuilds the **specific completed 108-trial report**, without model calls:

```powershell
.venv\Scripts\python.exe build_deep_report.py required-20261009-200529
```

Historical hashes are verified against that run's `frozen_sources/`, preserving the completed experiment while current code evolves. The builder is tailored to that run and retained manual AI adjudication; it is not a general accuracy scorer. Do not overwrite historical evidence or reuse adjudication scores for a new run.

## A computer for each agent

Today, each arm-C `Computer` owns a distinct ephemeral container, token, Chromium profile and workspace. Multiple instances can coexist without sharing browser state or scratch files. The trusted controller owns provisioning and teardown.

For KareOS, key sessions by `(tenant, user, encounter, agent, run)`. Allocate one computer per active agent session, preserve it through that agent's tool loop, and destroy it on completion, timeout, cancellation or error. Agents must not share profiles, cookies, mutable workspaces or service tokens. Shared read-only images and explicitly authorized evidence can be reused. Each agent gets its own system without requiring a physical machine or an always-running computer per registry entry.

```text
Scoped KareOS agent invocation
    -> allocate that agent's isolated computer session
    -> authorize and budget each tool action
    -> execute browser/workspace operation
    -> register source evidence and return observations
    -> produce validated specialist output
    -> destroy computer; retain authorized audit artifacts
```

A multi-agent session manager, cross-task persistence, visual model, production internet policy and general desktop/shell tools remain future work. Develop these here after baseline comparisons work. Start with two agents and state-isolation checks, then add a resource-bounded pool. Tool availability alone does not prove output improvement.

## Make changes and evaluate

1. Save a baseline with fixed cases, prompts, model, limits and review criteria.
2. Change one feature at a time: browser recovery, schema/missingness handling, tool ergonomics, then tasks that benefit from investigation. Record code/image/settings per run.
3. Add synthetic navigation, calculation and file tasks alongside clinical cases. Fix unsupported probability/missing-data handling in the shared model/schema before attributing it to computer access.
4. Keep source information and framing comparable. The current portal banner is a documented framing difference. Retain failures and reviewer uncertainty.
5. Compare correctness, unsupported claims, completion, evidence support, time, tokens and cost. Pair by case; repetitions are not independent patients.
6. Test agent-state separation, concurrency limits, cancellation, expired sessions and cleanup before scaling.

Edit `cases.json`, protocol files, `lab.py`, `computer.py`, `portal.py` and tests here. Keep `source_snapshot/` and its manifest frozen. To test a changed runtime contract, create a separately versioned snapshot/manifest rather than silently updating baseline hashes.

## Integrate into KareOS later

Bring back the reviewed adapter/contracts, session manager, policy and evaluation evidence. Wire optional computer actions into existing capability/scope checks and preserve KareOS's model router, validated output and evidence contracts. Do not copy `.env`, venvs, caches, vendor Git repositories or research reports into production runtime dependencies.

Preserve RDS metadata/authorization and private tenant-scoped S3 artifacts. Scratch files here contain synthetic data; there is no production patient-data path. The trusted gateway must restrict network/app access, budgets and evidence registration; agents cannot grant themselves capabilities. Start with one specialty behind a feature switch, compare it, then scale to a computer per active agent when results justify it.

## Project map

| Path | Purpose |
| --- | --- |
| `lab.py` | CLI, runtime adapters, providers, schedule and reports |
| `computer.py` | Container lifecycle, authenticated transport, tool policy |
| `portal.py`, `calculator.py`, `Dockerfile`, `start.sh` | Synthetic computer environment |
| `source_snapshot/` | Bundled hash-verified specialist; no parent imports |
| `cases.json`, `protocol*.json` | Cases and shared limits |
| `setup.ps1`, `export.ps1` | Setup and clean standalone export |
| `.env.template`, `requirements*.txt`, `pytest.ini` | Public configuration, dependencies and tests |
| `test_lab.py`, `test_standalone.py`, `smoke.py` | Runtime, portability, independent state and infrastructure checks |
| `deep_review*.py`, `build_deep_report.py` | AI audits and historical reporting |
| `reports/` | Generated evidence; summary included in default export |
| `RESEARCH_NOTES.md`, `IMPLEMENTATION.md` | Historical rationale and detailed implementation |
| `THIRD_PARTY_NOTICES.md` | Upstream attribution and license notice |

## Troubleshooting

- Docker unavailable/missing images: start Docker Desktop's Linux engine and rerun `setup.ps1`.
- Provider 401/403: verify key/profile, region and model permissions. Live failures are not replaced by mock answers. Throttle events are recorded.
- HTTP 409 on click: refresh the snapshot and use its current refs. Recovery can exhaust common budgets.
- Snapshot drift: restore the recorded source, not its hashes.
- After moving: `lab.py check` reports standalone mode and verifies local source hashes. Parent checks are not applicable. The original-parent guard is bound to the exact original path; no parent sources or Git are needed in standalone mode. Setup still needs Git to download OpenBot.
- After an interrupted run: inspect `docker ps -a --filter label=kareos.computer-research=pilot-v1`. Multiple project copies share that label; inspect names and remove only containers from the interrupted run.

Computers run non-root, network-disabled, resource-bounded, without host mounts or published ports. Provider credentials stay on the controller. Browser sandboxing inherits upstream image settings; this synthetic research setup is not validated production containment. Nothing here starts KareOS services, commits or pushes.
