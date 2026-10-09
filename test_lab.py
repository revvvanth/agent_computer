"""Contract/budget/isolation checks. Scripted responses test plumbing, not intelligence."""
import asyncio
import json
from pathlib import Path

import pytest

from calculator import calculate
from computer import Computer, ORIGIN, ROOT, docker, safe_path
from lab import LabRuntime, Limits, Scope, parent_integrity


def finalized(references):
    return {'action': 'finalize', 'result': {
        'schema_version': '1.0', 'voice_summary': 'Scripted plumbing check.',
        'clinical_assessment': 'Synthetic data only. Clinician assessment required.',
        'key_findings': [], 'differential': [], 'must_not_miss': [], 'missing_data': [],
        'stat_workup': [], 'routine_workup': [], 'treatment': [],
        'monitoring': {'frequency': 'Not specified', 'escalate_if': [], 'targets': []},
        'confidence': 'low', 'confidence_reasoning': 'Scripted test is not a clinical opinion.',
        'evidence_references': references, 'beyond_baseline': []}}


class ScriptedModel:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = 0

    async def complete(self, **_):
        self.calls += 1
        return json.dumps(next(self.actions))


def scope(case):
    return Scope(tenant_id='synthetic-lab', user_id='researcher', encounter_id=case['id'],
                 document_ids=tuple(d['id'] for d in case['documents'] if d['corpus'] == 'patient'))


@pytest.mark.parametrize('expression,expected', [('1800 - 1200', 600), ('0.04 * 1000', 40), ('(2 - 1) / 1 * 100', 100)])
def test_shared_arithmetic(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize('expression', ['__import__("os").getcwd()', '2**100000', '1/0', '1e999', 'True + 1'])
def test_calculator_rejects_unsafe_or_unbounded_inputs(expression):
    with pytest.raises((ValueError, ZeroDivisionError)):
        calculate(expression)


@pytest.mark.parametrize('path', ['../secret.txt', '/etc/passwd', 'a/b.txt', 'note.txt;echo secret'])
def test_workspace_path_boundary(path):
    with pytest.raises(ValueError):
        safe_path(path)


@pytest.mark.parametrize('arm', ['A', 'B', 'C'])
def test_specialist_contract_and_source_registration(arm, tmp_path):
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    docs = case['documents']
    if arm == 'A':
        actions = [{'action': 'search', 'corpus': corpus, 'query': 'synthetic hemoglobin trend', 'top_k': 8}
                   for corpus in ('patient', 'knowledge')]
    elif arm == 'B':
        actions = [{'action': 'structured', 'operation': 'document', 'document_id': doc['id']} for doc in docs]
        actions.append({'action': 'structured', 'operation': 'calculate', 'expression': '12 - 8'})
    else:
        actions = [{'action': 'computer', 'operation': 'navigate', 'url': ORIGIN + '/documents/' + doc['id']} for doc in docs]
        actions.append({'action': 'computer', 'operation': 'calculate', 'expression': '12 - 8'})
    actions.append(finalized([doc['id'] for doc in docs]))
    model = ScriptedModel(actions)
    computer = Computer(docs, tmp_path / 'computer') if arm == 'C' else None
    if computer:
        computer.__enter__()
    try:
        runtime = LabRuntime(arm, docs, model, Limits(max_depth=0, max_children=0, max_sessions=1), computer)
        result = asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
        assert result['status'] == 'completed'
        assert result['data']['evidence_references'] == [doc['id'] for doc in docs]
        assert set(runtime.gateway._items) == {doc['id'] for doc in docs}
        assert result['freeform']['usage']['sessions'] == 1
        assert result['freeform']['usage']['model_calls'] == len(actions)
        if arm != 'A':
            assert runtime.lab_trace[-1]['result']['value'] == 4
    finally:
        if computer:
            computer.close()


def test_unread_citation_is_rejected():
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    # First citation denied; second finalize uses no fabricated reference.
    runtime = LabRuntime('A', case['documents'], ScriptedModel([finalized(['c01-chart']), finalized([])]), Limits())
    result = asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
    assert result['data']['evidence_references'] == []
    assert any(event['status'] == 'denied' for event in result['freeform']['events'])


def test_arm_c_cannot_use_structured_shortcut():
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    model = ScriptedModel([{'action': 'structured', 'operation': 'document', 'document_id': 'c01-chart'}, finalized([])])
    runtime = LabRuntime('C', case['documents'], model, Limits())
    result = asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
    assert not runtime.gateway._items
    assert any(event['status'] == 'denied' for event in result['freeform']['events'])


def test_tool_budget_applies_to_extra_tools():
    from agents.freeform.contracts import FreeFormExecutionError
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    model = ScriptedModel([{'action': 'structured', 'operation': 'documents'}, finalized([])])
    runtime = LabRuntime('B', case['documents'], model, Limits(max_tools=0))
    with pytest.raises(FreeFormExecutionError) as error:
        asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
    assert error.value.error_type == 'ResourceLimited'


def test_incomplete_scores_do_not_import_production_calculator():
    import sys
    case = json.loads((ROOT / 'cases.json').read_text())[10]
    model = ScriptedModel([{'action': 'calculate_clinical_scores'}, finalized([])])
    runtime = LabRuntime('A', case['documents'], model, Limits())
    asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
    assert 'agents.cdss.calculator_tool' not in sys.modules
    assert 'unified_backend' not in sys.modules


def test_parent_repo_and_snapshot_untouched():
    integrity = parent_integrity()
    assert integrity['snapshot_hashes_match']
    if integrity['parent_guard_active']:
        assert integrity['parent_index_unchanged']
    else:
        assert integrity['mode'] == 'standalone'
        assert integrity['parent_index_unchanged'] is None


@pytest.mark.parametrize('operation', ['navigate', 'click', 'calculate'])
def test_missing_computer_arguments_rejected_before_execution(operation):
    from lab import ExtraAction
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtraAction.model_validate({'action': 'computer', 'operation': operation})


def test_bedrock_api_key_transport_does_not_need_aws_profile(monkeypatch):
    import httpx
    from lab import LiveModel
    requests = []

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            'output': {'message': {'content': [{'text': '{"action":"revise","note":"test"}'}]}},
            'usage': {'inputTokens': 11, 'outputTokens': 7}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **options: original_client(transport=httpx.MockTransport(respond), **options))
    model = LiveModel({'RESEARCH_PROVIDER': 'bedrock', 'RESEARCH_MODEL': 'in.anthropic.test-v1:0',
                       'RESEARCH_AWS_REGION': 'ap-south-2', 'BEDROCK_API_KEY': 'synthetic-test-token'})
    result = asyncio.run(model.complete(system='system', user='user', max_tokens=512, timeout=5))
    assert json.loads(result)['action'] == 'revise'
    assert requests[0].headers['authorization'] == 'Bearer synthetic-test-token'
    assert requests[0].url.host == 'bedrock-runtime.ap-south-2.amazonaws.com'
    assert json.loads(requests[0].content)['inferenceConfig']['maxTokens'] == 512
    assert model.calls[0]['usage'] == {'input_tokens': 11, 'output_tokens': 7}
    assert 'synthetic-test-token' not in json.dumps(model.calls)


