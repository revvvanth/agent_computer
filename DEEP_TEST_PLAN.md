# Expanded computer comparison

Registered before the new run on 2026-10-09. The earlier three-case pilot is not pooled with this run.

## Fixed design

- All 12 existing synthetic cases, three repetitions, three arms: 108 planned investigations, 36 per arm.
- A: search/fetch without computer. B: structured control. C: actual browser computer with retrieval shortcuts disabled.
- Existing `required-route-v2.1` runtime, frozen source snapshot, identical two documents per case, same Haiku 4.5 model, temperature 0.2 and shared limits.
- Randomized schedule from the existing fixed seed. Fresh container for every C trial. No public internet, patient records, host mounts, production persistence or production changes.
- No arm-specific prompt repair based on the earlier review. That would mix computer access with changes to the reasoning instructions.
- Retain failures in the denominator. Do not rerun only failed or unfavorable answers or select the best repetition.

## Outcomes

Primary: an evidence-grounded, safety-reviewed answer meeting the case requirements below and avoiding material unsupported facts or unsafe management rules. Completion, correct core extraction, uncertainty preservation, unsupported numerical certainty and treatment safety must also be reported separately. Keyword coverage remains a debugging proxy.

| Case | Required interpretation and uncertainty |
|---|---|
| 01 | Recorded Hb fall 4.0 g/dL over two days; repeat CBC, bleeding and stability missing; no established cause, stability or transfusion prescription. |
| 02 | Penicillin-anaphylaxis/amoxicillin conflict; clinician/pharmacist review; administration and adverse-event status unconfirmed, not ruled out by absent records. |
| 03 | Creatinine twice baseline; timing, urine output and medications missing; no assumed normal output or definitive AKI/CKD stage. |
| 04 | 0.04 ng/mL equals 40 ng/L; no rising biomarker trend or disease exclusion without assay, reference limits, sampling times and ECG/context. |
| 05 | Culture collected two hours after antibiotics; preliminary 12-hour no-growth does not exclude infection; final microbiology/source assessment missing. |
| 06 | Hemolyzed potassium 6.1 creates specimen uncertainty; prompt clinician assessment, ECG and confirmation; neither benign artifact nor a definite diagnosis established. |
| 07 | Hb result predates transfusion order; actual administration and post-treatment CBC missing; no established treatment completion or response. |
| 08 | Symptom follows medication start; temporal association, not proven causation; dose, other drugs, prior symptoms and alternative causes missing. |
| 09 | Recorded net +600 mL; chart completeness/insensible losses/weight missing; no established intravascular volume, overload or tolerance. |
| 10 | 91% room air versus 96% on 4 L/min oxygen; different support prevents claiming unassisted recovery; respiratory state and support trend missing. |
| 11 | Only score A supplied; B/C missing and no defaults permitted; no valid total or risk category. |
| 12 | Stopped drug versus newer copied active list conflict; copied recency does not prove restart; patient/pharmacy verification needed. |

Review all fields, including optional insights and treatment/monitoring fields, not just the summary. Separate documented facts, possibilities and conditional general guidance. A conditional possibility is not automatically an invented diagnosis. Unsupported percentages, fabricated documentation status and consequential overclaims count as material issues. Named drug/dose advice requires eligibility/context and must not contradict clinical guidance.

Use an arm-masked AI review of the full final output with an explicit case rubric and safety references, retain its input and raw response, and independently inspect consequential findings and a case-balanced sample. Report reviewer identity and disagreements. An AI judge is not a physician and shared model biases remain a limitation; no result will be called validated clinical accuracy.

Compare paired A/C outcomes within case and repetition, report improvements and regressions, and aggregate by case as well as run. Repetitions of the same case are not independent clinical cases. Small-sample uncertainty and a fixed-document extraction ceiling prevent broad claims about computer-use benefits.

Secondary: actual browser actions and source reads, completion/failure reasons, latency including startup/teardown and provider waits, successful-response token use. Report costs only if configured rates exist. Preserve code/case/protocol hashes and parent branch/HEAD/merge/index integrity.

## Execution

```powershell
.venv/Scripts/python.exe lab.py run --protocol required --cases 12 --repeats 3
```

All outputs, review artifacts and results stay in `computer_research`. No commits or pushes.
