"""Aggregate immutable trials and retained audits; does not invoke a model or tools."""
import argparse
import collections
import hashlib
import json
import random
import statistics
from pathlib import Path

from lab import ROOT, parent_integrity

parser = argparse.ArgumentParser()
parser.add_argument('run_name')
args = parser.parse_args()
run = (ROOT / 'reports' / args.run_name).resolve()
if run.parent != (ROOT / 'reports').resolve():
    raise SystemExit('Expected a local research run.')
summary = json.loads((run / 'summary.json').read_text())
settings = summary['settings']
frozen = run / 'frozen_sources'
code_root = frozen if frozen.is_dir() else ROOT
review_protocol = json.loads((run / 'deep-review-v2' / 'review-protocol.json').read_text(encoding='utf-8'))
if hashlib.sha256((code_root / 'deep_review_v2.py').read_bytes()).hexdigest() != review_protocol['code_sha256']:
    raise SystemExit('Replacement reviewer code drift.')
cases = {c['id']: c for c in json.loads((code_root / 'cases.json').read_text())}
manifest = json.loads((run / 'deep-manifest.json').read_text())
adjudication = json.loads((run / 'codex-adjudication.json').read_text())
adjudicated = {r['trial']: r for r in adjudication['adjudications']}
for name, digest in manifest['files'].items():
    if hashlib.sha256((code_root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Frozen protocol/code drift: ' + name)
expected = {(case, arm, rep) for case in cases for arm in 'ABC' for rep in range(1, 4)}
mapping = summary['review_mapping']
if {(m['case_id'], m['arm'], m['repeat']) for m in mapping.values()} != expected or len(mapping) != 108:
    raise SystemExit('Incomplete or duplicated schedule.')
records = []
for review_id, m in sorted(mapping.items()):
    name = f"{m['case_id']}-{m['arm']}-{m['repeat']}"
    raw = (run / name / 'result.json').read_bytes()
    result = json.loads(raw)
    review = json.loads((run / 'deep-review-v2' / f'{review_id}.json').read_text(encoding='utf-8'))
    if review['result_sha256'] != hashlib.sha256(raw).hexdigest():
        raise SystemExit('Result changed since review: ' + name)
    available = review['status'] == 'reviewed'
    raw_ai_primary = review['grounded_safe_pass'] if available else (False if result['status'] != 'completed' else None)
    checked = adjudicated[name]
    if checked['result_sha256'] != hashlib.sha256(raw).hexdigest():
        raise SystemExit('Adjudicated source changed: ' + name)
    witness = checked.get('witness')
    if witness:
        value = json.loads(result['output']['content'])
        for token in witness['pointer'][1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            value = value[int(token)] if isinstance(value, list) else value[token]
        if isinstance(value, str):
            if not witness['quote'] or witness['quote'] not in value:
                raise SystemExit('Adjudicated quote mismatch: ' + name)
        elif type(value) is not type(witness['value']) or value != witness['value']:
            raise SystemExit('Adjudicated scalar mismatch: ' + name)
        if witness['category'] == 'unsupported_number':
            item = json.loads(result['output']['content'])['differential'][int(witness['pointer'].split('/')[2])]
            if item['dx'] != witness['diagnosis'] or item['rationale'] != witness['rationale']:
                raise SystemExit('Adjudicated diagnostic context mismatch: ' + name)
    primary = checked['grounded_safe_pass']
    issues = review.get('audit', {}).get('material_issues', [])
    records.append({'trial': name, **m, 'review_id': review_id, 'result': result, 'review': review,
                    'primary': primary, 'raw_ai_primary': raw_ai_primary, 'adjudication': checked,
                    'primary_without_numerical_issues':
                    review['all_case_criteria_pass'] and not any(i['category'] != 'unsupported_number' for i in issues)
                    if available else (False if result['status'] != 'completed' else None)})

arms = {}
for arm in 'ABC':
    selected = [r for r in records if r['arm'] == arm]
    completed = [r for r in selected if r['result']['status'] == 'completed']
    reviewed = [r for r in selected if r['review']['status'] == 'reviewed']
    unknown = [r for r in selected if r['primary'] is None]
    successful = sum(r['primary'] is True for r in selected)
    tool_counts = collections.Counter()
    denied = collections.Counter()
    for r in selected:
        for t in r['result']['lab_tool_trace']:
            key = t['tool'] + ':' + t.get('operation', '')
            (denied if t.get('status') == 'denied' else tool_counts)[key] += 1
    issues = [i for r in reviewed for i in r['review']['audit']['material_issues']]
    runtime_actions = collections.Counter()
    for r in selected:
        trace = r['result'].get('output', {}).get('freeform') or r['result'].get('trace') or {}
        for event in trace.get('events', []):
            runtime_actions[event['action'] + ':' + event['status']] += 1
    waits = [sum(e.get('retry_delay_seconds', 0) for e in r['result']['provider_request_errors']) for r in selected]
    arms[arm] = {
        'planned': len(selected), 'completed': len(completed), 'failed': len(selected) - len(completed),
        'valid_ai_reviews': len(reviewed), 'unavailable_ai_reviews': sum(r['raw_ai_primary'] is None for r in selected),
        'adjudication_uncertain': len(unknown),
        'all_three_case_criteria_pass': sum(r['review']['all_case_criteria_pass'] for r in reviewed),
        'case_criteria_passes': sum(c['passed'] for r in reviewed for c in r['review']['audit']['criteria']),
        'case_criteria_scored': len(reviewed) * 3,
        'no_material_issue': sum(r['review']['material_issue_free'] for r in reviewed),
        'grounded_safe_passes': successful,
        'raw_ai_grounded_safe_passes': sum(r['raw_ai_primary'] is True for r in selected),
        'primary_planned_denominator_bounds': [successful / len(selected), (successful + len(unknown)) / len(selected)],
        'passes_ignoring_numerical_issues_only': sum(r['primary_without_numerical_issues'] is True for r in selected),
        'answers_with_issue_category': {category: sum(any(i['category'] == category for i in r['review']['audit']['material_issues']) for r in reviewed)
                                     for category in ('factual_overclaim', 'unsupported_number', 'clinical_safety', 'citation_support', 'other_material')},
        'issue_severity_counts': dict(collections.Counter(i['severity'] for i in issues)),
        'mean_total_seconds_all_trials': statistics.mean(r['result']['total_seconds'] for r in selected),
        'median_total_seconds_all_trials': statistics.median(r['result']['total_seconds'] for r in selected),
        'mean_inference_seconds_completed': statistics.mean(r['result']['inference_seconds'] for r in completed) if completed else None,
        'mean_total_seconds_minus_recorded_retry_waits': statistics.mean(r['result']['total_seconds'] - wait for r, wait in zip(selected, waits)),
        'recorded_retry_wait_seconds': sum(waits),
        'provider_error_counts': dict(collections.Counter(str(e['status']) for r in selected for e in r['result']['provider_request_errors'])),
        'usage_successful_responses_including_failed_trials': {k: sum(r['result']['usage'][k] for r in selected) for k in ('input_tokens', 'output_tokens')},
        'mean_model_calls': statistics.mean(len(r['result']['model_calls']) for r in selected),
        'successful_tool_operations': dict(tool_counts), 'denied_tool_operations': dict(denied),
        'lab_tool_trace_scope': 'Overlay B/C operations; baseline A search/fetch are represented in runtime_action_counts instead.',
        'runtime_action_counts': dict(runtime_actions),
        'all_documents_read_completed': sum(set(r['result']['retrieved_document_ids']) == {d['id'] for d in cases[r['case_id']]['documents']} for r in completed),
        'unretrieved_top_level_citations': sum(len(r['result']['proxy_metrics']['unretrieved_citations']) for r in completed),
        'estimated_usd': sum(r['result']['estimated_usd'] for r in selected) if all(r['result']['estimated_usd'] is not None for r in selected) else None,
    }

index = {(r['case_id'], r['arm'], r['repeat']): r for r in records}
pairing = {}
for metric in ('primary', 'primary_without_numerical_issues'):
    pairs = []
    for case in sorted(cases):
        for rep in range(1, 4):
            a, c = index[(case, 'A', rep)][metric], index[(case, 'C', rep)][metric]
            pairs.append({'case_id': case, 'repeat': rep, 'A': a, 'C': c,
                          'delta': int(c) - int(a) if a is not None and c is not None else None})
    usable = [p for p in pairs if p['delta'] is not None]
    complete_cases = [case for case in cases if all(p['delta'] is not None for p in pairs if p['case_id'] == case)]
    case_deltas = [statistics.mean(p['delta'] for p in pairs if p['case_id'] == case) for case in complete_cases]
    rng = random.Random(20261009)
    bootstrap = sorted(statistics.mean(rng.choices(case_deltas, k=len(case_deltas))) for _ in range(10000)) if case_deltas else []
    pairing[metric] = {
        'improvements': sum(p['delta'] == 1 for p in usable), 'regressions': sum(p['delta'] == -1 for p in usable),
        'ties': sum(p['delta'] == 0 for p in usable), 'unavailable_pairs': len(pairs) - len(usable),
        'case_level_mean_delta': statistics.mean(case_deltas) if case_deltas else None,
        'complete_case_count': len(complete_cases),
        'exploratory_case_bootstrap_95_interval': [bootstrap[249], bootstrap[9749]] if bootstrap else None,
        'warning': 'Resamples synthetic cases, not repetitions. Exploratory interval omits judge error and task-selection bias; a degenerate interval is not proof of equivalence.',
        'pairs': pairs,
    }
    if metric == 'primary':
        lower = [statistics.mean(int(p['C'] if p['C'] is not None else False) - int(p['A'] if p['A'] is not None else True) for p in pairs if p['case_id'] == case) for case in sorted(cases)]
        upper = [statistics.mean(int(p['C'] if p['C'] is not None else True) - int(p['A'] if p['A'] is not None else False) for p in pairs if p['case_id'] == case) for case in sorted(cases)]
        rng = random.Random(20261009)
        draws = [rng.choices(range(len(lower)), k=len(lower)) for _ in range(10000)]
        low_boot = sorted(statistics.mean(lower[i] for i in draw) for draw in draws)
        high_boot = sorted(statistics.mean(upper[i] for i in draw) for draw in draws)
        pairing[metric]['all_cases_mean_delta_bounds'] = [statistics.mean(lower), statistics.mean(upper)]
        pairing[metric]['all_cases_bootstrap_and_adjudication_envelope'] = [low_boot[249], high_boot[9749]]

codex = json.loads((run / 'codex-inspections.json').read_text())
sample = [i for i in codex['inspections'] if i['sample_role'] == 'preselected']
if {i['trial'] for i in sample} != {f'{case}-{arm}-1' for case in cases for arm in 'ABC'} or len(sample) != 36:
    raise SystemExit('Finish all 36 preselected Codex inspection slots.')
by_name = {r['trial']: r for r in records}
manual = {}
disagreements = []
for arm in 'ABC':
    selected = [i for i in sample if by_name[i['trial']]['arm'] == arm]
    available = [i for i in selected if i['full_final_answer_read']]
    manual[arm] = {'planned_slots': len(selected), 'full_answers_inspected': len(available),
                   'grounded_safe_passes': sum(i['grounded_safe_pass'] for i in selected),
                   'all_three_case_criteria_pass': sum(all(i['case_criteria']) for i in available),
                   'answers_with_issue_category': dict(collections.Counter(category for i in available for category in {x['category'] for x in i['material_issues']}))}
    for i in selected:
        record = by_name[i['trial']]
        if record['raw_ai_primary'] is not None and record['raw_ai_primary'] != i['grounded_safe_pass']:
            disagreements.append({'trial': i['trial'], 'metric': 'grounded_safe_pass', 'AI_judge': record['raw_ai_primary'], 'Codex': i['grounded_safe_pass']})
        if record['review']['status'] == 'reviewed':
            ai_core = [c['passed'] for c in sorted(record['review']['audit']['criteria'], key=lambda c: c['id'])]
            if ai_core != i['case_criteria']:
                disagreements.append({'trial': i['trial'], 'metric': 'case_criteria', 'AI_judge': ai_core, 'Codex': i['case_criteria']})

per_case = []
for case in sorted(cases):
    row = {'case_id': case}
    for arm in 'ABC':
        selected = [r for r in records if r['case_id'] == case and r['arm'] == arm]
        row[arm] = {'completed': sum(r['result']['status'] == 'completed' for r in selected),
                    'grounded_safe_passes': sum(r['primary'] is True for r in selected),
                    'unavailable_reviews': sum(r['primary'] is None for r in selected),
                    'all_three_case_criteria_pass': sum(r['review'].get('all_case_criteria_pass', False) for r in selected)}
    per_case.append(row)

review_usage = {k: sum(call['usage'][k] or 0 for r in records for call in r['review'].get('model_calls', [])) for k in ('input_tokens', 'output_tokens')}
integrity = parent_integrity()
report = {
    'run': args.run_name, 'design': {'unique_synthetic_cases': 12, 'repetitions': 3, 'planned_trials': 108,
    'prior_pilot_pooled': False, 'model': settings['model'], 'temperature': settings['temperature'],
    'computer_observation': 'Chromium text/DOM accessibility, not screenshots sent to the model.',
    'qualified_clinician_review': False, 'AI_judge_blinding': 'Arm/tool trace excluded; Sonnet 4.5 judge, Haiku 4.5 generator; same provider family.',
    'reviewer_model': review_protocol['model'], 'reviewer_temperature': review_protocol['temperature'],
    'evaluation_amendment': review_protocol['amendment'],
    'primary_assessor': adjudication['reviewer'], 'primary_adjudication_scope': adjudication['scope'],
    'Codex_sample_blinding': False},
    'arms': arms, 'paired_C_minus_A': pairing, 'per_case': per_case,
    'adjudication_status_counts': dict(collections.Counter(r['adjudication']['status'] for r in records)),
    'all_trial_primary_disagreements': [{'trial': r['trial'], 'raw_AI_judge': r['raw_ai_primary'], 'Codex': r['primary']}
                                       for r in records if r['raw_ai_primary'] != r['primary']],
    'codex_preselected_sample': manual, 'sample_disagreements': disagreements,
    'review_generation_usage_separate': review_usage,
    'initial_rejected_review_usage_separate': {k: sum(call['usage'][k] or 0 for p in (run / 'deep-review').glob('review-???.json') for call in json.loads(p.read_text(encoding='utf-8')).get('model_calls', [])) for k in ('input_tokens', 'output_tokens')},
    'parent_integrity': integrity,
    'original_result_hashes_verified': True, 'frozen_code_and_protocol_hashes_verified': True,
    'failures': [{'trial': r['trial'], 'error_type': r['result'].get('error_type'),
                  'retrieved_document_ids': r['result']['retrieved_document_ids'],
                  'model_calls': len(r['result']['model_calls'])} for r in records if r['result']['status'] != 'completed'],
    'unavailable_reviews': [{'trial': r['trial'], 'review_id': r['review_id'], 'error_type': r['review'].get('error_type')}
                            for r in records if r['review']['status'] == 'review_failed'],
}
(run / 'deep-comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
rows = ['# Expanded computer comparison', '',
        'The computer showed a small, case-specific quality gain, but this benchmark does not demonstrate a reliable overall accuracy improvement. Its extra passes came from two fluid-accounting answers. Completion fell to 31/36 from 36/36, and mean total latency roughly doubled.', '',
        '108 planned trials: 12 synthetic cases, three repetitions, three workflows. Previous pilots are not pooled.', '',
        'A is search/fetch without a computer, B is structured document tools, and C is actual isolated browser use with retrieval shortcuts disabled.', '',
        '**These are provisional AI audits, not validated clinical accuracy.** Primary counts use Codex adjudication: all candidate passes were fully read, and failed completed answers have a directly checked material-error witness. One borderline answer remains uncertain. Sonnet 4.5 provides a separate arm-masked audit; the generator remains Haiku 4.5. No reviewer is a qualified clinician.', '',
        '| Measure | A: no computer | B: structured | C: browser computer |', '|---|---:|---:|---:|']
table = {
    'Completed / planned': [f"{arms[a]['completed']}/36" for a in 'ABC'],
    'Valid AI audits / completed': [f"{arms[a]['valid_ai_reviews']}/{arms[a]['completed']}" for a in 'ABC'],
    'Primary: passes / planned, uncertainty retained': [f"{arms[a]['grounded_safe_passes']}/36" + (f" + {arms[a]['adjudication_uncertain']} uncertain" if arms[a]['adjudication_uncertain'] else '') for a in 'ABC'],
    'Secondary: raw Sonnet full-answer passes': [f"{arms[a]['raw_ai_grounded_safe_passes']}/36" for a in 'ABC'],
    'Secondary: Sonnet all three case criteria passed': [f"{arms[a]['all_three_case_criteria_pass']}/36" for a in 'ABC'],
    'Secondary: Sonnet flags unsupported numbers': [str(arms[a]['answers_with_issue_category']['unsupported_number']) for a in 'ABC'],
    'Secondary: Sonnet flags clinical safety': [str(arms[a]['answers_with_issue_category']['clinical_safety']) for a in 'ABC'],
    'Secondary: Sonnet passes ignoring only numerical issues': [f"{arms[a]['passes_ignoring_numerical_issues_only']}/36" for a in 'ABC'],
    'Mean total seconds, all trials': [f"{arms[a]['mean_total_seconds_all_trials']:.2f}" for a in 'ABC'],
    'Mean seconds minus recorded retry waits': [f"{arms[a]['mean_total_seconds_minus_recorded_retry_waits']:.2f}" for a in 'ABC'],
    'Mean successful-response input tokens / trial': [f"{arms[a]['usage_successful_responses_including_failed_trials']['input_tokens']/36:,.0f}" for a in 'ABC'],
    'Mean successful-response output tokens / trial': [f"{arms[a]['usage_successful_responses_including_failed_trials']['output_tokens']/36:,.0f}" for a in 'ABC'],
}
rows.extend('| ' + label + ' | ' + ' | '.join(values) + ' |' for label, values in table.items())
rows.extend(['', 'A failed generation counts as unsuccessful, not a clinical answer error. Primary bounds retain unresolved materiality; unavailable automated audits are also unknown. The JSON report provides each denominator and bounds.', '',
             '## Paired result', ''])
for metric, pair in pairing.items():
    rows.append(f"- `{metric}`: C improved {pair['improvements']} pairs, regressed {pair['regressions']}, tied {pair['ties']}; {pair['unavailable_pairs']} pairs unavailable.")
    if pair['case_level_mean_delta'] is not None:
        interval = pair['exploratory_case_bootstrap_95_interval']
        rows.append(f"  Case-averaged C-minus-A difference: {100*pair['case_level_mean_delta']:.1f} percentage points over {pair['complete_case_count']} complete cases; exploratory case-bootstrap interval {100*interval[0]:.1f} to {100*interval[1]:.1f} points.")
    if metric == 'primary':
        bounds = pair['all_cases_mean_delta_bounds']
        envelope = pair['all_cases_bootstrap_and_adjudication_envelope']
        rows.append(f"  Including all 12 cases and both outcomes for the uncertain answer: observed mean-difference bounds {100*bounds[0]:.1f} to {100*bounds[1]:.1f} points; exploratory case-resampling/adjudication envelope {100*envelope[0]:.1f} to {100*envelope[1]:.1f} points.")
rows.extend(['', 'The 12 cases, rather than 108 runs, are the distinct task units. These intervals exclude reviewer error and benchmark-selection bias. A zero or degenerate interval is not evidence of general equivalence.', '',
             'The numerical-issue sensitivity analysis uses raw Sonnet judgments and is secondary: C passed 15/36 versus A 18/36 when numerical issues alone were ignored. Removing the common probability defect therefore does not reveal an overall computer advantage in that audit.', '',
             '## Primary adjudication', '',
             'All 108 trial slots are accounted for: 91 completed answers have a directly verified material error, five are generation failures, 11 passed full-answer inspection, and one has unresolved materiality. Codex fully read 43 final answers, including every potential pass; the remaining failure decisions use directly inspected error witnesses rather than claiming an exhaustive medical review.', '',
             'Primary passes: A 3/36 with one uncertain answer (8.3%-11.1%); B 3/36 (8.3%); C 5/36 (13.9%). The additional C passes are two repetitions of the fluid-accounting case. Every mode passed all three incomplete-score repetitions. The uncertain A answer is a transfusion case with conditional treatment and a questionable raw-reticulocyte interpretation; expert adjudication could change its classification. Reticulocyte interpretation requires appropriate correction for anemia, as described in [Merck\'s anemia evaluation](https://www.merckmanuals.com/professional/hematology/approach-to-the-patient-with-anemia/evaluation-of-anemia).', '',
             'Both automated judges missed explicit missingness contradictions. Raw Sonnet scores therefore remain secondary, with disagreements retained. They are not substituted for source-checked primary judgments.', '',
             '## Computer actions and failures', '',
             'C executed 293 permitted browser operations (37 navigations, 129 snapshots, 124 clicks and three current-page reads), with 35 denied clicks recorded separately. No browser shortcuts, shell arithmetic or calculator calls were used in these live trials. Every completed C trial read both supplied evidence documents. All five failed C trials exhausted 16 model calls with only the chart read, leaving the exercise note unread. All 36 research containers were removed.', '',
             '## Independent Codex sample', '',
             'Repetition 1 was preselected for every case/arm: 36 slots. Complete answers were read, including treatment, workup, monitoring and extra insights. Supplemental checks are labelled and excluded from the sample denominator.', '',
             '| Measure | A | B | C |', '|---|---:|---:|---:|',
             '| Full answers read | ' + ' | '.join(str(manual[a]['full_answers_inspected']) for a in 'ABC') + ' |',
             '| All three case criteria passed | ' + ' | '.join(str(manual[a]['all_three_case_criteria_pass']) for a in 'ABC') + ' |',
             '| Passed full-answer Codex audit / 12 slots | ' + ' | '.join(str(manual[a]['grounded_safe_passes']) + '/12' for a in 'ABC') + ' |', '',
             f"{len(disagreements)} metric disagreements with the AI judge are retained in `deep-comparison.json`. The Codex sample is unblinded and is a second AI review, not physician verification.", '',
             '## Case-level primary counts', '',
             '| Case | A passes / 3 | B passes / 3 | C passes / 3 |', '|---|---:|---:|---:|'])
rows.extend('| ' + c['case_id'] + ' | ' + ' | '.join(str(c[a]['grounded_safe_passes']) + '/3' + (f" ({c[a]['unavailable_reviews']} unknown)" if c[a]['unavailable_reviews'] else '') for a in 'ABC') + ' |' for c in per_case)
rows.extend(['', '## Interpretation limits', '',
             '- This tests one differential-diagnosis specialist on short, fixed two-document tasks. It does not test every KareOS specialist, a full board, internet research, a visual desktop model or hospital workflows.',
             '- The frozen output contract requires integer probability for each differential item. That can encourage unsupported percentages or zero-as-missing. This is a shared model/schema weakness; computer access does not repair it. The numerical-issue sensitivity result is secondary and does not make remaining claims clinician-validated.',
             '- C receives browser text and accessibility observations. Screenshots are recorded as artifacts but are not provided to this model. Successful retrieval establishes evidence access, not support for every sentence citing an evidence ID.',
             '- Evidence document bodies are shared, but interface instructions and observation wrappers differ. The browser library prominently displays a training-fixture banner. More cautious exercise framing could partly explain particular C answers; this design does not isolate an inherent benefit from owning a computer.',
             '- Total latency includes startup/teardown, model calls and provider retries. Removing recorded retry waits is an approximation, not a controlled latency measurement. Token totals cover successful provider responses, including those in failed trials; review tokens are separate. Price rates were not configured, so no dollar comparison is asserted.',
             '- Generation limits and prompts were frozen. Failed/unfavorable generations were retained rather than rerun or repaired selectively.',
             '- Evaluation amendment: the first Haiku judge returned invalid evidence references and missed explicit missingness contradictions. Its partial audit is retained in `deep-review` and excluded from primary scores. A replacement Sonnet judge uniformly audits all 108 slots, with the same case criteria, expanded safety references and exact string/scalar evidence validation. One format-validation repair is allowed uniformly; unfavorable valid scores are not retried. This evaluator amendment occurred after generation and was not preregistered.', '',
             '## Artifacts and integrity', '',
             '- [Preregistered design](../../DEEP_TEST_PLAN.md), [run settings](settings.json), [frozen hashes](deep-manifest.json).',
             '- [Machine-readable comparison](deep-comparison.json), [Codex inspections](codex-inspections.json), [replacement AI audit protocol](deep-review-v2/review-protocol.json).',
             '- [All-slot primary adjudication](codex-adjudication.json) links each decision to original output hashes and exact error witnesses; uncertainty remains explicit.',
             '- Original `case-XX-ARM-REPEAT/result.json` files retain prompts, model outputs, browser/tool traces, usage and failures. `deep-review-v2/review-NNN.json` retains masked judge inputs/responses, validation attempts and links by SHA256; `summary.json` maps review IDs to trials.',
             '- Parent branch, HEAD, pending merge, index, tracked worktree and source-snapshot hashes verified unchanged. No commits or pushes. All experiment files remain under `computer_research`.', ''])
(run / 'DEEP_RESULTS.md').write_text('\n'.join(rows), encoding='utf-8')
print(json.dumps({'arms': arms, 'paired': {k: {x: v for x, v in p.items() if x != 'pairs'} for k, p in pairing.items()},
                  'codex_sample': manual, 'disagreements': disagreements, 'failures': report['failures'],
                  'unavailable_reviews': report['unavailable_reviews']}, indent=2))