def test_research_bedrock_key_overrides_application_key():
    from lab import LiveModel
    model = LiveModel({'RESEARCH_PROVIDER': 'bedrock', 'RESEARCH_MODEL': 'synthetic-model',
                       'RESEARCH_BEDROCK_API_KEY': 'synthetic-research-key', 'BEDROCK_API_KEY': 'synthetic-app-key'})
    assert model.bedrock_api_key == 'synthetic-research-key'


def test_lab_parser_matches_production_for_commentary_and_fenced_json():
    from lab import BASE_ADAPTER, parse_lab_action
    from agents.freeform.runtime import _parse_action
    raw = 'Rationale: inspect the record.\n```json\n{"action":"search","corpus":"patient","query":"hemoglobin trend"}\n```'
    assert parse_lab_action(raw, BASE_ADAPTER).model_dump() == _parse_action(raw).model_dump()


@pytest.mark.parametrize('raw', [
    '```json\n{"action":"revise","note":"first"}\n```\n```json\n{"action":"revise","note":"second"}\n```',
    '[{"action":"revise","note":"array"}]',
    '```json\n{"action":"revise","note":"incomplete"}',
    '{"action":"revise","note":"bare"} followed by prose',
])
def test_lab_parser_preserves_production_rejections(raw):
    from lab import BASE_ADAPTER, parse_lab_action
    from agents.freeform.runtime import _parse_action
    for parser in (lambda value: parse_lab_action(value, BASE_ADAPTER), _parse_action):
        with pytest.raises(ValueError):
            parser(raw)


