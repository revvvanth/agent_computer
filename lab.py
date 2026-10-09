"""Three-arm lab around an unmodified, hash-verified KareOS specialist snapshot."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
import time
import types
from pathlib import Path
from typing import Annotated, Literal

from dotenv import dotenv_values
from pydantic import Field, TypeAdapter, model_validator

from calculator import calculate
from computer import Computer, ComputerActionError, ORIGIN, ROOT, docker, safe_path

# Namespace packages bypass production package initializers and their service imports.
for name, directory in [('agents', 'agents'), ('agents.harness', 'agents/harness'), ('agents.freeform', 'agents/freeform')]:
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / 'source_snapshot' / directory)]
    sys.modules[name] = package

from agents.freeform.contracts import (
    Action, CalculateClinicalScores, CapabilityDenied, Fetch, Finalize, Limits,
    RequestInput, Revise, Scope, Search, StrictModel,
)
from agents.freeform.gateway import EvidenceGateway, EvidenceItem
from agents.freeform.persistence import NullRunStore
from agents.freeform.profiles import system_prompt
from agents.freeform.runtime import FreeFormSpecialistRuntime, _FENCE_RE, _THINK_RE


class ExtraAction(StrictModel):
    action: Literal['structured', 'computer']
    operation: Literal['documents', 'document', 'navigate', 'snapshot', 'click', 'read', 'calculate', 'read_file', 'write_file']
    document_id: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=250)
    ref: str | None = Field(default=None, max_length=128)
    snapshot_id: int | None = None
    expression: str | None = Field(default=None, max_length=200)
    path: str | None = Field(default=None, max_length=64)
    contents: str | None = Field(default=None, max_length=4000)

    @model_validator(mode='after')
    def required_arguments(self):
        required = {'document': ('document_id',), 'navigate': ('url',), 'click': ('ref', 'snapshot_id'),
                    'calculate': ('expression',), 'read_file': ('path',), 'write_file': ('path', 'contents')}
        missing = [name for name in required.get(self.operation, ()) if getattr(self, name) is None]
        if missing:
            raise ValueError('Missing tool arguments: ' + ', '.join(missing))
        return self


BaseAction = Search | Fetch | Revise | RequestInput | CalculateClinicalScores | Finalize
BASE_ADAPTER = TypeAdapter(Annotated[BaseAction, Field(discriminator='action')])
EXTRA_ADAPTER = TypeAdapter(BaseAction | ExtraAction)


class StructuredAction(ExtraAction):
    action: Literal['structured']


class ComputerAction(ExtraAction):
    action: Literal['computer']


RequiredBaseAction = Revise | RequestInput | CalculateClinicalScores | Finalize
REQUIRED_ADAPTERS = {
    'A': BASE_ADAPTER,
    'B': TypeAdapter(Annotated[RequiredBaseAction | StructuredAction, Field(discriminator='action')]),
    'C': TypeAdapter(Annotated[RequiredBaseAction | ComputerAction, Field(discriminator='action')]),
}


def parse_lab_action(raw, adapter):
    """Same explicit delimiter rules as the frozen production action parser."""
    cleaned = _THINK_RE.sub('', str(raw or '')).strip()
    blocks = _FENCE_RE.findall(cleaned)
    if len(blocks) > 1:
        raise ValueError('response contains more than one JSON block')
    if blocks:
        cleaned = blocks[0].strip()
    elif cleaned.startswith('```'):
        raise ValueError('response has an incomplete Markdown fence')
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError('action must be a JSON object')
    return adapter.validate_python(value)


class FixtureGateway(EvidenceGateway):
    def __init__(self, documents):
        super().__init__()
        self.documents = documents

    def register(self, scope, doc):
        self._bind(scope)
        item = EvidenceItem(doc['id'], doc['corpus'], doc['id'], doc['title'], doc['text'],
                            doc['id'] if doc['corpus'] == 'patient' else None, strategy='synthetic_fixture')
        self._items[item.evidence_id] = item
        return item

    async def search(self, scope, *, corpus, query, top_k):
        self._bind(scope)
        words = set(re.findall(r'\w+', query.lower()))
        docs = [d for d in self.documents if d['corpus'] == corpus]
        docs.sort(key=lambda d: -len(words & set(re.findall(r'\w+', (d['title'] + ' ' + d['text']).lower()))))
        return [self.register(scope, d) for d in docs[:top_k]]


class LabRuntime(FreeFormSpecialistRuntime):
    def __init__(self, arm, documents, model, limits, computer=None, retrieval_mode='offered'):
        self.arm = arm
        self.documents = documents
        self.computer = computer
        self.retrieval_mode = retrieval_mode
        self.notes = {}
        self.lab_trace = []
        self.gateway = FixtureGateway(documents)
        super().__init__(model=model, limits=limits, store=NullRunStore(), gateway_factory=lambda: self.gateway)
        self.adapter = REQUIRED_ADAPTERS[arm] if retrieval_mode == 'required' else (BASE_ADAPTER if arm == 'A' else EXTRA_ADAPTER)
        self._action_schema = self.adapter.json_schema()

    async def _next_action(self, investigation, session, *, root, turn):
        common = (
            '\nThis is a synthetic single-specialist experiment. No clinician answers during a run. '
            'Only actions in the supplied schema are available; delegation and production scores are disabled. '
            'Every arm has the same fixed two-document library through its enabled retrieval interface. '
            'Evidence IDs must be retrieved before citation. Library fixtures are exercise facts, not published guidelines. '
        )
        extra = ''
        if self.arm == 'B':
            extra = ('Additional action structured: documents lists IDs/titles; document(document_id) reads a source; '
                     'calculate(expression) evaluates numeric + - * /; read_file(path)/write_file(path,contents) manages .txt scratch notes.')
        elif self.arm == 'C':
            extra = (f'Additional action computer: navigate(url) opens {ORIGIN}/ or an available /documents/ID; '
                     'snapshot lists interactive refs with snapshotId; click(ref,snapshot_id) uses the most recent snapshot; '
                     'Every navigation or click makes earlier snapshot refs stale. Take a fresh snapshot before another click. '
                     'read reads the current page; calculate(expression) executes bounded arithmetic in the container; '
                     'read_file(path)/write_file(path,contents) manages .txt scratch notes. Screenshots are saved for reviewers, not sent to you. '
                     'There is no arbitrary shell, internet or application access.')
        if self.retrieval_mode == 'required':
            common += 'Before finalizing, read both documents in the library. No answer labels are provided. '
            if self.arm == 'A':
                extra = 'Your evidence interface is search/fetch. Search patient and knowledge corpora to read both documents.'
            elif self.arm == 'B':
                extra += ' Required interface: structured tools. Search/fetch and computer actions are unavailable. Start with structured documents, then read each document by its ID.'
            else:
                extra += f' Required interface: computer browser only. Search/fetch and structured actions are unavailable. Start by navigating to {ORIGIN}/, snapshot its links, and click/read both documents. Choose and execute your own browser actions; the controller does not retrieve documents for you.'
        system = system_prompt(session.specialty, session.profile, root, self._action_schema) + common + extra
        user = self._workspace(investigation, session, root=root, turn=turn, system_chars=len(system))
        timeout = await investigation.budget.reserve_model_call((len(system) + len(user) + 3) // 4 + self._limits.max_output_tokens)
        async with asyncio.timeout(timeout):
            async with investigation.budget.model_slots:
                raw = await self._model.complete(system=system, user=user, max_tokens=self._limits.max_output_tokens,
                                                 timeout=min(timeout, investigation.budget.remaining_seconds()))
        return parse_lab_action(raw, self.adapter)

    async def _execute_action(self, investigation, session, action, *, root):
        if self.retrieval_mode == 'required':
            if self.arm != 'A' and isinstance(action, (Search, Fetch)):
                raise CapabilityDenied('Use this arm’s required evidence interface')
            if isinstance(action, Finalize):
                unread = {doc['id'] for doc in self.documents} - set(self.gateway._items)
                if unread:
                    raise CapabilityDenied('Read both library documents through your enabled interface before finalizing. Unread IDs: ' + ', '.join(sorted(unread)))
        if isinstance(action, CalculateClinicalScores):
            await investigation.budget.reserve_tool()
            session.observations.append({'event': 'clinical_calculator_result', 'scores': [],
                                         'limitations': ['Production score calculators are unavailable in this synthetic lab; never invent missing inputs.']})
            return None
        if not isinstance(action, ExtraAction):
            return await super()._execute_action(investigation, session, action, root=root)
        expected = {'B': 'structured', 'C': 'computer'}.get(self.arm)
        if action.action != expected:
            raise CapabilityDenied('Tool is not enabled for this arm')
        await investigation.budget.reserve_tool()
        arguments = action.model_dump(exclude_none=True)
        arguments.pop('action')
        operation = arguments.pop('operation')
        try:
            if self.arm == 'B':
                result = self.structured(operation, investigation.scope, arguments)
            else:
                if operation in ('documents', 'document'):
                    raise ValueError('Use the browser to open/read documents in the computer arm')
                result = await asyncio.to_thread(self.computer.action, operation, **arguments)
                text = result.get('text', '')
                for doc in self.documents:
                    # Source registration requires actual document content, not an index title or link.
                    if result.get('url') == ORIGIN + '/documents/' + doc['id'] and doc['text'] in text:
                        self.gateway.register(investigation.scope, doc)
            self.lab_trace.append({'tool': action.action, 'operation': operation, 'arguments': arguments, 'result': result})
            session.observations.append({'event': action.action + '_result', 'operation': operation, 'result': result})
        except ComputerActionError as error:
            if error.status not in (400, 404, 409, 422):
                raise
            self.lab_trace.append({'tool': action.action, 'operation': operation, 'arguments': arguments,
                                   'result': {'error': str(error), 'http_status': error.status}, 'status': 'denied'})
            raise CapabilityDenied(str(error) + ' Refresh the current browser snapshot and use its refs/snapshotId before another click.') from error
        except (ValueError, KeyError) as error:
            raise CapabilityDenied(str(error)) from error
        return None

    def structured(self, operation, scope, arguments):
        if operation == 'documents':
            return {'documents': [{'id': d['id'], 'title': d['title']} for d in self.documents]}
        if operation == 'document':
            doc = next((d for d in self.documents if d['id'] == arguments['document_id']), None)
            if not doc:
                raise ValueError('Document outside this case')
            return self.gateway.register(scope, doc).public()
        if operation == 'calculate':
            return {'expression': arguments['expression'], 'value': calculate(arguments['expression'])}
        if operation in ('read_file', 'write_file'):
            path = safe_path(arguments['path'])
            if operation == 'write_file':
                self.notes[path] = arguments['contents']
            if path not in self.notes:
                raise ValueError('Note does not exist')
            return {'path': path, 'contents': self.notes[path]}
        raise ValueError('Unsupported structured operation')


class LiveModel:
    def __init__(self, config):
        self.config = config
        self.calls = []
        self.request_errors = []
        self.provider = config.get('RESEARCH_PROVIDER')
        self.model = config.get('RESEARCH_MODEL')
        self.bedrock_api_key = config.get('RESEARCH_BEDROCK_API_KEY') or config.get('BEDROCK_API_KEY') or config.get('AWS_BEARER_TOKEN_BEDROCK')
        self.region = config.get('RESEARCH_AWS_REGION') or 'us-east-1'
        if self.provider not in ('bedrock', 'openai-compatible') or not self.model:
            raise ValueError('Configure RESEARCH_PROVIDER and an explicit RESEARCH_MODEL in computer_research/.env')
        if self.provider == 'openai-compatible' and not config.get('RESEARCH_API_KEY'):
            raise ValueError('RESEARCH_API_KEY is missing in computer_research/.env')
        if self.provider == 'bedrock' and not self.bedrock_api_key:
            import boto3
            session = boto3.Session(profile_name=config.get('RESEARCH_AWS_PROFILE') or None,
                                    region_name=config.get('RESEARCH_AWS_REGION') or 'us-east-1')
            if session.get_credentials() is None:
                raise ValueError('No AWS credentials available for the selected research profile')
            self.session = session

    async def complete(self, *, system, user, max_tokens, timeout):
        started = time.monotonic()
        temperature = float(self.config.get('RESEARCH_TEMPERATURE') or '0.2')
        if self.provider == 'bedrock':
            payload = {'system': [{'text': system}],
                       'messages': [{'role': 'user', 'content': [{'text': user}]}],
                       'inferenceConfig': {'temperature': temperature, 'maxTokens': max_tokens}}
            if self.bedrock_api_key:
                import httpx
                from urllib.parse import quote
                if not re.fullmatch(r'[a-z]{2}-[a-z]+-\d', self.region):
                    raise ValueError('Invalid research AWS region')
                endpoint = f'https://bedrock-runtime.{self.region}.amazonaws.com/model/{quote(self.model, safe="")}/converse'
                deadline = time.monotonic() + timeout
                async with httpx.AsyncClient() as client:
                    for attempt in range(4):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('Bedrock request deadline exhausted')
                        result = await client.post(endpoint, headers={'Authorization': 'Bearer ' + self.bedrock_api_key}, json=payload, timeout=remaining)
                        if result.status_code < 400:
                            response = result.json()
                            break
                        error = {'status': result.status_code, 'attempt': attempt + 1,
                                 'category': result.headers.get('x-amzn-errortype', '').split(':')[0]}
                        self.request_errors.append(error)
                        delay = 10 * 2 ** attempt
                        if result.status_code != 429 or attempt == 3 or delay >= deadline - time.monotonic():
                            raise RuntimeError(f'Bedrock model HTTP error {result.status_code}')
                        error['retry_delay_seconds'] = delay
                        await asyncio.sleep(delay)
            else:
                from botocore.config import Config
                client = self.session.client('bedrock-runtime', config=Config(connect_timeout=10, read_timeout=timeout, retries={'total_max_attempts': 1}))
                response = await asyncio.to_thread(client.converse, modelId=self.model, **payload)
            text = ''.join(block.get('text', '') for block in response['output']['message']['content'])
            usage = {'input_tokens': response['usage']['inputTokens'], 'output_tokens': response['usage']['outputTokens']}
        else:
            import httpx
            base = (self.config.get('RESEARCH_BASE_URL') or '').rstrip('/')
            if not base.startswith('https://'):
                raise ValueError('An explicit HTTPS RESEARCH_BASE_URL is required')
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(base + '/chat/completions', headers={'Authorization': 'Bearer ' + self.config['RESEARCH_API_KEY']},
                                             json={'model': self.model, 'temperature': temperature, 'max_tokens': max_tokens,
                                                   'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]})
                if response.status_code >= 400:
                    # Response bodies may contain provider-specific sensitive data.
                    raise RuntimeError(f'Model HTTP error {response.status_code}')
                data = response.json()
            text = data['choices'][0]['message']['content']
            reported = data.get('usage') or {}
            usage = {'input_tokens': reported.get('prompt_tokens'), 'output_tokens': reported.get('completion_tokens')}
        self.calls.append({'system': system, 'user': user, 'response': text, 'usage': usage,
                           'seconds': round(time.monotonic() - started, 3)})
        return text


def configuration():
    file_values = dotenv_values(ROOT / '.env')
    # Configuration must work without the original user's credential-filled example.
    names = {'RESEARCH_PROVIDER', 'RESEARCH_MODEL', 'RESEARCH_AWS_REGION',
             'RESEARCH_AWS_PROFILE', 'RESEARCH_BASE_URL', 'RESEARCH_API_KEY',
             'RESEARCH_TEMPERATURE', 'RESEARCH_INPUT_PRICE', 'RESEARCH_OUTPUT_PRICE',
             'RESEARCH_BEDROCK_API_KEY', 'BEDROCK_API_KEY', 'AWS_BEARER_TOKEN_BEDROCK'}
    return {name: os.environ.get(name, file_values.get(name)) for name in names}


def snapshot_integrity(*, compare_parent=False):
    manifest = json.loads((ROOT / 'source_snapshot/manifest.json').read_text(encoding='utf-8-sig'))
    # Manifest is frozen at isolation time. Never regenerate from changed files.
    records = manifest.get('files', manifest) if isinstance(manifest, dict) else manifest
    if isinstance(records, dict):
        records = [{'path': path, 'sha256': digest} for path, digest in records.items()]
    for record in records:
        path = record.get('path', record.get('source'))
        digest = record['sha256'].lower()
        bases = [ROOT / 'source_snapshot']
        if compare_parent:
            bases.append(ROOT.parent)
        for base in bases:
            if hashlib.sha256((base / path).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Source snapshot drift: ' + path)
    return True


def parent_integrity():
    """Verify bundled sources everywhere; protect the original checkout only in place.

    The local, excluded guard binds to an exact parent path. A moved/exported
    project neither reads parent sources nor requires any Git repository.
    Historical callers keep this function name and report fields for compatibility.
    """
    snapshot_integrity()
    guard_path = ROOT / '.kareos-parent-guard.json'
    guard = json.loads(guard_path.read_text(encoding='utf-8-sig')) if guard_path.exists() else {}
    guarded_parent = guard.get('parent_path')
    if not guarded_parent or Path(guarded_parent).resolve() != ROOT.parent.resolve():
        return {'mode': 'standalone', 'snapshot_hashes_match': True,
                'parent_guard_active': False, 'parent_index_unchanged': None,
                'parent_tracked_worktree_unchanged': None,
                'snapshot_and_original_hashes_match': None}
    def git(*args):
        import subprocess
        return subprocess.check_output(['git', '-C', str(ROOT.parent), *args], text=True, encoding='utf-8').strip()
    checks = [('.baseline-head.txt', ('rev-parse', 'HEAD')), ('.baseline-merge-head.txt', ('rev-parse', 'MERGE_HEAD')),
              ('.baseline-index.txt', ('diff', '--cached', '--raw'))]
    for filename, command in checks:
        if git(*command) != (ROOT / filename).read_text(encoding='utf-8-sig').strip():
            raise RuntimeError('Parent Git state changed: ' + filename)
    if git('diff', '--name-only'):
        raise RuntimeError('Parent tracked working files changed')
    snapshot_integrity(compare_parent=True)
    return {'head': git('rev-parse', 'HEAD'), 'merge_head': git('rev-parse', 'MERGE_HEAD'),
            'mode': 'embedded', 'parent_guard_active': True, 'snapshot_hashes_match': True,
            'branch': git('branch', '--show-current'), 'parent_index_unchanged': True,
            'parent_tracked_worktree_unchanged': True, 'snapshot_and_original_hashes_match': True}


def proxy_metrics(output, case, registered):
    data = output.get('data') or {}
    text = json.dumps(data, ensure_ascii=False).casefold()
    def present(term):
        return bool(re.search(r'\b' + re.escape(term.casefold()) + r'\b', text)) if len(term) == 1 else term.casefold() in text
    signals = case['review']['signals']
    covered = sum(any(present(term) for term in alternatives) for alternatives in signals)
    refs = data.get('evidence_references', [])
    return {'keyword_signal_coverage': covered / len(signals), 'covered_signals': covered,
            'total_signals': len(signals), 'citation_count': len(refs),
            'unretrieved_citations': [ref for ref in refs if ref not in registered],
            'clinical_accuracy': None, 'clinical_review': 'pending',
            'warning': 'Keyword presence does not establish correctness, support or clinical usefulness.'}


async def run_trial(case, arm, model, limits, directory, retrieval_mode='offered'):
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    computer = None
    startup = None
    runtime = None
    try:
        if arm == 'C':
            computer = Computer(case['documents'], directory / 'computer')
            await asyncio.to_thread(computer.__enter__)
            startup = computer.inspect()
        runtime = LabRuntime(arm, case['documents'], model, limits, computer, retrieval_mode=retrieval_mode)
        scope = Scope(tenant_id='synthetic-lab', user_id='researcher', encounter_id=case['id'],
                      document_ids=tuple(d['id'] for d in case['documents'] if d['corpus'] == 'patient'))
        inference_started = time.monotonic()
        output = await runtime.run('differential_diagnosis', case['question'], '', scope)
        report = {'status': 'completed', 'output': output,
                  'proxy_metrics': proxy_metrics(output, case, runtime.gateway._items),
                  'inference_seconds': round(time.monotonic() - inference_started, 3)}
    except Exception as error:
        report = {'status': 'failed', 'error_type': type(error).__name__,
                  'trace': getattr(error, 'trace', None), 'clinical_review': 'pending'}
    finally:
        if computer and computer.created:
            try:
                await asyncio.to_thread(computer.screenshot)
            except Exception:
                pass  # No browser may have been opened; screenshot availability is not clinical success.
            await asyncio.to_thread(computer.close)
    report.update({'case_id': case['id'], 'arm': arm, 'computer': startup,
                   'retrieval_mode': retrieval_mode,
                   'retrieved_document_ids': sorted(runtime.gateway._items) if runtime else [],
                   'total_seconds': round(time.monotonic() - started, 3), 'model_calls': model.calls,
                   'provider_request_errors': model.request_errors,
                   'lab_tool_trace': runtime.lab_trace if runtime else [], 'simulated': False})
    usage = [call['usage'] for call in model.calls]
    report['usage'] = {key: sum(u[key] for u in usage) if all(u[key] is not None for u in usage) else None
                       for key in ('input_tokens', 'output_tokens')}
    rates = [model.config.get('RESEARCH_INPUT_PRICE'), model.config.get('RESEARCH_OUTPUT_PRICE')]
    report['estimated_usd'] = (sum(report['usage'][key] * float(rate) / 1e6 for key, rate in zip(('input_tokens', 'output_tokens'), rates))
                               if all(rates) and all(v is not None for v in report['usage'].values()) else None)
    (directory / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


async def live(args):
    parent_integrity()
    config = configuration()
    LiveModel(config)  # Fail before creating any container or report if credentials/model are absent.
    protocol_file = 'protocol.required.json' if getattr(args, 'protocol', 'offered') == 'required' else 'protocol.json'
    protocol = json.loads((ROOT / protocol_file).read_text())
    retrieval_mode = protocol.get('retrieval_mode', 'offered')
    cases = json.loads((ROOT / 'cases.json').read_text())[:args.cases]
    schedule = [(case, arm, repeat) for case in cases for repeat in range(args.repeats) for arm in protocol['arms']]
    random.Random(protocol['seed']).shuffle(schedule)
    prefix = 'required-' if retrieval_mode == 'required' else 'live-'
    directory = ROOT / 'reports' / time.strftime(prefix + '%Y%m%d-%H%M%S')
    directory.mkdir(parents=True)
    settings = {'protocol': protocol, 'provider': config['RESEARCH_PROVIDER'], 'model': config['RESEARCH_MODEL'],
                'temperature': config.get('RESEARCH_TEMPERATURE') or '0.2', 'case_count': len(cases),
                'bedrock_throttle_retry': {'max_attempts': 4, 'delays_seconds': [10, 20, 40], 'within_call_deadline': True},
                'repeats': args.repeats, 'case_sha256': hashlib.sha256((ROOT / 'cases.json').read_bytes()).hexdigest(),
                'openbot_commit': '4773ef6866544a497c2a33ed2475bb4aa1de0475',
                'parent_before': parent_integrity(), 'simulated': False}
    (directory / 'settings.json').write_text(json.dumps(settings, indent=2))
    results = []
    review_mapping = {}
    for index, (case, arm, repeat) in enumerate(schedule, start=1):
        print(f'{index}/{len(schedule)}: {case["id"]} arm {arm} repeat {repeat + 1}', flush=True)
        result = await run_trial(case, arm, LiveModel(config), Limits(**protocol['limits']), directory / f'{case["id"]}-{arm}-{repeat+1}', retrieval_mode=retrieval_mode)
        results.append(result)
        blind_id = f'review-{index:03}'
        review_mapping[blind_id] = {'case_id': case['id'], 'arm': arm, 'repeat': repeat + 1}
        review = {'review_id': blind_id, 'case': {k: v for k, v in case.items() if k != 'review'},
                  'rubric': case['review'], 'output': result.get('output', {}).get('data'),
                  'review_fields': {'correct_additional_findings': None, 'unsupported_claims': None,
                                    'citation_support': None, 'usefulness_1_to_5': None, 'reviewer_comments': ''}}
        review_dir = directory / 'blinded-review'
        review_dir.mkdir(exist_ok=True)
        (review_dir / (blind_id + '.json')).write_text(json.dumps(review, indent=2))
    summary = {'settings': settings, 'parent_after': parent_integrity(), 'completed': sum(r['status'] == 'completed' for r in results),
               'planned': len(schedule), 'clinical_review': 'pending', 'review_mapping': review_mapping}
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2))
    rows = ['# Live pilot results', '', 'Clinical review is pending. No accuracy conclusion can be drawn from keyword coverage.', '',
            '| Arm | Completed | Mean inference seconds | Mean keyword coverage (proxy) |', '|---|---:|---:|---:|']
    for arm in protocol['arms']:
        completed = [r for r in results if r['arm'] == arm and r['status'] == 'completed']
        mean = lambda key: sum(r[key] for r in completed) / len(completed) if completed else None
        coverage = sum(r['proxy_metrics']['keyword_signal_coverage'] for r in completed) / len(completed) if completed else None
        rows.append(f'| {arm} | {len(completed)}/{len(cases)*args.repeats} | {mean("inference_seconds")} | {coverage} |')
    (directory / 'SUMMARY.md').write_text('\n'.join(rows))
    print('Results: ' + str(directory))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('smoke')
    run = sub.add_parser('run')
    run.add_argument('--cases', type=int, choices=range(1, 13), default=3)
    run.add_argument('--repeats', type=int, choices=range(1, 4), default=1)
    run.add_argument('--protocol', choices=['offered', 'required'], default='offered')
    args = parser.parse_args()
    if args.command == 'check':
        print(json.dumps(parent_integrity(), indent=2))
    elif args.command == 'smoke':
        from smoke import smoke
        smoke()
    else:
        try:
            asyncio.run(live(args))
        except ValueError as error:
            print('Live evaluation blocked: ' + str(error), file=sys.stderr)
            sys.exit(2)


if __name__ == '__main__':
    main()
