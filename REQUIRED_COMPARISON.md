# Actual computer use versus retrieval without a computer

The earlier voluntary-adoption pilot gave the model a computer, but it chose existing search/fetch instead. The `required-route-v2.1` protocol tests actual browser use with equal source information.

## Design

Three fixed synthetic cases are each run twice in three arms, giving 18 investigations. Case order is randomized with seed 20261009. The configured model, temperature, specialist role, questions, two source documents, output contract and budgets are shared across arms. Document IDs are registered only after their content is retrieved. Every arm must read both documents before finalizing.

| Arm | Required evidence path |
|---|---|
| A: without computer | Original search/fetch over the synthetic patient and knowledge documents |
| B: structured control | Structured library listing and document reading; search/fetch disabled |
| C: with computer | Real OpenBot Chromium navigation, snapshots, clicks and page reading; search/fetch and structured shortcuts disabled |

The model selects its actions. The runner does not pre-navigate or automatically retrieve evidence for C. Each C investigation receives a fresh container with no external network, host mounts or published ports. The browser can reach only the container-local portal. Screenshot artifacts and actual actions are recorded. This is browser/DOM computer use; screenshots are not sent to the model for visual reasoning.

Requiring the retrieval route changes the experimental question. It compares these evidence-access workflows; it does not measure spontaneous adoption of an optional computer. A/B/C prompt differences describe the allowed tool interface, and their schemas expose the corresponding capabilities. All arms have the same requirement to read both documents. A remains a tool-using specialist, so "without computer" does not mean a tool-free chatbot.

## Measurements and interpretation

- Completion is a validated specialist output produced within the shared budgets after both sources are retrieved.
- Tool traces verify actual browser or structured-tool use, including denied actions that the agent can correct.
- Latency includes inference and tool execution. Total latency also includes computer creation and teardown. Provider throttling events are recorded; quota waits can affect timing.
- Input/output token usage comes from successful provider responses. Cost stays unknown when prices are unconfigured.
- Expected keyword coverage checks whether outputs mention the predefined fixture signals. This is an extraction proxy, not a clinical accuracy score.
- Registered citations establish that the source was retrieved. Their support for a claim, unsupported claims, and clinical usefulness require a qualified review. Review forms are blinded by arm.

These three simple synthetic cases cannot establish general clinical performance. Equal expected-signal coverage would show no measured benefit on this benchmark, even when C actually operates the browser. Faster or longer responses do not establish better reasoning. The structured control helps distinguish the effect of the browser interface from access to extra tools or information.

## Run and inspect

```powershell
Set-Location 'D:\Kraionyx AI\KareOS-V1\computer_research'
.venv\Scripts\python.exe -m pytest -q --basetemp .cache/pytest-temp
.venv\Scripts\python.exe lab.py run --protocol required --cases 3 --repeats 2
.venv\Scripts\python.exe lab.py check
```

Results are written to `reports/required-TIMESTAMP/`. Each `result.json` includes the retrieval mode, retrieved source IDs, actual tool trace, provider usage/errors, output and status. For blinded review, share only that run's `blinded-review/` directory, withholding the mapping and tool traces.

An initial required-route diagnostic run was interrupted after identifying a fatal handling bug for stale browser snapshot refs. That directory is retained as `reports/required-20261009-185702/`; it is not pooled with the comparison. The final protocol returns expected browser input errors (400/404/409/422) to the agent so it can refresh its snapshot and choose a corrective action. Other browser failures remain fatal. This mirrors baseline handling of invalid evidence selectors and duplicate searches. Unit checks verify both recovery and fatal failure behavior.

Current comparison results will be recorded in [reports/REQUIRED_RESULTS.md](reports/REQUIRED_RESULTS.md). All changes and artifacts remain inside `computer_research`; no parent files, commits or pushes are part of this experiment.