@pytest.mark.parametrize('status,expected_requests', [(429, 2), (403, 1)])
def test_bedrock_retries_throttling_but_not_authentication_errors(monkeypatch, status, expected_requests):
    import httpx
    from lab import LiveModel
    seen = []
    delays = []

    async def respond(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(status, headers={'x-amzn-errortype': 'SyntheticError'}, json={'message': 'synthetic'})
        return httpx.Response(200, json={'output': {'message': {'content': [{'text': 'OK'}]}},
                                         'usage': {'inputTokens': 2, 'outputTokens': 1}})

    async def fake_sleep(delay):
        delays.append(delay)

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **options: original_client(transport=httpx.MockTransport(respond), **options))
    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)
    model = LiveModel({'RESEARCH_PROVIDER': 'bedrock', 'RESEARCH_MODEL': 'synthetic-model',
                       'BEDROCK_API_KEY': 'synthetic-test-token'})
    operation = model.complete(system='s', user='u', max_tokens=512, timeout=30)
    if status == 403:
        with pytest.raises(RuntimeError, match='403'):
            asyncio.run(operation)
        assert delays == []
    else:
        assert asyncio.run(operation) == 'OK'
        assert delays == [10]
    assert len(seen) == expected_requests
    assert model.request_errors[0]['status'] == status


@pytest.mark.parametrize('arm', ['B', 'C'])
def test_required_routes_reject_search_shortcuts(arm):
    from lab import REQUIRED_ADAPTERS, parse_lab_action
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        parse_lab_action('{"action":"search","corpus":"patient","query":"shortcut"}', REQUIRED_ADAPTERS[arm])


@pytest.mark.parametrize('arm', ['A', 'B', 'C'])
def test_required_routes_cannot_finalize_before_reading_both_documents(arm, tmp_path):
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    docs = case['documents']
    if arm == 'A':
        reads = [{'action': 'search', 'corpus': corpus, 'query': 'synthetic evidence', 'top_k': 8} for corpus in ('patient', 'knowledge')]
    elif arm == 'B':
        reads = [{'action': 'structured', 'operation': 'document', 'document_id': doc['id']} for doc in docs]
    else:
        reads = [{'action': 'computer', 'operation': 'navigate', 'url': ORIGIN + '/documents/' + doc['id']} for doc in docs]
    model = ScriptedModel([finalized([]), *reads, finalized([doc['id'] for doc in docs])])
    computer = Computer(docs, tmp_path / 'computer') if arm == 'C' else None
    if computer:
        computer.__enter__()
    try:
        runtime = LabRuntime(arm, docs, model, Limits(), computer, retrieval_mode='required')
        result = asyncio.run(runtime.run('differential_diagnosis', case['question'], '', scope(case)))
        assert result['status'] == 'completed'
        assert any(event['action'] == 'finalize' and event['status'] == 'denied' for event in result['freeform']['events'])
        assert set(runtime.gateway._items) == {doc['id'] for doc in docs}
        if arm != 'A':
            assert len(runtime.lab_trace) == 2
            assert all(entry['tool'] == ('computer' if arm == 'C' else 'structured') for entry in runtime.lab_trace)
    finally:
        if computer:
            computer.close()


@pytest.mark.parametrize('http_status', [409, 500])
def test_browser_error_recovery_preserves_fatal_failures(http_status):
    from computer import ComputerActionError
    from agents.freeform.contracts import FreeFormExecutionError
    case = json.loads((ROOT / 'cases.json').read_text())[0]
    docs = case['documents']

    class Browser:
        def action(self, operation, **arguments):
            if operation == 'click':
                raise ComputerActionError(http_status, 'Synthetic stale snapshot or server failure')
            doc = next(d for d in docs if arguments['url'].endswith(d['id']))
            return {'url': arguments['url'], 'text': doc['text']}

    actions = [{'action': 'computer', 'operation': 'click', 'ref': 'e1', 'snapshot_id': 1}]
    actions += [{'action': 'computer', 'operation': 'navigate', 'url': ORIGIN + '/documents/' + d['id']} for d in docs]
    actions.append(finalized([d['id'] for d in docs]))
    runtime = LabRuntime('C', docs, ScriptedModel(actions), Limits(), Browser(), retrieval_mode='required')
    operation = runtime.run('differential_diagnosis', case['question'], '', scope(case))
    if http_status == 500:
        with pytest.raises(FreeFormExecutionError):
            asyncio.run(operation)
    else:
        result = asyncio.run(operation)
        assert result['status'] == 'completed'
        assert any(e['action'] == 'computer' and e['status'] == 'denied' for e in result['freeform']['events'])
        assert runtime.lab_trace[0]['result']['http_status'] == 409
